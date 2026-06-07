#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Ensure user-local packages are on the path
export PATH="$HOME/.local/bin:$PATH"

if ! python3 -c "import fastapi" &>/dev/null; then
  echo "Installing dependencies..."
  pip3 install --user --break-system-packages -r requirements.txt
fi

echo "Warpgate running at http://localhost:8000"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
