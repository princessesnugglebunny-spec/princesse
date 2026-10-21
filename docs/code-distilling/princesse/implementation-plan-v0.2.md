# Implementation Plan — princesse v0.2

**Date:** 2026-10-22  
**Base commit:** `95a0b3b`  
**Scope:** 9 audit items + novel hook system + model teaming + provider/catalogue layer + auto-install  
**Explicitly excluded:** multimodal routing (per user)

---

## Phase A — Foundations

### A1. `princesse/config.py` (audit #8)
Typed configuration with three merge layers (env > YAML > defaults).

```python
@dataclass
class Config:
    workspace: Path
    provider: str = "local"
    model: str = "auto"
    context_budget_tokens: int = 4000
    max_iterations: int = 10
    sandbox_enabled: bool = True
    allowed_commands: list[str] = [...]      # deny-by-default allowlist
    providers: dict[str, ProviderConfig]      # name -> base_url/key/model
    hooks_enabled: bool = True
    catalogue_url: str = "https://models.dev/api.json"
    catalogue_ttl_hours: int = 24
    auto_install: bool = True
```

Load order: `defaults` → `~/.princesse/config.yaml` → `./.princesse/config.yaml` → env (`PRINCESSE_*`).

### A2. `princesse/audit_log.py` (audit #6)
Append-only JSONL audit trail.

- `AuditLog(path)`; `log_tool_call(name, args, result, duration_ms, ok)`, `log_llm_call(model, tokens, latency)`, `log_event(kind, **fields)`.
- Every record gets `correlation_id` (UUID) + `ts`.
- Rotation at 10 MB (keep 5 files).
- `query()` helper for inspection; redacts secrets via `pii_redact`.

### A3. `princesse/security.py` (audit #2, #3)
- `safe_path(path, root)` → resolves symlinks, rejects escapes, returns resolved path or raises `PathEscapeError`.
- `CommandPolicy(allowlist, denylist)` → `check(command)`; deny-by-default; blocks `rm -rf /`, `sudo`, `curl | sh`, `dd`, fork bombs.
- `verify_skill(path, expected_sha256=None)` → SHA-256 check + optional cosign/sigstore signature check if `cosign` is on PATH; returns `VerificationResult`.
- `SkillVerifier` used by `skill_download.py` before registration.

### A4. `princesse/execution.py` (patch — audit #2)
`read_file`, `write_file`, `edit_file`, `list_dir` gain `root` parameter (default: config workspace) and route through `safe_path`. `run_terminal` routes through `CommandPolicy`. A `SubprocessIsolator` implements the `ToolRegistry` sandbox interface using `resource` limits + temp cwd.

---

## Phase B — Providers, Catalogue, Model Teaming

### B1. `princesse/providers/registry.py`
`ProviderSpec` catalogue (base_url, env var, api style, auth mode).

| Provider | Base URL | Key env | Auth |
|---|---|---|---|
| `opencode` (Zen) | `https://opencode.ai/zen/v1` | `OPENCODE_API_KEY` | bearer (free tier) |
| `opencode-go` | `https://opencode.ai/zen/go/v1` | `OPENCODE_API_KEY` | bearer |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | bearer |
| `nvidia` (NIM) | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` | bearer |
| `poolside` | `https://inference.poolside.ai/v1` | `POOLSIDE_API_KEY` | bearer |
| `ollama` | `http://localhost:11434/v1` | — | none (local) |
| `llamacpp` | `http://127.0.0.1:8080/v1` | — | none (local) |
| `lmstudio` | `http://127.0.0.1:1234/v1` | — | none (local) |
| `kilo` | CLI bridge | — | none (free tier) |
| `alphacode` | CLI bridge | — | none (free tier) |

`ProviderRegistry` holds live instances, `available()` (key present or local endpoint up), `health()` (GET `/v1/models`).

### B2. `princesse/providers/catalogue.py`
- `fetch_catalogue(url)` → models.dev JSON (232 providers, ~6 MB) cached at `~/.princesse/catalogue.json` with TTL.
- `refresh(force)` — re-fetch; **called on startup** (non-blocking, cached copy used if fetch fails).
- `free_models()` → all models with `cost.input == 0` (651 known).
- `models_for(provider)`; `find_model(query)` — fuzzy match by name/family.
- `test_model(provider, model)` → 1-token completion probe with timeout; marks model healthy/unhealthy; cached.

### B3. `princesse/providers/cli_bridge.py`
CLI-backed providers that shell out to free agents (kilo, alphacode). Each provider defines a command template; the bridge runs it, streams stdout, and parses a final-answer marker. Used as a fallback provider when no API key is configured.

### B4. `princesse/providers/team.py` — Model Teaming
- `ModelTeam(providers: dict[str, LLMProvider])`
- `route(task, strategy)` → picks provider by capability tags (`code`, `reasoning`, `summarize`, `tool_call`, `cheap`), or by free-model availability, or round-robin.
- `ensemble(task, n)` → run n providers/models in parallel, majority vote (`SelfConsistency` reuse), returns answer + agreement score.
- `debate(task, n)` → providers critique each other's answers, final synthesizer picks best.
- Integrates with `Agent` via a `TeamingProvider` that internally routes each LLM call.

---

## Phase C — Semantic Trigger Hooks (novel)

### C1. `princesse/hooks.py`
A declarative, fuzzy trigger engine.

```yaml
name: debug_session
triggers:
  - words: [debug, error, failing, broken, crash]
    order: loose            # any order
    proximity: 60           # max token gap
    threshold: 0.6          # fuzzy score
    min_matches: 2
actions:
  - preload_tools: [run_terminal, lsp_diagnostics, git_diff]
  - preload_skills: [error_patterns]
  - inject_context: recent_errors
  - switch_profile: debugger
  - background: run_tests
```

- `TriggerSpec` — words, synonyms, order (`strict`/`loose`), proximity, threshold, min_matches.
- `Hook` — id, triggers, actions.
- `HookEngine` — loads YAML hook packs, matches against text, returns `HookMatch` list with scores.
- Matching: token overlap + `difflib` fuzzy ratio + proximity window + order constraint.
- Actions executed by `HookExecutor`:
  - `preload_tools` → registers tool into a scoped view
  - `preload_skills` → injects skill content into the system prompt
  - `inject_context` → pulls from memory/RAG
  - `switch_profile` → swaps the agent profile mid-session
  - `background` → spawns an async task (non-blocking)

### C2. `princesse/hooks/builtin/*.yaml`
Packs: `debug.yaml`, `code_review.yaml`, `security.yaml`, `refactor.yaml`, `research.yaml`, `release.yaml`.

### C3. Integration
`Agent.run` calls `HookEngine.match(goal)` before the first LLM call, applies preload actions, and re-evaluates after each tool result (so "now the test fails" can trigger the debug hook mid-task).

---

## Phase D — Intelligence

### D1. `princesse/rag.py` (audit #12)
Retrieval over codebase + memory with **no new heavy dependency**:
- `Chunker` — AST-aware for Python, line-window for other files.
- `Indexer` — TF-IDF + hashing vector (implemented locally, ~150 LOC), cosine similarity.
- `PersistentIndex` — JSON store at `~/.princesse/index/`.
- `retrieve(query, k)` → ranked chunks; `retrieve_code(symbol)` → definition lookup.
- `auto_index(project_root)` on startup (configurable).

### D2. `princesse/models.py` (patch — audit #13)
Speculative decoding for llama.cpp: `ModelProfile.speculative` (draft model path, draft n, min tokens), `--speculative-model` / `--draft-max` flags in `LlamaServer.start`, plus `--fit` passthrough for MoE overflow (from model-loader).

### D3. `princesse/bootstrap_install.py` (new — user request)
Automatic environment setup on startup:
- **Dependencies**: parse `pyproject.toml`/`requirements.txt` → `pip install -e .` if imports missing.
- **LSP servers**: map language → server command (pyright, rust-analyzer, gopls, tsserver, clangd...) → install if missing and `auto_install` enabled.
- **MCP servers**: from config `mcp_servers` list → `uvx`/`npx` install + connect via `MCPRegistry`.
- All installs are logged to the audit log and reported, never silent.

---

## Phase E — Developer Experience

### E1. `princesse/ui/repl.py` (audit #14)
Rich REPL: streaming responses, input history (file-backed), slash commands (`/help`, `/models`, `/provider`, `/hooks`, `/tools`, `/memory`, `/skills`, `/exit`), inline docs (`/doc <name>`), Tab-completion for slash commands, Ctrl-C interrupt.

### E2. `princesse/cli.py` (patch — audit #10)
`princesse run` uses `SmallModelBooster` by default (`--no-boost` to disable). New commands: `models` (catalogue browse + test), `providers` (list + health), `hooks` (list/test), `install` (bootstrap).

---

## Module Map (new/changed)

```
princesse/
  config.py              NEW  typed config, env/YAML layering
  audit_log.py           NEW  append-only JSONL audit trail
  security.py            NEW  path sandbox, command policy, skill verification
  hooks.py               NEW  semantic trigger engine
  hooks/builtin/*.yaml   NEW  hook packs
  rag.py                 NEW  TF-IDF/hash index + retrieval
  bootstrap_install.py   NEW  auto deps/LSP/MCP install
  providers/
    __init__.py          NEW
    registry.py          NEW  provider specs + health
    catalogue.py         NEW  models.dev fetch/cache/refresh + model tests
    cli_bridge.py        NEW  kilo/alphacode CLI providers
    team.py              NEW  routing, ensemble, debate
  ui/repl.py             NEW  rich REPL
  execution.py           CHANGED  path sandbox + command policy
  skill_download.py      CHANGED  verification gate
  models.py              CHANGED  speculative decoding
  agent.py               CHANGED  hook integration
  cli.py                 CHANGED  boosted default + new commands
```

---

## Verification Plan

| Check | Gate |
|---|---|
| `pytest -q` | ≥ 95 tests, all pass |
| `pyright` | 0 errors, 0 warnings |
| Security tests | path escape rejected; deny-listed command blocked; tampered skill rejected |
| Hook tests | ordered + loose + fuzzy matching; action side-effects verified |
| Provider tests | catalogue parse, free-model filter, health probe against local stub |
| Team tests | routing selection, ensemble vote, debate aggregation |
| REPL smoke | launches, handles `/help`, exits cleanly |

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| models.dev unreachable | cached catalogue used; refresh is non-fatal |
| Free-tier providers require keys after all | registry reports `available=False` with a clear reason; CLI bridge is the no-key fallback |
| Auto-install mutates the host | gated behind `auto_install` config (default on for deps, off for system packages), always logged |
| Hooks fire on false positives | threshold + min_matches; `hooks_enabled` toggle; `/hooks` inspection command |
| RAG index grows unbounded | capped chunk count, rebuildable, stored outside the project |

---

## Estimated Delivery

6 commits, one per phase, each independently testable.

**Approval needed:** implement Phases A→E as specified?
EOF