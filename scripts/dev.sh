#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
test -d node_modules || npm ci
export DATABASE_URL="${DATABASE_URL:-sqlite:///./investoffice.db}"
export DEMO_MODE=true
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT
npm run dev
