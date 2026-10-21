# Distillation Spec — princesse (combined agent runtime)

## References

| Repo | Revision (SHA) | Tag/branch |
|---|---|---|
| agent0ai/agent-zero | ff2a5b9c9c4e490ba38dd7c313e779510bb2071a | v2.14 |
| NousResearch/hermes-agent | 3ab0930318ad970b4ec102838f75f62973e188ec | main |
| FoundationAgents/OpenManus | 3309bf4e416fb1c74b008f3e86494439a31bad53 | main |
| scratchhax/model-loader | 1c3032b96efe980ecb50f06659b5cb34e12704c0 | main |
| jir88/llama-optim | fa1241df7d2c21e031175d8272bf002e0320ef77 | main |
| SlutPrincesse/slutt (kilo/atomic-harbor-2w8) | 6925bac2ad3f8d6cb5380f3e4429cfd0eb324ace | kilo/atomic-harbor-2w8 |

Target: greenfield project `/root/projects/princesse`, Python 3.11+.

## Coverage

### Ported (core)
1. **Context window with hierarchical summarization** (slutt `agent_system_v9/context/*`): `ContextWindow`, `HierarchicalSummarizer`, token estimation, verbatim tail + rolling summary, budget-bounded `get_messages_for_model`.
2. **Dynamic tool registry** (slutt `tools/tool_registry.py`): `ToolRegistry` (singleton), `ToolEntry`, `ToolParameter`, `SandboxSpec`, registration, OpenAI function-schema export, arg validation, metrics, direct execution; sandbox execution delegated to an optional isolator interface.
3. **Agent loop** (agent-zero `Agent.monologue` shape + OpenManus flow + slutt `AgentCore`/`AgentLoop`): iterative think→tool→observe loop with a pluggable LLM provider and tool registry, bounded iterations, final response.
4. **Memory store** (hermes `memory_manager` concept, simplified): file-backed key/value + tagged entries with keyword search and periodic "nudge" hook; no Honcho/FTS5.
5. **Model loader** (model-loader + llama-optim): GGUF metadata probe, autoconfig (ctx-size, gpu-layers, cache quant), llama-server process lifecycle (start/stop/health), optimization parameter sweep + benchmark harness.
6. **Multi-agent orchestration** (slutt `MultiAgentOrchestrator` + OpenManus flow): planner decomposes task into steps; orchestrator runs sub-agents (sequential/parallel) and aggregates.
7. **Self-improvement hook** (hermes learning loop, simplified): post-task review that can register new tools/skills; skills stored as markdown with front-matter (agentskills.io-compatible shape).
8. **Capability tools from slutt non-core sections** (simplified): complexity evaluation, coverage collection, PII redaction, telemetry logging, canary controller, release tagger, hot-swap loader, knowledge extraction — registered as tools/skills with real (simplified) implementations.
9. **Auto skill discovery/download + equipping** (hermes `skill_bundles`/`skills_index_delta` + slutt tool synthesizer): fetch skills from a registry URL, validate, equip into the active agent; track installed set.
10. **Automatic dynamic tool creation** (slutt `ToolSynthesizer`): when a tool call fails or a capability gap is detected, synthesize a new tool function from a spec and register it.
11. **Automatic prompt refining** (hermes `prompt_builder` + slutt `dynamic_assembler`): assemble system prompt from profile + memory + skills + context; refine via feedback.
12. **Auto initial codebase exploration** (slutt `knowledge_extractor` + `ast_symbols`): on startup, scan project tree, extract symbols/knowledge, populate memory.

### Deliberately excluded
- Web UI / TUI / desktop / browser automation (agent-zero, model-loader, slutt) — **PARTIALLY IN SCOPE**: a minimal FastAPI web UI + a minimal TUI are included (see architecture); full desktop/browser automation remains out of scope.
- Docker/container orchestration, GPU telemetry, power monitoring (model-loader) — host-infra concerns, not runtime logic.
- slutt's 30+ non-core sections — **PARTIALLY IN SCOPE**: their public capabilities are exposed as registered tools/skills (simplified real implementations) rather than full subsystem ports. Full subsystems remain excluded.
- hermes channel gateways (Telegram/Discord/Slack/WhatsApp/Signal) — transport adapters, out of scope.
- Honcho dialectic user modeling, FTS5 session search — heavy deps; basic memory store covers needs.
- Agent profile YAML + prompt template trees (agent-zero) — **IN SCOPE**: agent profiles loaded from YAML + prompt templates assembled per profile (see architecture).
- Full OpenManus sandbox/browser tooling — keep tool interface only.

## Top-level concepts (Repo Read)

- **Agent Zero**: Dockerized Linux agent with extensible monologue loop, tool/hook system, projects, memory, skills, plugins, multi-agent delegation.
- **Hermes**: self-improving agent with closed learning loop (memory nudges, autonomous skill creation, FTS5 recall, Honcho user model), multi-platform gateway, 7 terminal backends, cron, subagents.
- **OpenManus**: simple Manus-style agent: flow-based planning (PlanAct), tool collection, sandbox, browser, MCP; minimal and hackable.
- **model-loader**: FastAPI homelab UI for llama.cpp GGUF management: HF download, models.ini editing, autoconfig, benchmarking, capability badges, load-failure diagnosis.
- **llama-optim**: small script sweeping llama.cpp server params for max throughput.
- **slutt (v9)**: 34-section kitchen-sink agent system; innovations concentrated in context compression, dynamic tool registry with sandbox specs, multi-agent orchestration, coding agent, and hot-swap plugin loading.

## Innovations taken

1. **Hierarchical summarization with tier promotion** (slutt): immediate→recent→session→historical→semantic tiers with bounded budgets; rolling summary replaces older turns. Buys long-session stability; costs loss of detail in old turns.
2. **Budget-bounded model message list** (slutt `ContextWindow.get_messages_for_model`): verbatim tail + single compressed system message; never exceeds budget.
3. **Dynamic tool registry with inferred params + OpenAI schemas + sandbox specs** (slutt): tools self-describe; sandbox execution optional; metrics per tool.
4. **Monologue agent loop with tool calls** (agent-zero): LLM emits tool calls, runtime executes, feeds results back, until final answer or iteration cap.
5. **Flow/plan-then-act** (OpenManus): planner produces step list before execution.
6. **Learning nudge + skill creation** (hermes): after complex tasks, agent curates memory and may create a reusable skill (markdown).
7. **GGUF autoconfig** (model-loader): read model metadata + probe VRAM, pick ctx/ngl/cache quant; fall back to `--fit` for MoE overflow.
8. **Parameter sweep benchmark** (llama-optim + model-loader): measure throughput across configs, keep best.

## Performance

- Context compression keeps token cost bounded (O(budget)) regardless of session length; summarization is O(turns) per compression event.
- Tool registry lookups O(1); execution dominated by tool I/O.
- Model autoconfig probes VRAM once; no repeated probing.
- No measured numbers available (unmeasured; label as estimated).

## Standardized language (term mapping)

- agent-zero "monologue" → "agent loop" / `Agent.run`
- slutt "ContextWindow" → `ContextWindow` (kept; standard term)
- slutt "DynamicToolRegistry" → `ToolRegistry`
- slutt "ToolEntry.to_openai_function" → `to_function_schema`
- slutt "SandboxSpec" → `SandboxSpec` (kept)
- hermes "skill" → `Skill` (agentskills.io shape)
- model-loader "models.ini section" → `ModelProfile`
- llama-optim "n-gpu-layers" → `gpu_layers`
- hermes "memory nudge" → `MemoryNudge`

## Architecture (target)

```
princesse/
  pyproject.toml
  princesse/
    __init__.py
    context.py        # ContextWindow, HierarchicalSummarizer
    tools.py          # ToolRegistry, ToolEntry, ...
    agent.py          # Agent, AgentLoop
    profiles.py       # AgentProfile loader (YAML + prompt templates)
    prompts.py        # PromptTemplate assembler
    memory.py         # MemoryStore, MemoryNudge
    models.py         # GGUF probe, autoconfig, LlamaServer
    optimize.py       # param sweep, benchmark
    orchestration.py  # Planner, Orchestrator
    skills.py         # Skill load/save
    skill_download.py # Auto skill discovery/download/equip
    tool_synthesis.py # Dynamic tool creation
    codebase_explore.py # Auto initial codebase exploration
    providers.py      # LLM provider protocol
    ui/
      web.py          # FastAPI minimal web UI
      tui.py          # Minimal TUI (rich-based)
    cli.py            # CLI entrypoint
  tests/
  docs/
```

## Verification

- `pytest` unit tests for context compression, tool registry, agent loop (mocked LLM), memory, autoconfig.
- LSP/pyright clean.
- No stubs/mocks in shipped code (tests may use fakes).

## Open questions

1. Should the package ship a CLI (`princesse run ...`)? Recommend yes, minimal.
2. LLM provider: support OpenAI-compatible only initially? Recommend yes.
3. Sandbox execution: implement subprocess-based isolator or interface-only? Recommend interface + a basic subprocess isolator.
Please approve or adjust before implementation.
