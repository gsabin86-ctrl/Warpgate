# Warpgate

Warpgate is the control panel for routing, loading, and managing local AI models across Greg's Ollama cluster on Giga-Brain.

It provides a clean web UI to:

- View all detected Ollama inference nodes by port.
- See service status, uptime, host, and loaded models.
- Load and unload models on specific Ollama instances.
- Browse installed models and identify whether a model is ready to load or needs pulling.
- Pull models into the local cluster.
- Chat/test models directly from the interface.
- Monitor lightweight system telemetry in a Hermes-style sidebar.

## Current runtime

- FastAPI app: `main.py`
- Static UI: `static/index.html`
- Service: `ollama-manager.service`
- Default URL: `http://127.0.0.1:8000/`

## Development commands

```bash
cd /home/greg/ollama-project
python3 -m unittest discover -s tests -v
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The deployed service uses the project virtual environment and is managed by systemd.

```bash
sudo systemctl restart ollama-manager.service
sudo systemctl status ollama-manager.service --no-pager
```

## Rollback hygiene

See the rollback runbook:

```text
docs/rollback.md
```

This repository is intentionally committed in small rollback points:

1. Baseline import of the known-working manager.
2. Documentation/runbook changes.
3. UI-only visual changes.
4. Backend/API changes only when needed.

Rollback to a previous local commit:

```bash
cd /home/greg/ollama-project
git log --oneline
git checkout <commit>
sudo systemctl restart ollama-manager.service
```

A tarball backup should also be created before major local UI or backend changes under:

```text
/home/greg/ollama-project-backups/
```
