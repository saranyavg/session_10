"""Session 8 skill registry + per-skill execution.

The orchestrator (flow.py) treats every node as a `Skill` object loaded
from agent_config.yaml. There is no Python class per skill — that
abstraction would have to be added at the point where a skill needs
behaviour the orchestrator can't infer from the yaml. Today every skill
either calls the gateway or (for sandbox_executor) calls sandbox.py.

What lives here:
  - Skill / SkillRegistry
  - input resolution (`n:...`, `art:...`, `USER_QUERY`, literals)
  - prompt rendering (template + inputs + optional failure report)
  - JSON parsing of the model's reply (single top-level object)
  - the MCP tool schemas exposed to tool-using skills
  - `run_skill(...)` — the dispatcher
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import yaml
from pydantic import ValidationError

import artifacts as artifacts_svc
from gateway import LLM
from schemas import AgentResult, NodeSpec

ROOT = Path(__file__).parent
AGENT_CONFIG_PATH = ROOT / "agent_config.yaml"


# ── catalogue ────────────────────────────────────────────────────────────────

class Skill:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.prompt_path = ROOT / cfg["prompt"]
        self.description = cfg.get("description", "")
        self.tools_allowed: list[str] = cfg.get("tools_allowed", []) or []
        self.internal_successors: list[str] = cfg.get("internal_successors", []) or []
        self.critic: bool = bool(cfg.get("critic", False))
        self.provider_pin: str | None = cfg.get("provider_pin")
        # P2 #10: per-skill temperature / max_tokens come from the yaml so
        # tuning a single skill no longer requires a code edit. Defaults
        # are deliberately conservative; a skill that wants exploration
        # (Researcher) bumps temperature; a skill that wants determinism
        # (Critic, Distiller) drops it to ~0.
        self.temperature: float = float(cfg.get("temperature", 0.3))
        self.max_tokens: int = int(cfg.get("max_tokens", 2048))

    def prompt_template(self) -> str:
        if not self.prompt_path.exists():
            return f"You are the {self.name} skill. (Prompt file missing.)"
        return self.prompt_path.read_text()


class SkillRegistry:
    def __init__(self):
        cfg = yaml.safe_load(AGENT_CONFIG_PATH.read_text())
        self._skills: dict[str, Skill] = {n: Skill(n, c) for n, c in cfg.items()}

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(f"unknown skill: {name}")
        return self._skills[name]

    def names(self) -> list[str]:
        return list(self._skills)


# ── input resolution + prompt rendering ──────────────────────────────────────

def resolve_inputs(node_inputs: list[str], graph_nodes, query: str) -> list[dict]:
    """Materialise each input id into a dict the prompt can serialise.

    Recognised input forms:
      - "USER_QUERY"  → the original user query text
      - "n:<i>"       → the AgentResult.output of that completed node
      - "art:<sha>"   → the bytes of an artifact, decoded as utf-8 best-effort
      - any other     → passed through as a free-form string

    `graph_nodes` is the nx node-view dict from flow.Graph; we read each
    upstream node's `result` attribute (set when the orchestrator marks
    the node complete).
    """
    out = []
    for inp in node_inputs:
        if inp == "USER_QUERY":
            out.append({"id": "USER_QUERY", "kind": "query", "value": query})
        elif inp.startswith("n:") and inp in graph_nodes:
            upstream = graph_nodes[inp].get("result")
            if isinstance(upstream, AgentResult):
                out.append({"id": inp, "kind": "upstream",
                            "skill": upstream.agent_name, "output": upstream.output})
            else:
                out.append({"id": inp, "kind": "upstream-missing", "output": None})
        elif inp.startswith("art:"):
            try:
                blob = artifacts_svc.get_bytes(inp)
                text = blob.decode("utf-8", errors="replace")
                out.append({"id": inp, "kind": "artifact", "text": text[:20_000]})
            except Exception as e:
                out.append({"id": inp, "kind": "artifact-missing", "error": str(e)})
        else:
            out.append({"id": inp, "kind": "literal", "value": inp})
    return out


def _format_memory_hits(hits: list) -> str:
    """Compact rendering of FAISS-ranked MemoryItem hits for the prompt.

    Each hit is shown as one line: kind, descriptor, source, plus a 400-char
    preview of `value.chunk` when present (indexed-document chunks) or of
    `value.raw` (classifier facts). The full chunk would blow the prompt,
    but the descriptor + preview is enough for the Planner to decide
    whether memory already covers the query and for downstream skills to
    synthesise from indexed material without an extra Retriever round-trip.
    """
    if not hits:
        return ""
    lines = []
    for h in hits[:8]:  # cap to keep the prompt bounded
        kind = getattr(h, "kind", "?")
        desc = (getattr(h, "descriptor", "") or "")[:200]
        source = getattr(h, "source", "")
        val = getattr(h, "value", {}) or {}
        chunk = val.get("chunk")
        raw = val.get("raw")
        line = f"  - [{kind}] {desc}"
        if source:
            line += f"\n      source: {source}"
        if isinstance(chunk, str) and chunk.strip():
            preview = chunk[:2000].replace("\n", " ")
            more = " …" if len(chunk) > 2000 else ""
            line += f"\n      chunk: {preview}{more}"
        elif isinstance(raw, str) and raw.strip():
            raw_more = " …" if len(raw) > 2000 else ""
            line += f"\n      raw: {raw[:2000]}{raw_more}"
        lines.append(line)
    return "\n".join(lines)


def render_prompt(skill: Skill, query: str, resolved: list[dict],
                  failure_report: str | None = None,
                  memory_hits: list | None = None,
                  question: str | None = None) -> str:
    parts = [skill.prompt_template().rstrip()]
    # USER_QUERY top-line: only when the Planner wired USER_QUERY into this
    # node's inputs. Earlier versions added it unconditionally, which
    # leaked the full original query into every fan-out worker — three
    # researcher siblings spawned to "find population of A / B / C" all
    # saw the same "compare A, B, C" query and each one ended up
    # searching for all three. Per-node scoping now travels through
    # `metadata.question` (rendered as QUESTION below) and the INPUTS
    # block; USER_QUERY is present only when the Planner asked for it.
    user_query_in_inputs = any(
        isinstance(r, dict) and r.get("id") == "USER_QUERY" for r in resolved
    )
    if user_query_in_inputs:
        parts += ["", f"USER_QUERY: {query}"]
    # QUESTION: the per-node sub-question the Planner attached via
    # `metadata.question`. This is how a fan-out worker learns *its*
    # slice of the user's request without seeing the whole query.
    if isinstance(question, str) and question.strip():
        parts += ["", f"QUESTION: {question.strip()}"]
    if failure_report:
        parts += ["", f"FAILURE:\n{failure_report}"]
    # Memory hits — FAISS-ranked MemoryItems from session-start memory.read.
    # Same hits flow into every skill's prompt this run (the S7 contract:
    # every cognitive role can see what the agent already knows).
    hits_block = _format_memory_hits(memory_hits or [])
    if hits_block:
        parts += ["", f"MEMORY HITS ({len(memory_hits)} from FAISS):", hits_block]
    parts += ["", "INPUTS:", json.dumps(resolved, indent=2, default=str)[:20_000]]
    return "\n".join(parts)


def parse_skill_json(text: str) -> dict:
    """Skills return a single top-level JSON object. Strip markdown fences
    if the model added them despite being told not to."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


# ── MCP tool schemas exposed through the gateway tools= channel ──────────────

_TOOL_CATALOG = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web (Tavily primary, DDG fallback). Hard-capped at 5 results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    "fetch_url": {
        "name": "fetch_url",
        "description": "Fetch clean markdown from a URL via crawl4ai.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "search_knowledge": {
        "name": "search_knowledge",
        "description": "Vector search over the agent's indexed knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
}


def tool_payload(tool_names: list[str]) -> list[dict] | None:
    if not tool_names:
        return None
    return [_TOOL_CATALOG[n] for n in tool_names if n in _TOOL_CATALOG]



async def generate_replay_report(session_id: str, query: str, graph_nodes, parsed_output: dict) -> None:
    import os
    import json
    import httpx
    import time
    from pathlib import Path
    
    # 1. Reconstruct DAG and gather node stats
    dag_nodes = []
    dag_edges = []
    browser_nodes = []
    
    # Sort nodes by completion time if possible, or numeric id
    sorted_nids = sorted(
        [nid for nid in graph_nodes if nid.startswith("n:")],
        key=lambda x: int(x.split(":")[1]) if x.split(":")[1].isdigit() else 9999
    )
    
    for nid in sorted_nids:
        node_attr = graph_nodes[nid]
        skill = node_attr.get("skill")
        status = node_attr.get("status")
        inputs = node_attr.get("inputs", [])
        result = node_attr.get("result")
        
        # Track node
        dag_nodes.append({
            "id": nid,
            "skill": skill,
            "status": status,
            "inputs": inputs,
            "elapsed": getattr(result, "elapsed_s", 0.0) if result else 0.0,
            "provider": getattr(result, "provider", "") if result else "",
            "success": getattr(result, "success", False) if result else False,
            "error": getattr(result, "error", "") if result else ""
        })
        
        # Build edges from inputs
        for inp in inputs:
            if inp.startswith("n:") and inp in graph_nodes:
                dag_edges.append((inp, nid))
                
        # Specialized node tracking
        if skill == "browser" and result:
            browser_nodes.append((nid, node_attr, result))
            
    # 2. Reconstruct graphical DAG text representation
    dag_lines = []
    dag_lines.append("```")
    
    parent_map = {}
    for edge in dag_edges:
        p, c = edge
        if p not in parent_map:
            parent_map[p] = []
        parent_map[p].append(c)
        
    predecessors = set(c for p, c in dag_edges)
    roots = [nid for nid in graph_nodes if nid not in predecessors]
    if "n:1" in graph_nodes:
        roots = ["n:1"]
        
    def draw_tree(node_id, indent=""):
        children = parent_map.get(node_id, [])
        for i, child in enumerate(children):
            c_attr = graph_nodes[child]
            skill_name = c_attr.get("skill", "")
            status = c_attr.get("status", "")
            is_last = (i == len(children) - 1)
            prefix = "└─ " if is_last else "├─ "
            meta_str = ""
            if skill_name == "browser":
                url = c_attr.get("metadata", {}).get("url", "")
                meta_str = f" (url={url})"
            dag_lines.append(f"{indent}{prefix}{skill_name.capitalize()} ({child}) [{status}]{meta_str}")
            draw_tree(child, indent + ("     " if is_last else "│    "))
            
    for root in roots:
        r_attr = graph_nodes[root]
        r_skill = r_attr.get("skill", "")
        r_status = r_attr.get("status", "")
        dag_lines.append(f"{r_skill.capitalize()} ({root}) [{r_status}]")
        draw_tree(root, "")
    dag_lines.append("```")
    dag_text = "\n".join(dag_lines)
    
    # 3. Retrieve cost statistics from gateway
    cost_data = {}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"http://localhost:8109/v1/cost/by_agent?session={session_id}", timeout=5.0)
            if r.status_code == 200:
                cost_data = r.json()
    except Exception as e:
        print(f"[report] Failed to fetch cost stats: {e!r}")
        
    # Format Cost Summary Table (Markdown)
    cost_rows = []
    total_calls = 0
    total_in = 0
    total_out = 0
    total_dollars = 0.0
    
    for agent, rows in cost_data.items():
        for row in rows:
            provider = row.get("provider", "")
            calls = row.get("calls", 0)
            in_tok = row.get("in_tok") or row.get("in_tokens") or 0
            out_tok = row.get("out_tok") or row.get("out_tokens") or 0
            dollars = row.get("dollars", 0.0)
            
            cost_rows.append(f"| {agent} | {provider} | {calls} | {in_tok} / {out_tok} | ${dollars:.6f} |")
            total_calls += calls
            total_in += in_tok
            total_out += out_tok
            total_dollars += dollars
            
    cost_table_md = "\n".join([
        "| Agent | Provider | Calls | Tokens (In/Out) | USD Cost |",
        "|---|---|---|---|---|",
        *cost_rows,
        f"| **Total** | | **{total_calls}** | **{total_in} / {total_out}** | **${total_dollars:.6f}** |"
    ])
    
    # 4. Gather Browser Node details
    browser_details_md = []
    session_dir = Path(__file__).parents[1].joinpath("state", "sessions", session_id)
    browser_dir = session_dir / "browser"
    
    for nid, node_attr, result in browser_nodes:
        out = result.output or {}
        url = out.get("url") or node_attr.get("metadata", {}).get("url") or ""
        goal = out.get("goal") or node_attr.get("metadata", {}).get("goal") or ""
        path = out.get("path")
        if not path and result.error_code == "gateway_blocked":
            path = "blocked"
        elif not path:
            path = "failed"
            
        turns = out.get("turns", 0)
        actions = out.get("actions", [])
        final_url = out.get("final_url") or url
        content = out.get("content") or ""
        
        browser_details_md.append(f"### Browser Node `{nid}` Details")
        browser_details_md.append(f"- **URL**: {url}")
        browser_details_md.append(f"- **Goal**: {goal}")
        browser_details_md.append(f"- **Path Chosen**: `{path.upper()}`")
        browser_details_md.append(f"- **Total Turns**: {turns}")
        browser_details_md.append(f"- **Final URL**: {final_url}")
        browser_details_md.append(f"- **Success**: `{result.success}`")
        if result.error:
            browser_details_md.append(f"- **Error**: {result.error}")
            
        # Format actions table
        if actions:
            action_rows = []
            for a in actions:
                turn = a.get("turn", 0)
                sub_acts = a.get("actions", [])
                outcome = a.get("outcome", "")
                
                act_strs = []
                for sa in sub_acts:
                    atype = sa.get("type", "")
                    if atype == "click":
                        act_strs.append(f"click(mark={sa.get('mark')})")
                    elif atype == "type":
                        act_strs.append(f"type(mark={sa.get('mark')}, value='{sa.get('value')}')")
                    elif atype == "done":
                        act_strs.append(f"done(success={sa.get('success')})")
                    else:
                        act_strs.append(f"{atype}(...)")
                
                action_rows.append(f"| {turn} | {', '.join(act_strs)} | {outcome} |")
                
            actions_table = "\n".join([
                "| Turn | Actions | Outcome |",
                "|---|---|---|",
                *action_rows
            ])
            browser_details_md.append("\n**Actions Taken:**\n" + actions_table)
            
        # Find screenshots on disk
        screenshots = []
        if browser_dir.exists():
            for png_path in sorted(browser_dir.glob("**/*.png")):
                rel_path = png_path.relative_to(session_dir)
                name = png_path.name
                parent = png_path.parent.name
                turn_str = "01"
                for part in png_path.stem.split("_"):
                    if part.isdigit():
                        turn_str = part
                        break
                screenshots.append({
                    "path": str(rel_path).replace("\\", "/"),
                    "name": name,
                    "turn": turn_str,
                    "layer": parent
                })
                
        if screenshots:
            browser_details_md.append("\n**Visual Replay Viewer (Screenshots):**")
            layers = {}
            for s in screenshots:
                layer = s["layer"]
                if layer not in layers:
                    layers[layer] = []
                layers[layer].append(s)
                
            for layer, scs in layers.items():
                browser_details_md.append(f"\n*Layer: {layer}*")
                turns_sc = {}
                for s in scs:
                    t = s["turn"]
                    if t not in turns_sc:
                        turns_sc[t] = {}
                    if "marked" in s["name"]:
                        turns_sc[t]["marked"] = s["path"]
                    else:
                        turns_sc[t]["raw"] = s["path"]
                        
                carousel_slides = []
                for t in sorted(turns_sc.keys()):
                    t_info = turns_sc[t]
                    path_to_show = t_info.get("marked") or t_info.get("raw")
                    if path_to_show:
                        slide_md = f"![Turn {t} Screenshot]({path_to_show})\n*Turn {t} - {layer.upper()}*"
                        carousel_slides.append(slide_md)
                        
                if carousel_slides:
                    carousel_content = "\n<!-- slide -->\n".join(carousel_slides)
                    browser_details_md.append(f"````carousel\n{carousel_content}\n````")
                    
        if content:
            preview = content[:2000] + ("..." if len(content) > 2000 else "")
            browser_details_md.append(f"\n**Extracted Data Preview (first 2000 chars):**\n```\n{preview}\n```")
            
    # 5. Extract Structured Comparison Table if available
    comparison_table_md = ""
    distiller_output = None
    for nid, node_attr in graph_nodes.items():
        if node_attr.get("skill") == "distiller":
            res = node_attr.get("result")
            if res and res.success and isinstance(res.output, dict):
                distiller_output = res.output
                
    if distiller_output:
        comparison_table_md = "### Extracted Structured Comparison Table\n"
        records = None
        for val in distiller_output.values():
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                records = val
                break
        if records:
            keys = list(records[0].keys())
            headers = "| " + " | ".join(keys) + " |"
            align = "| " + " | ".join(["---"] * len(keys)) + " |"
            rows = []
            for rec in records:
                row_str = "| " + " | ".join(str(rec.get(k, "")) for k in keys) + " |"
                rows.append(row_str)
            comparison_table_md += "\n".join([headers, align, *rows]) + "\n"
            
    if not comparison_table_md and parsed_output and parsed_output.get("final_answer"):
        fa = parsed_output["final_answer"]
        if "|" in fa and "\n|---" in fa:
            comparison_table_md = "### Final Comparison Table (from synthesized response)\n"
            lines = fa.split("\n")
            table_lines = [l for l in lines if l.strip().startswith("|")]
            if table_lines:
                comparison_table_md += "\n".join(table_lines) + "\n"
                
    # 6. Put everything together into the Markdown Report
    report_md = f"""# 🌌 Session Replay Viewer & Report

**Session ID**: `{session_id}`
**Original Query**: {query}
**Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}

## 1. Planner DAG
{dag_text}

## 2. Cost Ledger & Token Usage
{cost_table_md}

## 3. Browser Interaction Logs
{"No browser interaction was performed in this session." if not browser_details_md else "\n".join(browser_details_md)}

## 4. Structured Data
{comparison_table_md or "No comparison table could be automatically extracted from the distiller output."}

## 5. Final Answer
{parsed_output.get('final_answer') or "(no final answer)"}
"""

    session_dir.mkdir(parents=True, exist_ok=True)
    report_path = session_dir / "replay_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    
    # Write to artifacts directory in app data
    try:
        app_data_dir = Path("C:/Users/DELL/.gemini/antigravity/brain/b89bcd77-9a8a-4c93-82b0-3e621127f518")
        if app_data_dir.exists():
            art_browser_dir = app_data_dir / "browser"
            art_browser_dir.mkdir(parents=True, exist_ok=True)
            if browser_dir.exists():
                import shutil
                shutil.copytree(str(browser_dir), str(art_browser_dir), dirs_exist_ok=True)
            app_report_path = app_data_dir / f"replay_report_{session_id}.md"
            app_report_path.write_text(report_md, encoding="utf-8")
            print(f"[report] Wrote artifact report to {app_report_path}")
    except Exception as e:
        print(f"[report] Failed to copy artifact to app data: {e!r}")

    # 7. Print Console Report
    print(f"\n{'═' * 78}")
    print(f"🌌 SESSION REPLAY REPORT — {session_id}")
    print(f"{'═' * 78}")
    print(f"Goal: {query}")
    print(f"DAG Execution:")
    for line in dag_lines[1:-1]:
        print("  " + line)
    print(f"{'─' * 78}")
    
    if browser_nodes:
        print("Browser Cascades:")
        for nid, node_attr, result in browser_nodes:
            out = result.output or {}
            path = out.get("path")
            if not path and result.error_code == "gateway_blocked":
                path = "blocked"
            elif not path:
                path = "failed"
            print(f"  Node {nid}: URL={out.get('url')} | Path Chosen={path.upper()} | Turns={out.get('turns', 0)}")
            for a in out.get("actions", []):
                act_types = [sa.get("type", "") for sa in a.get("actions", [])]
                print(f"    Turn {a.get('turn')}: {', '.join(act_types)} -> {a.get('outcome')}")
        print(f"{'─' * 78}")
        
    print("Cost Ledger & Token Usage:")
    print(f"  Total Cost: ${total_dollars:.6f} | Total Calls: {total_calls} | Total Tokens: {total_in}/{total_out}")
    print(f"{'─' * 78}")
    
    if comparison_table_md:
        print("Structured Data / Comparison Table:")
        table_lines = [l for l in comparison_table_md.split("\n") if l.strip().startswith("|")]
        for l in table_lines:
            print("  " + l)
        print(f"{'═' * 78}\n")


# ── per-node execution ───────────────────────────────────────────────────────


async def run_skill(skill: Skill, node_id: str, graph_nodes,
                    session_id: str, query: str,
                    failure_report: str | None,
                    *, memory_hits: list | None = None) -> tuple[AgentResult, str]:
    """Dispatch one node. Returns (result, rendered_prompt).

    `memory_hits` is the FAISS-ranked MemoryItem list captured once at
    session start by Executor.run and threaded through here so every
    skill's prompt can see the same hits. This is the S7 promise carried
    forward — Memory works in S8 because the orchestrator delivers the
    hits, not just because the FAISS index is on disk.

    sandbox_executor bypasses the gateway: it picks the `code` field out of
    its upstream coder node and runs sandbox.run_python directly. All other
    skills are LLM-backed and route through the V8 gateway with
    agent=<skill_name> so agent_routing.yaml + cost-by-agent kick in."""
    resolved = resolve_inputs(graph_nodes[node_id]["inputs"], graph_nodes, query)
    # Per-node sub-question from the Planner's `metadata.question`. Travels
    # into the rendered prompt as a QUESTION: block so a fan-out worker
    # (e.g. one of three researchers spawned to cover three cities) can
    # see *its* slice of the user's request even when USER_QUERY is not
    # in its inputs.
    node_meta = graph_nodes[node_id].get("metadata") or {}
    question = node_meta.get("question") if isinstance(node_meta, dict) else None
    rendered = render_prompt(skill, query, resolved, failure_report,
                             memory_hits=memory_hits, question=question)
    started = time.time()

    if skill.name == "sandbox_executor":
        code = ""
        for r in resolved:
            if r.get("kind") == "upstream" and isinstance(r.get("output"), dict):
                code = r["output"].get("code") or code
        if not code:
            return AgentResult(
                success=False, agent_name=skill.name,
                error="no code in upstream coder output",
                elapsed_s=time.time() - started,
            ), rendered
        from sandbox import run_python
        out = run_python(code)
        return AgentResult(
            success=(out["exit_code"] == 0 and not out["timed_out"]),
            agent_name=skill.name, output=out,
            elapsed_s=time.time() - started,
        ), rendered

    if skill.name == "browser":
        # Same shape as sandbox_executor: the Browser skill owns its own
        # cascade (extract → deterministic → a11y → vision) and never
        # touches the LLM tool/text channel — so we bypass render_prompt
        # and the gateway-chat dispatch entirely and hand off to
        # BrowserSkill.run(NodeSpec).
        node_dict = graph_nodes[node_id]
        node_spec = NodeSpec(
            skill="browser",
            inputs=node_dict.get("inputs") or [],
            metadata=node_dict.get("metadata") or {},
        )
        from browser.skill import BrowserSkill
        sk = BrowserSkill(
            artifacts_root=str(ROOT / "state" / "sessions" / session_id / "browser"),
            session=session_id,
        )
        result = await sk.run(node_spec)
        if not result.elapsed_s:
            result.elapsed_s = time.time() - started
        return result, rendered

    if skill.name == "computer":
        node_dict = graph_nodes[node_id]
        node_spec = NodeSpec(
            skill="computer",
            inputs=node_dict.get("inputs") or [],
            metadata=node_dict.get("metadata") or {},
        )
        from cua_skill import ComputerSkill
        sk = ComputerSkill(
            artifacts_root=str(ROOT / "state" / "sessions" / session_id / "computer"),
            session=session_id,
        )
        result = await sk.run(node_spec)
        if not result.elapsed_s:
            result.elapsed_s = time.time() - started
        return result, rendered

    tools = tool_payload(skill.tools_allowed)
    if tools:
        # Multi-turn tool-use loop. mcp_runner opens one MCP stdio session
        # per skill invocation, dispatches each tool_call the model emits,
        # and feeds the results back until the model produces final text.
        from mcp_runner import run_with_tools
        reply = await run_with_tools(
            prompt=rendered,
            tools_payload=tools,
            agent=skill.name,
            session_id=session_id,
            provider_pin=skill.provider_pin,
            max_tokens=skill.max_tokens,
            temperature=skill.temperature,
        )
    else:
        reply = await asyncio.to_thread(
            LLM().chat,
            prompt=rendered,
            agent=skill.name,
            session=session_id,
            provider=skill.provider_pin,
            max_tokens=skill.max_tokens,
            temperature=skill.temperature,
        )
    parsed = parse_skill_json(reply.get("text", ""))

    if skill.name == "formatter":
        try:
            await generate_replay_report(session_id, query, graph_nodes, parsed)
        except Exception as report_err:
            import traceback
            print(f"[skills] Failed to generate replay report: {report_err!r}")
            traceback.print_exc()

    # Lift orchestrator-recognised fields out of the skill's JSON.
    # NOTES_RUNS feedback P0 #1: malformed successors used to be silently
    # dropped, which left students chasing "missing node" bugs for an hour.
    # Now: log the offending JSON + the validation error, then fail the
    # node so the failure path (and replay) surfaces it.
    raw_successors = parsed.pop("successors", []) or []
    successors: list[NodeSpec] = []
    rejected: list[str] = []
    for s in raw_successors:
        try:
            successors.append(NodeSpec.model_validate(s))
        except ValidationError as ve:
            rejected.append(f"successor={s!r}  error={ve}")
    if skill.name == "planner":
        for s in parsed.get("nodes", []) or []:
            try:
                successors.append(NodeSpec.model_validate(s))
            except ValidationError as ve:
                rejected.append(f"node={s!r}  error={ve}")

    if rejected:
        err = (
            f"{skill.name}: {len(rejected)} malformed NodeSpec(s) emitted.\n"
            + "\n".join(f"  - {line}" for line in rejected)
        )
        print(f"[skills] {err}")
        return AgentResult(
            success=False, agent_name=skill.name,
            output=parsed, successors=successors,
            elapsed_s=time.time() - started,
            provider=reply.get("provider", ""),
            error=err,
        ), rendered

    return AgentResult(
        success=True,
        agent_name=skill.name,
        output=parsed,
        successors=successors,
        elapsed_s=time.time() - started,
        provider=reply.get("provider", ""),
    ), rendered
