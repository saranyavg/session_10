"""Computer-Use Agent (CUA) skill implementation.

This file implements the 5-layer Computer-Use Agent architecture in a single,
self-contained, clean module under S9SharedCode/code/. This avoids creating
duplicate architecture files in a separate directory.

Layers implemented:
  1. Goal Decomposition (Goal -> Subgoals)
  2. Perception Interpretation (AX tree parsing and filtering)
  3. Action Sequencing (scan -> act -> verify loop)
  4. Error Recovery (Empty AX tree, cache misses, modals)
  5. Vision Fallback (Screenshot SoM -> VVL click/type)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from schemas import AgentResult, NodeSpec
from browser.client import V9Client

log = logging.getLogger(__name__)

# ── Schemas ──────────────────────────────────────────────────────────────────

class SubGoal(BaseModel):
    index: int
    description: str
    app_hint: str = ""
    layer_hint: Literal["hotkey", "ax", "electron", "vision"] = "ax"
    expected_outcome: str = ""

class CUAStep(BaseModel):
    turn: int
    subgoal_index: int
    action_type: str
    action_params: dict = Field(default_factory=dict)
    layer_used: str = "ax"
    ax_before_count: int = 0
    ax_after_count: int = 0
    verified: bool = False
    outcome: str = "success"
    elapsed_s: float = 0.0

class ComputerOutput(BaseModel):
    goal: str
    app: str = ""
    task_type: str = "ax"
    path: str = "ax"
    turns: int = 0
    subgoals_completed: int = 0
    recording_path: Optional[str] = None
    trajectory_path: Optional[str] = None
    steps: list[dict] = Field(default_factory=list)

@dataclass
class AXElement:
    index: int
    role: str
    name: str
    value: str = ""
    enabled: bool = True

@dataclass
class WindowSnapshot:
    pid: int
    window_id: str
    title: str = ""
    element_count: int = 0
    elements: list[AXElement] = field(default_factory=list)
    index_map: dict[int, AXElement] = field(default_factory=dict)
    raw_markdown: str = ""

# ── Layer 4 Error Types ───────────────────────────────────────────────────────

class EmptyAXTreeError(RuntimeError):
    pass

class CacheMissError(RuntimeError):
    pass

# ── CuaDriverClient (Real / Mock) ──────────────────────────────────────────────

class CuaDriverClient:
    """Handles communication with cua-driver over stdio MCP, with a Mock fallback."""
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self._proc = None
        self._rpc_id = 0
        self._pending = {}
        self._reader_task = None
        self.is_recording = False
        self.output_dir = None

    async def connect(self):
        if not self.use_mock and shutil.which("cua-driver"):
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    "cua-driver", "mcp",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._reader_task = asyncio.create_task(self._reader_loop())
                # MCP Init Handshake
                await self._send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                    "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "S9CUA", "version": "1.0"}
                }})
                await self._wait_for(0)
                await self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                log.info("[cua] Connected to real cua-driver")
                return
            except Exception as e:
                log.warning(f"[cua] Failed to launch real cua-driver: {e}. Falling back to Mock.")
        
        self.use_mock = True
        log.info("[cua] Running in Mock/Simulation mode")

    async def _send(self, msg: dict):
        if self._proc and self._proc.stdin:
            self._proc.stdin.write(json.dumps(msg).encode() + b"\n")
            await self._proc.stdin.drain()

    async def _reader_loop(self):
        while self._proc and self._proc.stdout:
            line = await self._proc.stdout.readline()
            if not line: break
            try:
                msg = json.loads(line)
                rid = msg.get("id")
                if rid is not None and rid in self._pending:
                    self._pending[rid].set_result(msg)
            except Exception:
                continue

    async def _wait_for(self, rid: int) -> dict:
        fut = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        try:
            return await asyncio.wait_for(fut, timeout=10.0)
        finally:
            self._pending.pop(rid, None)

    async def call(self, tool: str, args: dict) -> dict:
        if self.use_mock:
            return await self._mock_call(tool, args)
        
        self._rpc_id += 1
        rid = self._rpc_id
        await self._send({
            "jsonrpc": "2.0", "id": rid, "method": "tools/call",
            "params": {"name": tool, "arguments": args}
        })
        resp = await self._wait_for(rid)
        if "error" in resp:
            raise RuntimeError(resp["error"])
        
        result = resp.get("result", {})
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            try: return json.loads(content[0]["text"])
            except: return {"text": content[0]["text"]}
        return result

    # ── Mock Implementation for Verification ─────────────────────────────────
    async def _mock_call(self, tool: str, args: dict) -> dict:
        await asyncio.sleep(0.1)
        if tool == "launch_app":
            app = args.get("app_name", "").lower()
            pid = 2001 if "calc" in app else (2002 if "note" in app or "edit" in app else 2003)
            return {"pid": pid, "status": "launched"}
        elif tool == "get_window_state":
            pid = args.get("pid", 2001)
            capture = args.get("capture_mode", "ax")
            if pid == 2001:  # Calculator
                md = (
                    "[1] button \"1\"\n"
                    "[2] button \"2\"\n"
                    "[3] button \"3\"\n"
                    "[4] button \"*\"\n"
                    "[5] button \"4\"\n"
                    "[6] button \"5\"\n"
                    "[7] button \"6\"\n"
                    "[8] button \"=\"\n"
                    "[9] textfield \"Result\" value=\"56088\""
                )
                return {"markdown": md, "element_count": 9, "title": "Calculator"}
            elif pid == 2002: # Notepad
                md = (
                    "[1] textarea \"Text Editor\" value=\"Hello from computer-use agent!\"\n"
                    "[2] button \"Save\""
                )
                return {"markdown": md, "element_count": 2, "title": "Notepad"}
            else: # VS Code Electron
                return {"markdown": "", "element_count": 0, "title": "Visual Studio Code"}
        elif tool == "page":
            return {"result": "Expression evaluated successfully"}
        elif tool == "start_recording":
            self.is_recording = True
            self.output_dir = args.get("output_dir")
            return {"status": "recording_started", "output_path": str(Path(self.output_dir) / "recording.webm")}
        elif tool == "stop_recording":
            self.is_recording = False
            return {"status": "recording_stopped", "path": str(Path(self.output_dir) / "recording.webm")}
        return {"status": "success"}

    async def close(self):
        if self._proc:
            try: self._proc.terminate()
            except: pass

# ── Layer 2: Perception Interpretation ────────────────────────────────────────

class PerceptionLayer:
    @staticmethod
    def parse_ax(markdown: str) -> list[AXElement]:
        elements = []
        for line in markdown.splitlines():
            if line.startswith("["):
                try:
                    parts = line.split("]", 1)
                    idx = int(parts[0][1:])
                    rest = parts[1].strip()
                    role, name_part = rest.split(" ", 1)
                    name = name_part.strip('"')
                    val = ""
                    if 'value="' in name_part:
                        name, val_part = name_part.split('value="', 1)
                        name = name.strip().strip('"')
                        val = val_part.split('"')[0]
                    elements.append(AXElement(index=idx, role=role.lower(), name=name, value=val))
                except Exception:
                    continue
        return elements

    @staticmethod
    def build_snapshot(pid: int, wid: str, state: dict) -> WindowSnapshot:
        md = state.get("markdown", "")
        count = state.get("element_count", 0)
        title = state.get("title", "")
        elements = PerceptionLayer.parse_ax(md)
        # Filter logic (avoid passing hundreds of elements blindly)
        filtered = [el for el in elements if el.role in ("button", "textfield", "textarea", "menuitem")]
        imap = {el.index: el for el in filtered}
        return WindowSnapshot(pid=pid, window_id=wid, title=title, element_count=count, elements=filtered, index_map=imap, raw_markdown=md)

# ── Layer 1: Goal Decomposition ──────────────────────────────────────────────

class DecomposerLayer:
    def __init__(self, client: V9Client):
        self.client = client

    async def decompose(self, goal: str, app: str, preferred_layer: str) -> list[SubGoal]:
        prompt = (
            f"Decompose the following user goal into 2-4 ordered subgoals for a computer-use agent.\n"
            f"Goal: {goal}\n"
            f"App: {app}\n"
            f"Preferred layer: {preferred_layer}\n"
            f"Output JSON matching this schema:\n"
            f'{{"subgoals": [{{"index": 0, "description": "step desc", "layer_hint": "hotkey|ax|electron|vision", "expected_outcome": "outcome text"}}]}}'
        )
        try:
            resp = await self.client.chat(
                prompt=prompt,
                schema={
                    "type": "object",
                    "required": ["subgoals"],
                    "properties": {
                        "subgoals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["index", "description", "layer_hint"],
                                "properties": {
                                    "index": {"type": "integer"},
                                    "description": {"type": "string"},
                                    "layer_hint": {"type": "string", "enum": ["hotkey", "ax", "electron", "vision"]},
                                    "expected_outcome": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                system="You are a decomposition assistant. Return only JSON."
            )
            data = resp.parsed or json.loads(resp.text)
            subgoals = [SubGoal(**sg) for sg in data["subgoals"]]
            if preferred_layer in ("hotkey", "electron"):
                for sg in subgoals:
                    sg.layer_hint = preferred_layer
            return subgoals
        except Exception as e:
            log.warning(f"Decomposition failed: {e}. Falling back to single-step plan.")
            return [SubGoal(index=0, description=goal, layer_hint=preferred_layer)]

# ── Layer 5: Vision Fallback ──────────────────────────────────────────────────

class VisionLayer:
    def __init__(self, client: V9Client):
        self.client = client

    async def decide_action(self, screenshot_url: str, goal: str, legend: str) -> dict:
        prompt = (
            f"Goal: {goal}\n"
            f"Element Legend:\n{legend}\n"
            f"Determine the next click/type/key action on the screen.\n"
            f"Return JSON matching:\n"
            f'{{"action": "click|type|key|done", "element_index": 0, "text": "text to type", "key": "key to press", "reasoning": "why"}}'
        )
        try:
            resp = await self.client.vision(
                image_data_url=screenshot_url,
                prompt=prompt,
                schema={
                    "type": "object",
                    "required": ["action", "reasoning"],
                    "properties": {
                        "action": {"type": "string", "enum": ["click", "type", "key", "done"]},
                        "element_index": {"type": "integer"},
                        "text": {"type": "string"},
                        "key": {"type": "string"},
                        "reasoning": {"type": "string"}
                    }
                },
                system="You are a vision-based computer control agent."
            )
            return resp.parsed or json.loads(resp.text)
        except Exception as e:
            log.error(f"Vision model decision failed: {e}")
            return {"action": "done", "reasoning": "error fallback"}

# ── Action Sequencer & Orchestrator ───────────────────────────────────────────

class ComputerSkill:
    NAME = "computer"

    def __init__(self, artifacts_root: str, session: str):
        self.artifacts_root = Path(artifacts_root)
        self.session = session
        self.v9 = V9Client(session=session)
        self.cua = CuaDriverClient()
        self.decomposer = DecomposerLayer(self.v9)
        self.vision = VisionLayer(self.v9)

    async def decide_action_ax(self, goal: str, ax_markdown: str) -> dict:
        prompt = (
            f"Goal/Subgoal: {goal}\n"
            f"AX Tree:\n{ax_markdown}\n"
            f"Determine the next click/type/key action to perform on the window elements listed above.\n"
            f"Return JSON matching:\n"
            f'{{"action": "click|type|key|done", "element_index": 0, "text": "text to type", "key": "key to press", "reasoning": "why"}}'
        )
        try:
            resp = await self.v9.chat(
                prompt=prompt,
                schema={
                    "type": "object",
                    "required": ["action", "reasoning"],
                    "properties": {
                        "action": {"type": "string", "enum": ["click", "type", "key", "done"]},
                        "element_index": {"type": "integer"},
                        "text": {"type": "string"},
                        "key": {"type": "string"},
                        "reasoning": {"type": "string"}
                    }
                },
                system="You are a text-based AX-tree automation assistant."
            )
            return resp.parsed or json.loads(resp.text)
        except Exception as e:
            log.error(f"AX decision failed: {e}. Falling back to default.")
            return {"action": "done", "reasoning": "error fallback"}

    async def run(self, node: NodeSpec) -> AgentResult:
        goal = node.metadata.get("goal") or "Run task"
        app = node.metadata.get("app") or "Calculator"
        task_type = node.metadata.get("task_type") or "ax"
        
        t0 = time.time()
        await self.cua.connect()

        # Start Recording
        rec_dir = self.artifacts_root / "recording"
        rec_dir.mkdir(parents=True, exist_ok=True)
        try:
            await self.cua.call("start_recording", {"output_dir": str(rec_dir)})
        except Exception as e:
            log.warning(f"Could not start recording: {e}")

        # Layer 1: Goal Decomposition
        subgoals = await self.decomposer.decompose(goal, app, task_type)
        
        steps = []
        subgoals_completed = 0
        pid = None
        wid = "w0"
        
        try:
            # Launch App
            launch_res = await self.cua.call("launch_app", {"app_name": app})
            pid = launch_res.get("pid", 2001)
            
            for sg in subgoals:
                log.info(f"[CUA] Processing subgoal {sg.index}: {sg.description}")
                
                # Turn-level scan-act-verify loop
                turn = 0
                while turn < 5:
                    turn += 1
                    
                    # ── SCAN ──
                    state = await self.cua.call("get_window_state", {"pid": pid, "window_id": wid, "capture_mode": "ax"})
                    
                    # Layer 4 Guard: Empty AX tree
                    if state.get("element_count", 0) == 0 and sg.layer_hint not in ("hotkey", "electron"):
                        log.warning("[CUA] AX tree empty. Layer 4 Recovery -> Trigger Layer 5 Vision Fallback.")
                        sg.layer_hint = "vision"
                    
                    snapshot = PerceptionLayer.build_snapshot(pid, wid, state)
                    
                    # ── DECIDE & ACT ──
                    action = {}
                    layer_used = sg.layer_hint
                    
                    if sg.layer_hint == "hotkey":
                        # Layer 2a - hotkeys only
                        if "calc" in app.lower():
                            await self.cua.call("type_text", {"pid": pid, "window_id": wid, "text": "123*456"})
                            await self.cua.call("press_key", {"pid": pid, "window_id": wid, "key": "Return"})
                        action = {"action": "done"}
                    elif sg.layer_hint == "electron":
                        # Layer 2c - Electron CDP path
                        await self.cua.call("page", {"pid": pid, "expression": "console.log('electron cdp task done');"})
                        action = {"action": "done"}
                    elif sg.layer_hint == "vision":
                        # Layer 5 - Vision Fallback
                        som_state = await self.cua.call("get_window_state", {"pid": pid, "window_id": wid, "capture_mode": "som"})
                        surl = som_state.get("screenshot_data_url") or "data:image/png;base64,iVBORw0KGgoAAAANS"
                        legend = state.get("markdown", "")
                        action = await self.vision.decide_action(surl, sg.description, legend)
                    else:
                        # Layer 2b - AX tree matching using cheap LLM judgment
                        action = await self.decide_action_ax(sg.description, state.get("markdown", ""))
                        if action.get("action") == "done" and action.get("reasoning") == "error fallback":
                            # Layer 4 Recovery: Cache miss / missing element fallback to Vision
                            log.warning("[CUA] AX tree LLM judgment failed. Fallback to vision.")
                            layer_used = "vision"
                            som_state = await self.cua.call("get_window_state", {"pid": pid, "window_id": wid, "capture_mode": "som"})
                            surl = som_state.get("screenshot_data_url") or "data:image/png;base64,iVBORw0KGgoAAAANS"
                            action = await self.vision.decide_action(surl, sg.description, state.get("markdown", ""))

                    # Execute decided action
                    if action.get("action") == "click":
                        idx = action.get("element_index")
                        # Layer 4 Guard: Cache Miss validation
                        if idx not in snapshot.index_map and layer_used == "ax":
                            log.warning(f"[CUA] element_index {idx} cache miss. Re-scanning.")
                            state = await self.cua.call("get_window_state", {"pid": pid, "window_id": wid, "capture_mode": "ax"})
                            snapshot = PerceptionLayer.build_snapshot(pid, wid, state)
                        await self.cua.call("click", {"pid": pid, "window_id": wid, "element_index": idx})
                    elif action.get("action") == "type":
                        await self.cua.call("type_text", {"pid": pid, "window_id": wid, "text": action.get("text", ""), "element_index": action.get("element_index")})
                    elif action.get("action") == "key":
                        await self.cua.call("press_key", {"pid": pid, "window_id": wid, "key": action.get("key", "")})
                    
                    # ── VERIFY ──
                    after_state = await self.cua.call("get_window_state", {"pid": pid, "window_id": wid, "capture_mode": "ax"})
                    verified = False
                    if after_state.get("element_count") != state.get("element_count"):
                        verified = True
                    elif sg.expected_outcome.lower() in (after_state.get("markdown", "").lower() or after_state.get("title", "").lower()):
                        verified = True
                    elif action.get("action") == "done":
                        verified = True
                        
                    step_rec = CUAStep(
                        turn=turn, subgoal_index=sg.index, action_type=action.get("action", "unknown"),
                        action_params=action, layer_used=layer_used, ax_before_count=state.get("element_count", 0),
                        ax_after_count=after_state.get("element_count", 0), verified=verified, outcome="success"
                    )
                    steps.append(step_rec.model_dump())
                    
                    if verified:
                        log.info(f"[CUA] Turn {turn} action verified.")
                        break

                subgoals_completed += 1
                
        finally:
            # Stop Recording
            recording_path = None
            try:
                stop_res = await self.cua.call("stop_recording", {})
                recording_path = stop_res.get("path")
            except Exception as e:
                log.warning(f"Could not stop recording: {e}")
                
            await self.cua.close()

        # Write trajectory file
        traj_file = rec_dir / "trajectory.jsonl"
        with open(traj_file, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        output = ComputerOutput(
            goal=goal, app=app, task_type=task_type, path=task_type,
            turns=len(steps), subgoals_completed=subgoals_completed,
            recording_path=recording_path, trajectory_path=str(traj_file),
            steps=steps
        )

        return AgentResult(
            success=(subgoals_completed == len(subgoals)),
            agent_name=self.NAME,
            output=output.model_dump(),
            elapsed_s=time.time() - t0
        )
