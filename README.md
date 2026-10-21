# princesse

An original agent runtime distilled from the decisions in:
- agent0ai/agent-zero (ff2a5b9)
- NousResearch/hermes-agent (3ab0930)
- FoundationAgents/OpenManus (3309bf4)
- scratchhax/model-loader (1c3032b)
- jir88/llama-optim (fa1241d)
- SlutPrincesse/slutt @ kilo/atomic-harbor-2w8 (6925bac)

All code is original, re-expressed in this project's conventions (PRP). No code was copied.

## Install

```bash
pip install -e .
```

## Usage

```bash
princesse version
princesse explore .
princesse web --port 8765
princesse tui
princesse repl                       # interactive REPL with live transparency
princesse run "summarize this repo" --provider ollama --model qwen3
princesse models --free             # browse the model catalogue
princesse providers --health        # probe provider endpoints
princesse hooks "fix the failing test"   # test semantic trigger hooks
princesse reuse "parse configuration file"  # find code that already exists
princesse install --dry-run          # auto deps / LSP / MCP setup
```

## Capabilities

### Core runtime
- Rolling context window with hierarchical summarization (budget-bounded).
- Dynamic tool registry with OpenAI function schemas, validation, metrics, sandbox specs.
- Agent loop (think -> tool -> observe) with pluggable LLM provider, parallel tool execution.
- File-backed memory store with keyword search, nudges, consolidation.
- Agent profiles (YAML) + dynamic prompt assembler.
- Skills (markdown with front-matter), skill catalogue, auto download/equip with hash verification.
- MCP client + MCP server catalogue (official registry search, local/remote install).
- Learning loop: post-task review, memory nudges, auto skill creation.
- Reuse advisor: finds code that already exists in the repo before new code is written.

### Semantic trigger hooks
Declarative YAML hooks with fuzzy / ordered / proximity matching that preload tools, inject
context, switch profiles, or run background work — before the model asks for them.
Built-in packs: debug, code review, security, refactor, research, release.

### Providers & model teaming
- Built-ins: OpenCode Zen, OpenCode Go, OpenRouter, NVIDIA NIM, Poolside, Ollama, llama.cpp, LM Studio.
- Key-free CLI providers: Kilo, AlphaCode (shell-out bridge).
- Model catalogue: models.dev fetch/cache/refresh on startup, free-model discovery, model health probes.
- Model teaming: capability routing, ensemble voting, debate.

### Model operations
- GGUF metadata probe, autoconfig (ctx/gpu-layers/cache quant), llama-server lifecycle.
- Speculative decoding support (`--speculative-model`, `--draft-max`), `--fit` passthrough.
- `models.ini` management with atomic writes and rolling backups.
- HF GGUF download with resume; parameter sweep + benchmark harness.

### Security & transparency
- Workspace path sandbox, deny-by-default command allowlist, skill signature/hash verification.
- Append-only JSONL audit log with correlation IDs and secret redaction.
- Live transparency bus: every LLM call, tool call, hook match and memory write is observable.
- Rich REPL with live event rendering, slash commands, and transcript export.

### Intelligence
- Local RAG (TF-IDF + hashing vectors, AST-aware chunking) over the codebase and memory.
- Small-model booster: CoT, few-shot, self-consistency, reflection, verification, structured reasoning.
- Context optimisation: importance scoring, deduplication, token budgeting, sliding window, truncation.

## Tests

```bash
pytest -q
```

## License

MIT (code original to this project).
EOF
cd /root/projects/princesse && python -m pytest -q 2>&1 | tail -3