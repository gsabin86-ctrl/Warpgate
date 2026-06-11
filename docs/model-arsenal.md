# Warpgate Model Arsenal Manifest

Last updated: 2026-06-11

This manifest records source-verified model additions for Giga-Brain / Warpgate. It intentionally avoids duplicating models already installed on the Ollama ports unless a model needs to exist in a separate isolated model store.

## Current pre-expansion Ollama inventory

### Port 11434 — main

- `fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b`
- `llama2-uncensored:latest`
- `gemma4:e4b`
- `assistant-persistent:latest`
- `qwen3.5:9b-q4_K_M`
- `qwen2.5:7b`
- `qwen2.5:32b`
- `nomic-embed-text:latest`
- `mistral:7b`
- `llama3:8b`
- `llama3.2:3b`

### Port 11435 — karax

- `qwen2.5:7b`
- `llama3.2:3b`
- `gemma4:e4b`

### Port 11436 — spare

- `llama3.2:3b`
- `gemma4:e4b`

### Port 11437 — accounting

- `llama3.2:3b`
- `gemma4:e4b`

## Phase 1 selected Ollama additions

These models were selected because they add new capability categories: vision, code-specialization, and dedicated reasoning. They are targeted at the main Ollama store on port `11434` first. Other isolated ports can pull them later only if needed.

## `llama3.2-vision:11b`

- Capability: vision-language / image understanding
- Source URL: https://ollama.com/library/llama3.2-vision
- Exact model/tag: `llama3.2-vision:11b`
- Source verification: Ollama tag page listed `11b`, `11b-instruct-q4_K_M`, `11b-instruct-q8_0`, and related tags.
- Target host/service: main Ollama, `http://127.0.0.1:11434`
- Reason for adding: screenshot, diagram, UI, and local image Q&A capability.
- Already installed before expansion? no
- Validation command:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama list | grep 'llama3.2-vision'
```

- Rollback/removal command:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama rm llama3.2-vision:11b
```

## `qwen2.5-coder:7b-instruct-q4_K_M`

- Capability: code-specialized local LLM
- Source URL: https://ollama.com/library/qwen2.5-coder
- Exact model/tag: `qwen2.5-coder:7b-instruct-q4_K_M`
- Source verification: Ollama tag page listed `7b-instruct-q4_K_M` and other 7B/14B coder variants.
- Target host/service: main Ollama, `http://127.0.0.1:11434`
- Reason for adding: local coding assistant for Warpgate, scripts, test writing, and repo review.
- Already installed before expansion? no
- Validation command:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama list | grep 'qwen2.5-coder'
```

- Rollback/removal command:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama rm qwen2.5-coder:7b-instruct-q4_K_M
```

## `deepseek-r1:7b-qwen-distill-q4_K_M`

- Capability: dedicated reasoning model
- Source URL: https://ollama.com/library/deepseek-r1
- Exact model/tag: `deepseek-r1:7b-qwen-distill-q4_K_M`
- Source verification: Ollama tag page listed `7b-qwen-distill-q4_K_M` and related distilled variants.
- Target host/service: main Ollama, `http://127.0.0.1:11434`
- Reason for adding: slower but stronger local reasoning/planning model.
- Already installed before expansion? no
- Validation command:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama list | grep 'deepseek-r1'
```

- Rollback/removal command:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama rm deepseek-r1:7b-qwen-distill-q4_K_M
```

## Deferred Phase 1 candidate

### `llava`

- Source URL: https://ollama.com/library/llava
- Status: deferred for now.
- Reason: `llama3.2-vision:11b` is the first vision target. Add `llava` later only if we want a second/backup vision model.

## Validation checklist

After every pull:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama list
curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:8000/api/instances
```

For loaded model smoke tests, use Warpgate or direct Ollama API.

## Installation result — 2026-06-11

Installed on main Ollama, `http://127.0.0.1:11434`:

- `llama3.2-vision:11b`
  - Ollama ID: `6f2f9757ae97`
  - Reported size: `7.8 GB`
  - Smoke test: `/api/generate` returned `OK` for a short text prompt with `keep_alive: 0`.
- `qwen2.5-coder:7b-instruct-q4_K_M`
  - Ollama ID: `dae161e27b0e`
  - Reported size: `4.7 GB`
  - Smoke test: `/api/generate` returned `OK` for a short text prompt with `keep_alive: 0`.
- `deepseek-r1:7b-qwen-distill-q4_K_M`
  - Ollama ID: `755ced02ce7b`
  - Reported size: `4.7 GB`
  - Smoke test: `/api/generate` answered a `2+2` prompt; reasoning model latency was slower as expected.

Post-install disk state:

```text
/ filesystem: 158G used, 274G available, 37% used
```
