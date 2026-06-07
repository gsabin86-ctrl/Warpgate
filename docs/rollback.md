# Warpgate rollback runbook

This runbook keeps Warpgate usable while changes are in progress.

## Stable baseline

Current verified stable tag:

```text
stable-2026-06-07-warpgate-baseline
```

Current verified stable commit:

```text
c1e805ff62c53eb778484a7a364b28ed58a4813d
```

Local tarball backup created on Giga-Brain:

```text
/home/greg/warpgate-backups/warpgate-stable-20260607-151238-c1e805f.tar.gz
```

SHA256:

```text
9a5667fe6d9e3a3ff36e090e0fd38ed72d83481697e5b25dba6126cdd69193a4
```

## Before making risky changes

1. Confirm the working tree is clean:

```bash
cd /home/greg/ollama-project
git status --short --branch
```

2. Run tests:

```bash
cd /home/greg/ollama-project
.venv/bin/python -m unittest discover -s tests -v
```

3. Create a fresh tarball backup:

```bash
cd /home/greg
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p /home/greg/warpgate-backups
tar --exclude='./.git' --exclude='./.venv' --exclude='./__pycache__' --exclude='./.pytest_cache' --exclude='./.hermes' \
  -czf "/home/greg/warpgate-backups/warpgate-prechange-${STAMP}.tar.gz" \
  -C /home/greg/ollama-project .
sha256sum "/home/greg/warpgate-backups/warpgate-prechange-${STAMP}.tar.gz" \
  > "/home/greg/warpgate-backups/warpgate-prechange-${STAMP}.tar.gz.sha256"
```

4. Prefer branch-based work for larger changes:

```bash
cd /home/greg/ollama-project
git checkout -b feature/<short-description>
```

## Fast rollback to the stable git tag

Use this when the service still starts but the latest code is bad.

```bash
cd /home/greg/ollama-project
git fetch --tags origin
git checkout main
git reset --hard stable-2026-06-07-warpgate-baseline
sudo systemctl restart ollama-manager.service
systemctl is-active ollama-manager.service
curl -fsS http://127.0.0.1:8000/api/instances
```

If you want the remote `main` branch rolled back too, push only after confirming locally:

```bash
git push --force-with-lease origin main
```

## Restore from local tarball backup

Use this if the working tree is badly broken or git state is confusing.

```bash
sudo systemctl stop ollama-manager.service
cd /home/greg
mv /home/greg/ollama-project "/home/greg/ollama-project-broken-$(date +%Y%m%d-%H%M%S)"
mkdir -p /home/greg/ollama-project
tar -xzf /home/greg/warpgate-backups/warpgate-stable-20260607-151238-c1e805f.tar.gz \
  -C /home/greg/ollama-project
cd /home/greg/ollama-project
git init
git remote add origin git@github.com:gsabin86-ctrl/Warpgate.git
git fetch origin main --tags
git reset --hard stable-2026-06-07-warpgate-baseline
sudo systemctl start ollama-manager.service
systemctl is-active ollama-manager.service
curl -fsS http://127.0.0.1:8000/api/instances
```

## Live functionality checks

After rollback or deployment, verify:

```bash
systemctl is-active ollama-manager.service
curl -fsS http://127.0.0.1:8000/ -o /tmp/warpgate.html
python3 - <<'PY'
from pathlib import Path
html = Path('/tmp/warpgate.html').read_text()
for needle in ['<title>Warpgate</title>', 'Warpgate Control', 'loadModel']:
    print(f'{needle}: {needle in html}')
PY
curl -fsS http://127.0.0.1:8000/api/instances
```

Expected current stable cluster shape:

```text
ports: 11434, 11435, 11436, 11437
service: active
```

## Commit discipline

- Keep `main` working.
- Commit small checkpoints.
- Push only after tests and live verification pass.
- Use tags for known-good stable points.
- Keep local tarball backups before major UI/backend refactors.
