# Archon / Ollama Manager

A local control panel for managing multiple Ollama instances on Giga-Brain.

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
