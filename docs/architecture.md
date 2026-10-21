# Architecture

```
                 ┌──────────────┐
   user input ──▶│  CLI / REPL  │  ui/cli.py · ui/repl.py · ui/web.py
                 └──────┬───────┘
                        │
                 ┌──────▼───────┐
                 │    Agent     │  agent.py — think → tool → observe
                 └──┬───┬───┬──┘
        ┌───────────┘   │   └────────────┐
┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│  ContextWindow│ │ ToolRegistry│ │  EventBus   │
│  context.py   │ │  tools.py   │ │transparency.│
└───────┬───────┘ └──────┬──────┘ └──────┬──────┘
        │                │               │
┌───────▼──────┐ ┌───────▼───────┐ ┌─────▼──────┐
│  RAG / Reuse │ │  Execution    │ │ AuditLog   │
│ rag.py       │ │  execution.py │ │ audit_log.py│
│ reuse.py     │ │  security.py  │ └────────────┘
└──────────────┘ └───────┬───────┘
                         │
              ┌──────────▼──────────┐
              │ SandboxIsolator     │  rlimits · scrubbed env · workspace cwd
              └─────────────────────┘
```

## Layers

| Layer | Modules | Responsibility |
|---|---|---|
| **Interface** | `cli.py`, `ui/repl.py`, `ui/web.py`, `ui/tui.py` | Parsing, rendering, live transparency, auth |
| **Orchestration** | `agent.py`, `orchestration.py`, `delegation.py`, `coding_agent.py`, `tdd.py`, `strategies.py`, `small_model_booster.py` | Control flow: loops, plans, sub-agents, task strategies |
| **Context** | `context.py`, `context_optimization.py`, `context_pruning.py`, `prompt_optimization.py`, `rag.py`, `reuse.py` | Token economy: budgeting, compression, retrieval, anti-reinvention |
| **Capability** | `tools.py`, `capabilities.py`, `execution.py`, `git_tools.py`, `lsp_tool.py`, `browser.py`, `mcp_client.py`, `tool_synthesis.py` | What the agent can do |
| **Models** | `llm.py`, `models.py`, `models_ini.py`, `hf_download.py`, `optimize.py`, `providers/` | Talking to models, local inference, catalogue, teaming |
| **Policy & state** | `config.py`, `security.py`, `audit_log.py`, `logging_setup.py`, `memory.py`, `skills.py`, `skill_catalogue.py`, `mcp_catalogue.py`, `hooks/` | Configuration, safety, persistence, triggers |
| **Ops** | `bootstrap.py`, `bootstrap_install.py`, `transparency.py` | Wiring, environment setup, observability |

## Request flow (single turn)

1. **Interface** hands a goal to `Agent.run`.
2. **Hook engine** (`hooks/matching.py`) scores the goal against trigger specs.
   Matches drive `HookExecutor` actions: preload tools, inject context, switch profile,
   run background work. Preloaded tools also **scope** the tool list sent to the model,
   which is the main token saving.
3. **Context assembly**: `ContextWindow` returns a budget-bounded message list;
   `SlidingWindowCompressor` trims it; the reuse advisor injects existing code.
4. **Provider call** (`llm.py`): pooled HTTP client, optional streaming
   (`llm_delta` events), retry/backoff and response cache via `inference.py`.
5. **Tool execution**: `ToolRegistry` validates arguments, then runs the tool.
   Execution tools run inside `SandboxIsolator` by default.
   Tool calls in one turn execute **in parallel**.
6. **Observation** is appended to the context; the loop repeats until the model
   answers or the iteration cap is hit.
7. **Transparency**: every step emits an `Event`; the REPL renders them live and
   `TranscriptWriter` writes a redacted markdown transcript.

## Cross-cutting invariants

| Invariant | Enforced by |
|---|---|
| The model only sees tools that are relevant | `Agent.active_tools` set by hook preloads |
| The context never exceeds its token budget | `ContextWindow._maybe_compress` |
| File access stays inside the workspace | `security.safe_path` |
| Shell commands pass an allowlist | `security.CommandPolicy` |
| Untrusted skill names cannot escape the skills dir | `skills.sanitize_name` |
| Dynamic code cannot reach `open`/`__import__` | `ToolSynthesizer._safe_builtins` |
| Secrets never reach the log or transcript | `audit_log.redact` / `redact_mapping` |
| Every tool call is attributable | `AuditLog` correlation IDs + `EventBus` |

## Extension points

| To add… | Do this |
|---|---|
| A tool | `register_tool(registry, name, fn, description, parameters=[...])` |
| A provider | subclass `ProviderSpec` in `providers/registry.py`, or point `base_url` at any OpenAI-compatible server |
| A skill | drop a markdown file with front-matter in the skills directory |
| A trigger hook | add a YAML file to `princesse/hooks/builtin/` |
| A model | add it to the catalogue (models.dev) or configure it in `models.ini` |
| An MCP server | `princesse` → search the registry, then connect via `MCPRegistry` |
