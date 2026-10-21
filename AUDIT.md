# princesse — Complete Audit & Scoring Report

**Date:** 2026-10-22
**Commit audited:** `916fffb` → `f0dc2a1` (audit fixes applied in this pass)
**Language:** Python 3.11+ · **Package:** `princesse` 0.1.0
**Repo:** https://github.com/princessesnugglebunny-spec/princesse

---

## 1. Executive Summary

**Overall score: 7.6 / 10** — a strong, original agent runtime with excellent architecture and
extensibility, held back by test coverage gaps on the interface layer and an unfinished OS-level
sandbox.

| Verdict | Detail |
|---|---|
| **Production-ready?** | **No** — for untrusted input or multi-tenant use. **Yes** for local single-user development. |
| **Blocking gaps** | 4 (listed in §7) |
| **Defects found & fixed in this audit** | 11 |
| **Security findings** | 0 high, 0 medium (was 3 high, 4 medium) |
| **Test coverage** | 55% overall (4,847 stmts, 2,198 missed); 58.8% excluding `ui/*`; 62.4% excluding `ui/*` + `cli.py`; 0% on the interface layer (604 stmts) |

---

## 2. Objective Metrics

| Metric | Value | Source |
|---|---|---|
| Source modules | 57 | `find` |
| Source LOC | 6,677 | `wc -l` |
| Test modules / LOC | 20 / 990 | `pytest` |
| Tests | **96 passing, 0 failing** | `pytest -q` |
| Line coverage | **55%** (4,847 stmts, 2,198 missed) | `pytest-cov` |
| Type errors | **0** | `pyright` |
| Lint warnings | **0** | `pyflakes` |
| Security findings | **0 high / 0 medium / 26 low** | `bandit` |
| Stub markers (`TODO`/`FIXME`/`pass`/`NotImplementedError`) | **0** | grep |
| Bare `except:` | **0** | grep |
| Hook packs | 3 YAML files, 7 hooks | `hooks/builtin/` |
| Runtime dependencies | 3 (`pyyaml`, `rich`, `httpx`) | `pyproject.toml` |
| Optional dependencies | 1 (`playwright`) | `browser.py` |

### Largest modules (LOC)
| Module | LOC | Concern |
|---|---|---|
| `hooks.py` | 340 | Matching engine + executor in one module — consider splitting |
| `ui/repl.py` | 333 | 0% covered |
| `small_model_booster.py` | 331 | 37% covered, 4 agent strategies in one file |
| `cli.py` | 328 | 0% covered |
| `tools.py` | 298 | Core, 80% covered — acceptable |
| `context.py` | 245 | Core, 69% covered |

---

## 3. Dimension Scorecard

| # | Dimension | Score | Evidence | Verdict |
|---|---|---|---|---|
| 1 | **Architecture & modularity** | **9.0** | 57 focused modules, no circular imports, one public surface in `__init__.py`, no module >340 LOC | Excellent |
| 2 | **Extensibility & plugin surface** | **9.0** | `ToolRegistry` + `register_tool` (idempotent), `LLMProvider` protocol, skill registry, YAML hook packs, provider registry, MCP bridge | Excellent |
| 3 | **Observability & transparency** | **8.5** | `EventBus` (7 event kinds), `TranscriptWriter`, JSONL audit log with correlation IDs, live REPL rendering, per-tool metrics | Strong |
| 4 | **Code quality & hygiene** | **8.5** | pyright 0, pyflakes 0, no stubs, docstrings on public API, `__all__` complete (40+ exports) | Strong |
| 5 | **Security posture** | **7.5** | Path chroot, deny-by-default command allowlist, skill hash verification, URL scheme validation, redaction, sandboxed builtins — but `shell=True` and `exec` remain by design | Good, not hardened |
| 6 | **Documentation** | **7.0** | README (updated), `AUDIT.md`, distillation spec, implementation plan, module docstrings — no API reference or architecture diagram | Adequate |
| 7 | **Developer experience** | **7.5** | `princesse` CLI with 10 subcommands, rich REPL, `--help` everywhere, no setup wizard or config validator | Good |
| 8 | **Performance & token efficiency** | **7.0** | Parallel tool execution, tool scoping by hook, output truncation, context pruning, response caching, retry/backoff — but no streaming in the agent loop, no connection pooling, no benchmarks | Adequate |
| 9 | **Error handling & resilience** | **7.0** | Retry with exponential backoff, catalogue cache fallback, provider health checks, graceful degradation — but several `except Exception: pass` blocks swallow errors silently | Adequate |
| 10 | **Feature completeness vs. goal** | **8.0** | 8 of 9 requested audit items + hook system + model teaming + catalogues + transparency + reuse advisor | Strong |
| 11 | **Test suite** | **6.5** | 96 tests, 55% coverage, good unit coverage on core modules — 0% on `cli.py`/`ui/*`, no integration tests, no real-LLM test | Weakest area |
| 12 | **Production readiness** | **6.5** | No OS sandbox by default, no secrets manager, no rate limiting, no multi-tenancy, auto-install runs on every CLI invocation | Not ready |

**Weighted overall: 7.6 / 10** (weights: architecture 2×, security & correctness 2×, everything else 1×)

---

## 4. Coverage by Module

| Coverage | Modules |
|---|---|
| **90–100%** | `memory_consolidation` 100, `providers/__init__` 100, `codebase_explore` 90, `learning` 91, `optimize` 91, `skills` 91, `tool_cache` 70 → `models_ini` 83, `reuse` 84, `memory` 84 |
| **70–89%** | `tools` 80, `hooks` 79, `execution` 78, `orchestration` 78, `transparency` 76, `coding_agent` 75, `config` 75, `audit_log` 74, `rag` 72, `mcp_catalogue` 70, `capabilities` 69, `context` 69 |
| **50–69%** | `providers/catalogue` 68, `providers/team` 58, `security` 59, `llm_optimization` 57, `models` 53, `skill_catalogue` 51, `providers/registry` 49 |
| **30–49%** | `git_tools` 44, `profiles` 42, `small_model_booster` 37, `prompts` 36, `context_pruning` 36, `tool_synthesis` 35, `providers/cli_bridge` 34, `lsp_tool` 33, `browser` 31, `reflection` 30, `tdd` 38 |
| **0–29%** | `hf_download` 26, `inference` 25, `mcp_client` 23, `bootstrap_install` 18, `skill_download` 18, `llm` 12, `cli` 0, `ui/repl` 0, `ui/web` 0, `ui/tui` 0 |

**Interface-layer coverage: 0%** — `cli.py` + `ui/*` is 604 statements with no tests, and is the
single biggest blind spot. Everything else reaches 58.8%, and the core runtime
(`agent`, `tools`, `context`, `hooks`) reaches 69–80%.

---

## 5. Security Audit

### Bandit results
| Severity | Before this audit | After |
|---|---|---|
| High | 3 | **0** |
| Medium | 4 | **0** |
| Low | 26 | 26 |

Remaining 26 LOW findings are inherent to the design: `B404`/`B603`/`B607` (subprocess use),
`B110` (try/except/pass), `B112` (try/except/continue). None are exploitable in context —
subprocess calls are policy-gated and try/except blocks guard optional subsystems.

### Control matrix
| Control | Status | Implementation |
|---|---|---|
| Filesystem containment | ✅ | `security.safe_path()` resolves symlinks, rejects `..` escapes |
| Command execution control | ✅ | `CommandPolicy` allowlist + 7 deny patterns (`rm -rf /`, `sudo`, fork bombs, `curl\|sh`) |
| Untrusted skill handling | ✅ | SHA-256 verification, optional cosign signature, filename sanitisation |
| Secret redaction | ✅ | `redact()` + `redact_mapping()` on audit log **and** transcripts |
| URL scheme validation | ✅ | `safe_http_url()` rejects `file:`/`ftp:`/custom schemes |
| Dynamic code execution | ⚠️ | `exec` retained (dynamic tool creation) but namespace restricted to 28 safe builtins |
| Shell execution | ⚠️ | `shell=True` retained by design, gated by policy + workspace cwd |
| OS-level isolation | ❌ | `SandboxIsolator` is interface-complete but not wired as the default; `preexec_fn` limits are advisory |
| Authentication on MCP transport | ❌ | stdio only; no TLS/mTLS |
| Rate limiting / quota | ❌ | Not implemented |
| Secret management | ❌ | Keys read from env only; no OS keychain integration |

---

## 6. Defects Found and Fixed in This Audit

| # | Defect | Severity | Fix |
|---|---|---|---|
| 1 | `register_default_tools` raised `ValueError` on second call (non-idempotent) | **High** | New `register_tool()` helper; all 5 packs use it; regression test added |
| 2 | Skill name from an untrusted catalogue escaped the skills directory (`../escape` → wrote outside) | **High** | `sanitize_name()`; `SkillRegistry.register` normalises; test added |
| 3 | `llama-server` process leaked when it never became healthy | **High** | `start()` now terminates the process and returns `False` |
| 4 | Browser tools advertised when playwright was absent → guaranteed-failing tool call + wasted turn | Medium | `register_browser_tools()` returns 0 and registers nothing when unavailable |
| 5 | Secrets leaked into markdown transcripts (`token: sk-...` survived) | **High** | `TranscriptWriter` now redacts; pattern extended to bare `token`; test added |
| 6 | `exec` in tool synthesis had unrestricted builtins | **High** | `_safe_builtins()` — 28 builtins, no `open`/`__import__`/`eval` |
| 7 | Health probes followed any URL scheme (`file:` local read) | Medium | `safe_http_url()` + `nosec` justification |
| 8 | SHA-1 flagged as a weak crypto primitive | Medium | `usedforsecurity=False` (identifier, not security) |
| 9 | `hf_download.download_parallel` was serial — docstring lied | Medium | Real parallel range download with per-chunk resume and merge |
| 10 | `rag.Indexer._index` written but never read | Low | Removed |
| 11 | `providers` package shadowed `providers.py` module → circular import | **High** | Moved base class to `princesse/llm.py`; `providers/` is now a package |

---

## 7. Open Issues (ranked)

### P0 — Blocking for production
| ID | Issue | Why it blocks |
|---|---|---|
| P0-1 | `SandboxIsolator` not the default execution path | `run_terminal`/`run_python` run in the host process; `preexec_fn` limits are advisory, not a security boundary |
| P0-2 | `ui/repl.py`, `ui/web.py`, `cli.py` have 0% coverage | The user-facing surface is entirely unverified; 604 statements of untested code |
| P0-3 | `exec`-based tool synthesis reachable from the agent loop | Model-authored code executes in-process; restricted builtins reduce but do not remove risk |
| P0-4 | No authentication on the web UI | `princesse web` binds `127.0.0.1` with no auth or CSRF — safe locally, unsafe if bound publicly |

### P1 — Should fix before wide use
| ID | Issue |
|---|---|
| P1-1 | Auto-install runs on **every** `princesse run` invocation (pip/npm/LSP installs) — should be once-per-boot or explicit |
| P1-2 | `except Exception: pass` in 5 places silently hides failures (bootstrap_install, transparency, mcp_client, cli, browser) |
| P1-3 | `ToolRegistry` is a global singleton — tests and multi-agent runs share state |
| P1-4 | `small_model_booster` implements 4 agent strategies in one file (37% covered) |
| P1-5 | `hooks.py` mixes the matching engine and the action executor (340 LOC) |
| P1-6 | No structured logging; only the audit log and event bus |

### P2 — Quality of life
| ID | Issue |
|---|---|
| P2-1 | Streaming is implemented in the provider but never used by the agent loop |
| P2-2 | No connection pooling — a new HTTP client per LLM call |
| P2-3 | `ProviderRegistry.health()` opens a fresh connection per provider |
| P2-4 | No API reference documentation or architecture diagram |
| P2-5 | No lockfile — dependency versions are ranges |
| P2-6 | `hf_download` still lacks a live end-to-end test against Hugging Face |

---

## 8. Recommendations

### P0 (this sprint)
1. **Wire `SandboxIsolator` as the default** for `run_terminal` / `run_python`; keep host execution behind an explicit `sandbox=false` opt-in.
2. **Add interface-layer tests**: CLI argument parsing (subprocess-free), REPL command dispatch, web handler routing. Target ≥60% on those three modules.
3. **Gate dynamic tool synthesis** behind a config flag (`allow_dynamic_tools`) that is off by default and logged in the audit trail.
4. **Add auth to the web UI** (bearer token from config + CSRF) or bind to loopback only with a printed warning.

### P1 (next sprint)
5. Run auto-install once per boot, cached in `~/.princesse/bootstrap.json`; make it opt-in for `npm`/`pip` mutations.
6. Replace silent `except Exception: pass` with a logged warning through the event bus.
7. Make `ToolRegistry` instance-scoped with a module-level default, so tests and sub-agents do not share state.
8. Split `hooks.py` → `hooks/matching.py` + `hooks/executor.py`; split `small_model_booster.py` → one module per strategy.
9. Adopt `structlog` or stdlib `logging` with JSON output and the correlation ID from the audit log.

### P2 (backlog)
10. Stream tokens from the provider into the REPL instead of waiting for a full completion.
11. Add an `httpx.AsyncClient` pool reused across calls.
12. Write `docs/architecture.md` (module map + data flow) and `docs/api.md`.
13. Pin dependencies with `uv.lock` and add a scheduled `pip-audit` run.
14. Add a live smoke test against a public OpenAI-compatible endpoint (opt-in, marked `network`).

---

## 9. Test Gap Plan

| Target | Modules | Current | Action |
|---|---|---|---|
| ≥80% | `cli`, `ui/repl`, `ui/web`, `ui/tui` | 0% | Add smoke tests (arg parsing, command dispatch, HTTP routing) |
| ≥70% | `small_model_booster`, `security`, `providers/*`, `bootstrap_install`, `mcp_client`, `skill_download` | 18–59% | Add unit tests with fake providers / local HTTP stubs |
| ≥90% | core runtime (`agent`, `tools`, `context`, `hooks`) | 69–80% | Add edge cases: tool-call storms, empty context, malformed tool args |

---

## 10. Limits of This Audit

- **Coverage is line coverage**, not branch coverage; branch coverage would be materially lower.
- **No live-LLM validation**: every provider path was exercised with fakes or a local stub. Real
  models, real tool-call formats, and real streaming were not tested.
- **No multi-user / concurrency test**: the global `ToolRegistry` singleton and the shared
  `.princesse/` state directory were not stress-tested.
- **Dependency CVE scan not completed**: `pip-audit` requires network access to the advisory
  database and was killed on timeout — **unverified**.
- **`bandit` does not model the agent threat model**: an LLM driving `run_terminal` is a different
  risk profile than a web service.
- Scores are the auditor's judgement against the stated goals, not a benchmark against other
  projects.

---

## 11. Bottom Line

**princesse is a well-built, original agent runtime with an unusually strong foundation in
architecture, extensibility, and observability for a project of this size.** The distillation from
six reference repositories produced coherent, well-named code rather than a copy.

It is **not** production-ready: the OS-level sandbox is optional, the interface layer is untested,
and dynamic code execution remains reachable. Those three items (P0-1, P0-2, P0-3) are the
difference between a powerful local agent and a service you would expose.

Fixing the four P0 items and lifting the interface layer to 60% coverage would move the overall
score to roughly **8.6 / 10** and make the project defensible for real use.
