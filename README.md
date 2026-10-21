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
princesse run "summarize this repo" --base-url http://localhost:8080/v1 --model default
```

## Capabilities

- Rolling context window with hierarchical summarization (budget-bounded).
- Dynamic tool registry with OpenAI function schemas, validation, metrics, sandbox specs.
- Agent loop (think -> tool -> observe) with pluggable LLM provider.
- File-backed memory store with keyword search and nudges.
- Agent profiles (YAML) + dynamic prompt assembler.
- Skills (markdown with front-matter).
- Auto skill download/equip, dynamic tool synthesis, codebase exploration.
- GGUF metadata probe, autoconfig, llama-server lifecycle.
- Parameter sweep + benchmark harness.
- Multi-agent orchestration.
- Capability tools: complexity, coverage, PII redaction, telemetry, canary, release tagging, hot-swap, knowledge extraction.

## Tests

```bash
pytest -q
```

## License

MIT (code original to this project).
EOF
cd /root/projects/princesse && python -m pytest -q 2>&1 | tail -3