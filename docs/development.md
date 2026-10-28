# Nexus development guide

Nexus now has two separately loaded web surfaces. They share API utilities and
chat building blocks, but they do **not** mount each other:

| Surface | URL in dev | Entry HTML | React entry | Root component |
| --- | --- | --- | --- | --- |
| Workplace OS | `http://localhost:3000/` | `web/index.html` | `web/src/main.tsx` | `web/src/App.tsx` |
| Chat UI | `http://localhost:3000/chat.html` | `web/chat.html` | `web/src/chat-main.tsx` | `web/src/chat/ChatApp.tsx` |

The Chat UI controller lives in
`web/src/chat/useStandaloneChatController.ts`. It uses shared pieces
(`web/src/components/ClaudeChatWorkspace.tsx`, `web/src/api.ts`,
`web/src/utils/chatHistory.ts`, `web/src/data/modelCatalog.ts`, and
`web/src/utils/voiceManager.ts`) without importing the Workplace OS shell,
knowledge-graph state, HUD, or workspace navigation.

Workplace OS still links to Chat, but the link now navigates to `/chat.html`.
The full Claude-style chat workspace is no longer an internal Workplace OS
mode.

## One-command local stack

From the repo root:

```bash
bash scripts/dev.sh --setup   # first run: create .venv, install deps, start
bash scripts/dev.sh           # later runs: start API + bridge + Vite
```

The launcher starts:

- FastAPI API on `http://localhost:8000` (`/docs`, `/healthz`)
- IDE bridge on `ws://127.0.0.1:8765` (the browser connects through `/bridge`)
- Vite on `http://localhost:3000`
  - Workplace OS: `/`
  - Standalone Chat UI: `/chat.html`

Press `Ctrl+C` in that terminal to stop all three services.

## Manual setup

Use this if you prefer separate terminals or are debugging one service.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e . --no-deps
cd web && npm ci && cd ..
cp .env.example .env
```

API terminal:

```bash
PYTHONPATH=src \
NEXUS_INFRA_BACKEND=memory \
NEXUS_SANDBOX_BACKEND=subprocess \
NEXUS_LLM_PROVIDER=nvidia \
NEXUS_NIM_MODEL=meta/llama-3.3-70b-instruct \
NEXUS_HISTORY_PATH=data/chat_history.json \
NEXUS_WORKSPACE_ROOT="$PWD" \
NEXUS_API_KEYS='{"sk-local-dev":{"user_id":"dev","tenant_id":"default","role":"admin"}}' \
.venv/bin/python -m uvicorn nexus.infrastructure.api.main:app --host 0.0.0.0 --port 8000
```

Bridge terminal:

```bash
NEXUS_BRIDGE_TOKEN=bridge-test-token .venv/bin/python scripts/ide_bridge.py --port 8765 --poll 5
```

Web terminal:

```bash
cd web
VITE_BRIDGE_TOKEN=bridge-test-token npm run dev
```

Then open `http://localhost:3000/` for Workplace OS or
`http://localhost:3000/chat.html` for Chat.

## Environment notes

- Auth is fail-closed. The browser defaults to the local development key from
  `.env.example`; replace `NEXUS_API_KEYS` before any real deployment.
- With `NEXUS_LLM_PROVIDER=nvidia` and no live NVIDIA key available to the
  backend, model responses run in NVIDIA NIM simulation mode. Add a real key
  through the backend environment for live model calls.
- `NEXUS_HISTORY_PATH=data/chat_history.json` keeps backend chat history in a
  local ignored file. Delete that file if you want a clean local history.
- `NEXUS_WORKSPACE_ROOT` confines file/repository tools to the repo during
  local development.
- `NEXUS_INFRA_BACKEND=memory` avoids requiring Redis/Qdrant/Neo4j for local
  development. Use the external backend only when those services are running.

## Verification commands

Web:

```bash
cd web
npm run lint
npm run build
```

The production build emits both `index.html` (Workplace OS) and `chat.html`
(Chat UI) into `frontend/dist/`.

Python/API smoke checks after the stack is up:

```bash
curl http://127.0.0.1:8000/healthz
curl -H 'Authorization: Bearer sk-local-dev' http://127.0.0.1:3000/api/models
curl -H 'Authorization: Bearer sk-local-dev' http://127.0.0.1:3000/v1/tools
```

Focused backend tests can be run with the project virtualenv, for example:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_model_changer.py tests/unit/test_chat_history_api.py -q
```

## Troubleshooting

- **Only an old page loads after a sandbox reset:** rerun
  `bash scripts/dev.sh --setup`; sandboxes may delete `.venv` and
  `web/node_modules` while preserving source files.
- **401 errors in the browser:** refresh once. The web API client clears a
  stale browser-saved API key after a 401 and retries with the configured
  local development key.
- **Chat opens Workplace OS instead:** use `/chat.html`, not `/`. The root URL
  is intentionally Workplace OS.
- **Bridge shows waiting/auth errors:** start the bridge and make sure the web
  `VITE_BRIDGE_TOKEN` matches the bridge `NEXUS_BRIDGE_TOKEN`.
- **Port already in use:** stop the previous API/Vite/bridge process before
  starting a new stack.
