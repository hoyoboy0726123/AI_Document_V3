#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

log() {
  printf '\n[AI_Document_V3] %s\n' "$1"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: missing command '$1'" >&2
    exit 1
  }
}

log "Checking prerequisites"
need_cmd python3
need_cmd npm

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

log "Preparing backend"
cd "$BACKEND_DIR"
if [ ! -f .env ]; then
  cp .env_example .env
  echo "Created backend/.env from .env_example"
fi
uv sync

log "Preparing frontend"
cd "$FRONTEND_DIR"
npm install

cat <<'EOF'

Setup complete.

Next steps:
1. Edit backend/.env and set SECRET_KEY
2. Make sure Ollama is installed and running if you want embedding / RAG
3. Start backend:
   cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
4. Start frontend:
   cd frontend && npm run dev

Optional Docker compose:
   docker compose up --build
EOF
