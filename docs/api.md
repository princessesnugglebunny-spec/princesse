# API Reference

Public surface of `princesse`. Import from the package root:

```python
from princesse import Agent, ToolRegistry, ContextWindow, load_config
```

---

## Runtime

### `Agent`
```python
Agent(provider, tools=None, context=None, memory=None, system_prompt="...",
      max_iterations=10, hook_engine=None, hook_executor=None, audit_log=None,
      team=None, event_bus=None, stream_enabled=False)
```
- `await run(goal, use_optimizations=True) -> AgentResult`
- `active_tools: set[str] | None` — restricts the tool schemas sent to the model.
- `stream_enabled=True` uses the provider's streaming path and emits `llm_delta` events.

### `AgentResult`
`final_answer: str`, `iterations: int`, `tool_calls: list[dict]`, `messages: list[dict]`

### `AgentLoop`
`await start(goal) -> AgentResult` — thin convenience wrapper.

---

## Context

### `ContextWindow`
```python
ContextWindow(session_id="default", budget_tokens=4000, verbatim_tail=8, storage_path=None)
```
- `append(role, content, metadata=None) -> ContextMessage`
- `get_messages_for_model() -> list[dict]` — budget-bounded: running summary + verbatim tail.
- `get_total_tokens() -> int`, `save(path=None)`, `load(path)`

### `HierarchicalSummarizer`
Tiers: `immediate → recent → session → historical → semantic`.
`add_interaction()`, `create_semantic_summary()`, `get_context(max_tokens)`, `get_stats()`.

### Optimisation helpers
| Function | Purpose |
|---|---|
| `SlidingWindowCompressor.compress(window, keep_last)` | Trim a context, preserving entities |
| `OutputTruncator.truncate_tool_output(text, max_chars)` | Bound tool output size |
| `SemanticDeduplicator.dedup(messages)` | Drop repeated messages |
| `TokenBudgetAllocator(total).allocate(sections)` | Split a budget across sections |
| `ImportanceScorer.score(message, query, index, total)` | Rank messages |
| `ContextPruner.prune(window, query, max_messages)` | Relevance-based selection |
| `PromptCompressor.compress(text, target_ratio)` | Shrink redundant prompt text |
| `ChainOfThought.wrap(prompt, style)` | Append a reasoning cue |
| `FewShotSelector(examples).select(query, k)` | Pick relevant examples |
| `SelfConsistency(provider, n).run(messages)` | Majority vote over N samples |

---

## Tools

### `ToolRegistry`
```python
ToolRegistry(allow_dynamic_tools=False)
ToolRegistry.get_instance()      # process-wide default
ToolRegistry.set_default(reg)    # replace the default
```
| Method | Notes |
|---|---|
| `register(name, fn, description, category=..., parameters=None, ...)` | Raises if the name exists |
| `register_tool(registry, name, fn, description, **kwargs)` | Idempotent variant — use this in packs |
| `unregister(name)`, `get(name)`, `list_all()`, `search(query, category=None)` | Introspection |
| `await execute(name, args, sandbox=False)` | Validates args, runs sync or async fns, records metrics |
| `to_openai_tools(names=None)` | Schema export; `names` restricts the set |
| `register_synthesized(...)` | Raises `PermissionError` unless `allow_dynamic_tools` |

### `ToolEntry`
`to_function_schema()` → OpenAI function schema. `validate_args(args)` → `(ok, error)`.

### `SandboxSpec`
Declared sandbox intent per tool: image, memory, cpu, timeout, network, volumes, env, cwd, user.

---

## Hooks

```python
from princesse import HookEngine, HookExecutor
engine = HookEngine(["./princesse/hooks/builtin"])
matches = engine.match("the test is failing")
executor = HookExecutor(tools=reg, skills=reg, memory=store, advisor=advisor)
executor.apply(matches)
executor.prompt_injection(matches)   # text to inject into the system prompt
```

Trigger spec fields: `words`, `order` (`strict`/`loose`), `proximity` (token gap),
`threshold` (score gate), `min_matches`, `synonyms`.
Action kinds: `preload_tools`, `preload_skills`, `inject_context`, `switch_profile`,
`background`, `reuse_existing`.

---

## Providers

```python
from princesse.providers import ProviderRegistry, CatalogueManager, ModelTeam
reg = ProviderRegistry()               # 10 built-ins
reg.available()                         # usable right now
reg.health("openrouter")                # endpoint probe
key, url = reg.resolve("openrouter")

cat = CatalogueManager()                # models.dev, cached
await cat.refresh(force=True)
cat.get().free_models()                 # 651 known free models
await cat.test_model(url, "model-id")   # health probe

team = ModelTeam()
team.add("coder", provider, tags=["code"])
team.route("implement this function")   # capability routing
await team.ensemble("task", n=3)       # majority vote
await team.debate("task", n=3)          # critique + synthesis
```

Built-in providers: `opencode`, `opencode-go`, `openrouter`, `nvidia`, `poolside`,
`ollama`, `llamacpp`, `lmstudio`, `kilo`, `alphacode`.

---

## Models

```python
from princesse import probe_gguf, autoconfig, LlamaServer
meta = probe_gguf("model.gguf")     # GGUF metadata
prof = autoconfig(meta, vram_bytes=8 << 30)
prof.speculative_model = Path("draft.gguf")
prof.fit = True                     # let llama.cpp place an oversized MoE
server = LlamaServer(); server.start(prof); server.health(); server.stop()
```

---

## Security

```python
from princesse.security import safe_path, CommandPolicy, SkillVerifier, SandboxIsolator
safe_path("src/app.py", "/workspace")     # raises PathEscapeError on escape
CommandPolicy().check("rm -rf /")         # PolicyDecision(allowed=False, reason=...)
SkillVerifier(expected_hashes={...}).verify(path)
SandboxIsolator("/workspace").run_command_sync("pytest -q")
```

---

## Observability

```python
from princesse import EventBus, TranscriptWriter, AuditLog
bus = EventBus()
bus.subscribe(lambda e: print(e.kind, e.data))
tw = TranscriptWriter("transcript.md"); tw.attach(bus)
tw.save()

log = AuditLog("~/.princesse/audit.jsonl")
log.log_tool_call("read_file", {"path": "a.py"}, "ok", 12.5, True)
log.query(kind="tool_call")
```

---

## Reuse & retrieval

```python
from princesse import ReuseAdvisor, Retriever
advisor = ReuseAdvisor(root="."); advisor.build()
advisor.suggest("parse configuration file")     # ranked existing symbols
advisor.prompt_block("parse configuration file") # inject into the system prompt
advisor.similar_symbols("load_settings")         # prior art by name

r = Retriever(indexer=Indexer(root="."))
r.auto_index(); r.retrieve("config loading", k=5); r.retrieve_code("load_settings")
```

---

## Configuration

```python
from princesse import load_config
cfg = load_config()   # defaults → ~/.princesse/config.yaml → ./.princesse/config.yaml → env
```
Environment overrides: `PRINCESSE_PROVIDER`, `PRINCESSE_MODEL`, `PRINCESSE_SANDBOX`,
`PRINCESSE_ALLOW_HOST_EXECUTION`, `PRINCESSE_ALLOW_DYNAMIC_TOOLS`, `PRINCESSE_HOOKS_ENABLED`,
`PRINCESSE_CONTEXT_BUDGET`, `PRINCESSE_MAX_ITERATIONS`, `PRINCESSE_WEB_TOKEN`,
`PRINCESSE_WEB_HOST`, `PRINCESSE_MCP_SERVERS`, `PRINCESSE_LOG_LEVEL`, `PRINCESSE_LOG_FORMAT`.
