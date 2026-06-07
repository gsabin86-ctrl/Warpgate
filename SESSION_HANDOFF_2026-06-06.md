# Ollama Manager / Giga-Brain Session Handoff

Date: Saturday, June 6, 2026, late evening CDT
Host: Giga-Brain
Project: `/home/greg/ollama-project`
Manager URL: `http://127.0.0.1:8000/`
Managed by systemd unit: `ollama-manager.service`

## Purpose of this handoff

This document captures the current state of Greg's Ollama Manager work so a new Hermes session can continue without relying on the prior chat context.

## Current working state

The custom Ollama Manager UI is running and healthy.

Verification command:

```bash
systemctl is-active ollama-manager.service
```

Observed result:

```text
active
```

The four intended external/systemd Ollama instances are active and visible through the Manager API.

Current role/port map from `/api/instances`:

```text
11434 = external/default Ollama
        loaded: fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b
        family: qwen35
        params: 4.5B
        quant: Q4_K_M
        context: 2048

11435 = external Karax instance
        loaded: qwen2.5:7b
        family: qwen2
        params: 7.6B
        quant: Q4_K_M
        context: 4096

11436 = external Spare instance
        loaded: llama3.2:3b
        family: llama
        params: 3.2B
        quant: Q4_K_M
        context: 4096

11437 = external Accounting instance
        loaded: llama3.2:3b
        family: llama
        params: 3.2B
        quant: Q4_K_M
        context: 4096
```

All four are `external: true`, meaning they are systemd-managed Ollama services discovered by the Manager, not processes launched by the Manager itself.

The accidental/temporary managed test instance on `11438` was stopped before this handoff:

```text
DELETE /api/instances/11438 -> 200 {"status":"stopped","port":11438}
```

Final visible ports after cleanup:

```text
11434 running
11435 running
11436 running
11437 running
```

## Systemd service inventory

Expected active units:

```text
ollama.service              active running Ollama Service
ollama-karax.service        active running Ollama Instance - Karax
ollama-spare.service        active running Ollama Instance - Spare
ollama-accounting.service   active running Ollama Instance - Accounting
ollama-manager.service      active running Greg's Ollama Manager UI
```

## Major changes completed this session

### 1. External/systemd ports can load models from the Manager UI

Problem solved:

- External/systemd Ollama ports appeared in the UI but originally did not expose a reliable Load path.
- The Manager's load logic needed to handle ports that are bound/reachable even if they are not in the internal `instances` process registry.

Backend route used:

```text
POST /api/instances/{port}/load
```

Current behavior:

- Checks whether the target port is bound/reachable.
- Rejects if the port is already loading or pulling.
- Starts a background model-load task using Ollama `/api/generate` with `keep_alive: -1`.

### 2. Target-port-aware model catalog

Problem solved:

- The Load Model dropdown used to be misleading because it effectively reflected `11434` rather than the selected target port.

Current routes:

```text
GET /api/models?port=<port>
GET /api/instances/{port}/models
```

Current behavior:

- Collects installed models by port.
- Merges models from discovered Ollama ports and curated pull candidates.
- Marks each option as either:

```text
installed
needs_pull
```

Example on target port `11437`:

```text
gemma4:e4b — installed
llama3.2:3b — installed
fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b — needs pull
llama2-uncensored:latest — needs pull
qwen2.5:7b — needs pull
qwen2.5:32b — needs pull
```

### 3. Pull button added to Load Model modal

The Load Model modal now has:

```text
Pull custom model
[input]
↓ Pull
```

Route:

```text
POST /api/instances/{port}/pull
```

Behavior:

- Pulls into the selected target port, not always `11434`.
- Validates model names with a conservative regex.
- Selecting a `needs pull` model auto-fills the pull input.
- The Load button is disabled for models not installed on the selected target.

Validation example that was tested:

```text
POST /api/instances/11437/pull
{"model":"bad model"}
```

Expected/observed response:

```text
400
{"detail":"Invalid model name"}
```

### 4. Visible loading feedback / spinner added

Greg requested visible surface feedback when loading a model.

Frontend file changed:

```text
/home/greg/ollama-project/static/index.html
```

Current UI behavior when clicking Load:

- Modal stays open.
- Load button changes to a spinner state:

```text
Loading
```

- A yellow status box appears:

```text
Loading <model> on :<port>… This can take a moment.
```

- Load modal controls are disabled during the load:
  - model dropdown
  - pull input
  - Pull button
  - Load button
  - Cancel button

- The UI polls `/api/instances` until the target model is loaded or an error appears.
- On success, the modal closes and a success toast appears.

Backend support added:

- `port_targets: dict[int, str | None]`
- External/systemd discovered instances can now report:

```text
status: loading
target_model: <model being loaded>
```

This allows external ports to show loading feedback just like Manager-created ports.

### 5. Broken direct Hugging Face Qwen3.5 import removed

Removed broken model from the main instance:

```text
hf.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive:Q4_K_M
```

Reason:

- It appeared to pull/install, but runtime generation failed.
- Prior investigation suggested raw HF GGUF import had architecture/metadata problems for `qwen35`.
- The Ollama-library packaged model works instead:

```text
fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b
```

This working packaged version remains installed and loaded on `11434`.

## Files changed

Primary changed files:

```text
/home/greg/ollama-project/main.py
/home/greg/ollama-project/static/index.html
/home/greg/ollama-project/tests/test_model_catalog.py
```

Observed file stats near handoff:

```text
/home/greg/ollama-project/main.py                  21159 bytes
/home/greg/ollama-project/static/index.html       48547 bytes
/home/greg/ollama-project/tests/test_model_catalog.py 1977 bytes
```

## Tests / verification commands

Use the project venv:

```bash
cd /home/greg/ollama-project
.venv/bin/python -m py_compile main.py
.venv/bin/python -m unittest tests.test_model_catalog -v
```

Expected test result:

```text
test_catalog_marks_models_not_on_target_as_needs_pull ... ok
test_catalog_marks_target_installed_models ... ok
test_model_names_are_restricted_for_pull_endpoint ... ok

Ran 3 tests
OK
```

JavaScript syntax check used:

```bash
cd /home/greg/ollama-project
python3 - <<'PY'
from pathlib import Path
import re
html=Path('static/index.html').read_text()
m=re.search(r'<script>(.*?)</script>', html, re.S)
Path('/tmp/ollama-manager-ui.js').write_text(m.group(1) if m else '')
PY
node --check /tmp/ollama-manager-ui.js
```

Expected result: no syntax errors.

Restart command:

```bash
sudo systemctl restart ollama-manager.service
systemctl is-active ollama-manager.service
```

Expected result:

```text
active
```

Browser verification performed:

- Opened `http://127.0.0.1:8000/`.
- Confirmed all four ports appear.
- Confirmed Load modal opens.
- Confirmed target-port model catalog appears.
- Confirmed loading status element exists.
- Simulated busy state and verified spinner/status text:

```text
Loading llama3.2:3b on :11437… This can take a moment.
```

- Confirmed browser console had no JavaScript errors.

## Backups created before major edits

Backups are in:

```text
/home/greg/ollama-project-backups/
```

Known backups from this session:

```text
/home/greg/ollama-project-backups/ollama-project-20260606-170931.tar.gz
SHA256: 0c4588e81f16dcd59a7e73557b5c181e1450754219d83b7af8b49fe7af6871d6

/home/greg/ollama-project-backups/ollama-project-20260606-191856.tar.gz
SHA256: aaa8937d750ec59d34f13524c172a29d38ed139b6a1aa7b7520d478abcb6824d

/home/greg/ollama-project-backups/ollama-project-20260606-195254.tar.gz
SHA256: d9ed8763d37fd54106a5a375d3e27e703198f4ea02a533584a37b67ae662b4d2
```

The latest backup before the loading-spinner changes is:

```text
/home/greg/ollama-project-backups/ollama-project-20260606-195254.tar.gz
```

Rollback example:

```bash
cd /home/greg
sudo systemctl stop ollama-manager.service
mv /home/greg/ollama-project /home/greg/ollama-project-bad-$(date +%Y%m%d-%H%M%S)
tar -xzf /home/greg/ollama-project-backups/ollama-project-20260606-195254.tar.gz
sudo systemctl start ollama-manager.service
systemctl is-active ollama-manager.service
```

## Hardware/concurrency notes from this session

Giga-Brain hardware summary relevant to Ollama:

```text
CPU: 2 × Intel Xeon E5-2690
Physical cores: 16
Threads: 32
RAM: 110 GiB
GPU inference: effectively unavailable / nvidia-smi unavailable
```

Four loaded Q4-class models are memory-safe.

Observed earlier with four loaded models:

```text
RAM total: ~110 GiB
RAM used: ~19 GiB
RAM available: ~90 GiB
Swap used: 0
```

Concurrency guidance:

- Many models can be resident.
- CPU inference is the bottleneck.
- Recommended active inference concurrency:

```text
1 active model: smooth
2 active models: good
3 active models: usable but slower
4 active models: possible, stress territory
5+ active generations: likely too much without thread throttling
```

Recommended agentic workflow pattern:

```text
Use one stronger coordinator/reviewer model.
Use several 3B-ish worker models for narrow tasks.
Queue many jobs, but allow only 2-3 simultaneous model generations.
```

## The “soul file” question

Greg asked:

```text
so what is wrong with the soul file again? explain that to me?
```

A session search was run for:

```text
"soul file" OR soul
```

Result:

```text
No matching sessions found.
```

Therefore, do **not** assume which file Greg means in a new session. Ask Greg to identify the soul file path/name, or search the filesystem if he wants the assistant to locate candidate files.

Possible next-step commands if asked to investigate:

```bash
# Use Hermes search_files rather than shell find when possible.
# Search file names for soul-related candidates under likely project roots.
```

No conclusion about the soul file has been established yet.

## Important caution for new session

- Treat `/home/greg/ollama-project` as production-adjacent. Create a rollback backup before further edits.
- The Manager UI is systemd-managed and should be restarted via:

```bash
sudo systemctl restart ollama-manager.service
```

- Do not confuse external/systemd Ollama ports with Manager-created child processes.
- External/systemd ports are expected and healthy on 11434-11437.
- Avoid leaving temporary Manager-created instances running on extra ports unless Greg explicitly asks for them.

## Quick health-check script for next session

```bash
cd /home/greg/ollama-project
systemctl is-active ollama-manager.service
curl -sS --max-time 5 http://127.0.0.1:8000/api/instances | python3 -m json.tool
.venv/bin/python -m py_compile main.py
.venv/bin/python -m unittest tests.test_model_catalog -v
```

## Human summary

The Ollama Manager is in good shape. The UI can discover four external systemd Ollama instances, load/unload models on those ports, show target-port-specific installed/needs-pull status, pull models into the selected target port, and now display a visible spinner/status while a model is loading.

The only unresolved user question is the “soul file”; no matching past-session context was found, so the next session should ask Greg for the file path or perform a file search.
