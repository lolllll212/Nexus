#!/usr/bin/env bash
# Nexus local development stack.
#
# Starts the three services used by the separated web surfaces:
#   - API (FastAPI)          http://localhost:8000/docs
#   - IDE bridge (WebSocket) ws://127.0.0.1:8765  (browser uses /bridge)
#   - Vite web dev server    http://localhost:3000/          -> Workplace OS
#                            http://localhost:3000/chat.html -> standalone Chat UI
#
# Usage:
#   bash scripts/dev.sh           # start stack (deps must already exist)
#   bash scripts/dev.sh --setup   # create .venv + npm ci, then start stack
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '\033[1;36m[nexus-dev]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[nexus-dev]\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${1:-}" == "--setup" ]]; then
  log "Setting up Python virtualenv (.venv) and web dependencies…"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m pip install -e . --no-deps
  (cd web && npm ci)
elif [[ "${1:-}" != "" ]]; then
  fail "Unknown argument: $1 (expected --setup or no argument)"
fi

[[ -x .venv/bin/python ]] || fail ".venv is missing. Run: bash scripts/dev.sh --setup"
[[ -d web/node_modules ]] || fail "web/node_modules is missing. Run: bash scripts/dev.sh --setup"
[[ -x web/node_modules/.bin/vite ]] || fail "Vite binary is missing. Run: bash scripts/dev.sh --setup"

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
export NEXUS_INFRA_BACKEND="${NEXUS_INFRA_BACKEND:-memory}"
export NEXUS_SANDBOX_BACKEND="${NEXUS_SANDBOX_BACKEND:-subprocess}"
export NEXUS_LLM_PROVIDER="${NEXUS_LLM_PROVIDER:-nvidia}"
export NEXUS_NIM_MODEL="${NEXUS_NIM_MODEL:-meta/llama-3.3-70b-instruct}"
export NEXUS_HISTORY_PATH="${NEXUS_HISTORY_PATH:-data/chat_history.json}"
export NEXUS_WORKSPACE_ROOT="${NEXUS_WORKSPACE_ROOT:-$ROOT_DIR}"
export NEXUS_BRIDGE_TOKEN="${NEXUS_BRIDGE_TOKEN:-bridge-test-token}"
export VITE_BRIDGE_TOKEN="${VITE_BRIDGE_TOKEN:-$NEXUS_BRIDGE_TOKEN}"

# Local-only development identities. Override NEXUS_API_KEYS in your shell or
# .env for anything beyond a private dev sandbox. (Keep this as an if-block:
# nested JSON braces inside ${VAR:-...} are parsed by Bash as brace matching.)
if [[ -z "${NEXUS_API_KEYS:-}" ]]; then
  export NEXUS_API_KEYS='{"sk-local-dev":{"user_id":"dev","tenant_id":"default","role":"admin"},"sk-test-1":{"user_id":"u1","tenant_id":"t1","role":"admin"}}'
fi

mkdir -p data

API_PID=""
BRIDGE_PID=""
WEB_PID=""

cleanup() {
  local status=$?
  log "Stopping Nexus dev stack…"
  for pid in "$WEB_PID" "$BRIDGE_PID" "$API_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

log "Starting API on http://localhost:8000 (docs: /docs)…"
.venv/bin/python -m uvicorn nexus.infrastructure.api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

log "Starting IDE bridge on ws://127.0.0.1:8765 (browser path: /bridge)…"
.venv/bin/python scripts/ide_bridge.py --port 8765 --poll 5 &
BRIDGE_PID=$!

log "Starting Vite on http://localhost:3000 …"
(cd web && exec ./node_modules/.bin/vite --host 0.0.0.0 --port 3000) &
WEB_PID=$!

cat <<URLS

Nexus development stack is starting:

  Workplace OS  http://localhost:3000/
  Chat UI       http://localhost:3000/chat.html
  API docs      http://localhost:8000/docs
  Health        http://localhost:8000/healthz

Press Ctrl+C to stop all services.
URLS

# If any long-lived service exits, shut the rest down instead of leaving a
# half-working stack behind.
wait -n "$API_PID" "$BRIDGE_PID" "$WEB_PID"
