# Session 9 — LLM Gateway V9 + Agent Orchestrator

A multi-provider LLM gateway with auto-routing, embedding, vision/multimodal support, and an agent orchestrator that chains cognitive layers (Perception → Memory → Decision → Action) into executable DAGs.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    S9SharedCode / code/                      │
│  (Agent Orchestrator — flow.py, perception, memory, etc.)   │
│                                                             │
│  flow.py → planner → [researcher|browser|...] → formatter   │
│              ↕ critic (auto-inserted for distiller skills)  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP /v1/chat
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    llm_gatewayV9/                            │
│  (LLM Gateway — FastAPI, port 8109)                         │
│                                                             │
│  /v1/chat     — chat completion with 7 providers            │
│  /v1/embed    — text embedding (Ollama → Gemini failover)   │
│  /v1/vision   — single-image vision call                    │
│  /v1/chat/batch — batch dispatch with bounded parallelism   │
│  /v1/cost/by_agent — per-skill cost rollup                  │
│  /v1/routers  — router pool status                          │
│  /v1/providers, /v1/capabilities, /v1/status, /v1/calls    │
│  / (dashboard), /help                                       │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start the Gateway

```bash
cd llm_gatewayV9
uv run python main.py
# Gateway starts on port 8109 (configurable via GATEWAY_V9_PORT)
```

Requires a `.env` file in the parent directory, `llm_gatewayV9/.env`, or `S9SharedCode/code/.env` with provider API keys:

```bash
GEMINI_API_KEY=...
NVIDIA_API_KEY=...
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
OPEN_ROUTER_API_KEY=...
GITHUB_ACCESS_TOKEN=...
OLLAMA_MODEL=gemma4:31b
```

### 2. Run the Demo Suite

```bash
cd S9SharedCode
./run_demo.sh          # pytest + 5 canonical queries
./run_demo.sh browser  # Browser skill end-to-end
./run_demo.sh wipe     # Clear state/sessions + logs
```

## Gateway Features (V9)

### Provider Pool — 7 Workers

| Shortcut | Provider     | Default Model                    | Free Tier (RPM / RPD) |
|----------|-------------|----------------------------------|-----------------------|
| `o`      | Ollama      | env-controlled (local)           | unlimited             |
| `g`      | Gemini      | `gemini-2.5-flash`               | 15 / 1,000            |
| `n`      | NVIDIA NIM  | `deepseek-ai/deepseek-v3.2`      | 40 / —                |
| `gr`     | Groq        | `openai/gpt-oss-120b`            | 30 / 1,000            |
| `c`      | Cerebras    | `zai-glm-4.7`                    | 30 / —                |
| `or`     | OpenRouter  | `nvidia/nemotron-3-super-120b-a12b:free` | 20 / 50    |
| `gh`     | GitHub      | `openai/gpt-4.1-mini`            | 10–15 / 50–150        |

### Auto-Routing (V3+)

The gateway classifies each request into a tier using a small router LLM:

| Tier   | Token Range | Worker Order |
|--------|------------|-------------|
| TINY   | < 1,000    | github → openrouter → groq → nvidia → cerebras → gemini → ollama |
| LARGE  | 1,000–8,000 | gemini → groq → nvidia → cerebras → github → openrouter → ollama |
| HUGE   | > 8,000    | 503 — use Summarizer Agent or chunk input |

Router pool: cerebras → groq → nvidia → github (failover ring).

### Agent Routing (V8)

`agent_routing.yaml` maps skill names to preferred providers:

```yaml
planner: gemini
researcher: gemini
critic: groq
coder: gemini
browser: gemini
retriever: github
```

### Embedding (V7+)

`POST /v1/embed` — failover ring: Ollama (`nomic-embed-text`, 768-dim) → Gemini (`gemini-embedding-001`, sliced to 768-dim). Inputs over 8,000 chars are rejected with 413.

### Vision / Multimodal (V9)

`POST /v1/vision` — single-image vision call. Accepts `data:` or `http(s)` URLs (pre-resolved to `data:` centrally). Routes to vision-capable providers only.

### Batch Dispatch (V8)

`POST /v1/chat/batch` — submit N requests in one round-trip. Gateway manages bounded parallelism so provider rate limits are respected centrally.

### Cost Tracking (V8+)

`GET /v1/cost/by_agent` — per-skill token and USD cost rollup. Scoped by `?session=<sid>` for flow-run-level granularity.

## Agent Orchestrator (S9SharedCode)

The orchestrator (`flow.py`) builds and executes a DAG for each user query:

1. **Planner** — decides which skills to invoke and in what order
2. **Researcher** — gathers information (parallel fan-out per question)
3. **Distiller** — synthesises research into structured output
4. **Critic** — auto-inserted for distiller skills; judges output against the original query
5. **Formatter** — produces the final answer
6. **Browser** — end-to-end web browsing via Playwright (extract → deterministic → a11y → vision cascade)

### Demo Queries

| Query | Shape | What It Demonstrates |
|-------|-------|---------------------|
| `hello` | planner → formatter | Smallest possible DAG |
| `shannon` | planner → researcher → formatter | Single-item research |
| `populations` | planner → researcher ×3 → formatter | Parallel fan-out with per-worker scoping |
| `structured` | planner → researcher → distiller → critic → formatter | Critic auto-insertion |
| `fail` | planner → formatter | Graceful fail-by-planning |
| `browser` | planner → browser → formatter | Browser skill end-to-end |

## Project Structure

```
session_9/
├── README.md                          ← this file
├── llm_gatewayV9/                     ← LLM Gateway (FastAPI, port 8109)
│   ├── main.py                        — FastAPI app, routes, routing logic
│   ├── providers.py                   — 7 provider adapters + router providers
│   ├── router.py                      — Router (worker pool) + RouterPool
│   ├── schemas.py                     — Pydantic v2 request/response models
│   ├── embedders.py                   — Ollama + Gemini embedding providers
│   ├── db.py                          — SQLite call logging
│   ├── cache.py                       — Gemini prompt cache
│   ├── client.py                      — Python SDK
│   ├── pricing.py                     — USD cost estimation
│   ├── agent_routing.yaml             — Agent → provider pinning
│   ├── pyproject.toml                 — Project metadata + dependencies
│   ├── requirements.txt               — pip dependencies
│   ├── run.sh                         — Quick-start script
│   ├── static/
│   │   ├── dashboard.html             — Live dashboard
│   │   └── help.html                  — Help page
│   └── tests/
│       ├── test_all_providers.py      — Provider matrix tests
│       ├── test_embed.py              — Embedding tests
│       ├── test_vision_endpoint.py    — Vision endpoint tests
│       └── test_vision_smoke.py       — Vision smoke tests
├── S9SharedCode/                      ← Agent orchestrator
│   ├── run_demo.sh                    — Demo runner
│   ├── code/
│   │   ├── flow.py                    — Orchestrator DAG executor
│   │   ├── perception.py              — Perception layer
│   │   ├── memory.py                  — Memory layer (FAISS vector index)
│   │   ├── decision.py                — Decision layer
│   │   ├── action.py                  — Action layer
│   │   ├── skills.py                  — Skill definitions
│   │   ├── schemas.py                 — Orchestrator Pydantic models
│   │   ├── gateway.py                 — Gateway client wrapper
│   │   ├── artifacts.py               — Artifact management
│   │   ├── sandbox.py                 — Sandbox executor
│   │   ├── recovery.py                — Recovery/retry logic
│   │   ├── replay.py                  — Session replay
│   │   ├── persistence.py             — State persistence
│   │   ├── mcp_server.py              — MCP server
│   │   ├── mcp_runner.py              — MCP runner
│   │   ├── vector_index.py            — FAISS vector index
│   │   ├── agent_config.yaml          — Agent configuration
│   │   ├── agent7_s7_carryover.py     — S7 carryover agent
│   │   ├── VALIDATION.md              — Validation documentation
│   │   ├── pyproject.toml             — Project metadata
│   │   ├── requirements.txt           — pip dependencies
│   │   ├── browser/                   — Browser skill (Playwright)
│   │   ├── prompts/                   — Prompt templates
│   │   └── tests/                     — Orchestrator tests
│   ├── logs/                          — Demo logs
│   └── state/                         — Session state + FAISS index
```

## Key Design Principles

1. **Separation of concerns** — The router LLM never sees the worker's system prompt, tools, schema, or earlier turns. It receives only a token estimate and a content sample.
2. **Honest failure** — The gateway returns clear error codes (413 for oversized input, 503 when all providers unavailable, 429 for rate limits) rather than silently degrading.
3. **Free-tier reality** — Rate limits, cooldowns, and backoff are first-class design elements, not afterthoughts.
4. **Observability** — Every call is logged to SQLite with role markers, router decisions, and cost data. The dashboard shows worker and router pools side-by-side.

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Ollama (optional, for local models)
- Playwright (optional, for Browser skill)
- Provider API keys (see `.env` setup above)