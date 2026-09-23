#!/usr/bin/env python3
"""Mock LM Studio — a zero-dependency, OpenAI-compatible stand-in for demos.

Serves :1234 with /v1/models, /v1/chat/completions (always returns a ReAct-
style FINAL ANSWER echo), and /v1/embeddings. Lets you run the fully wired
NEXUS system (UI → chat → LLM) on a machine without a GPU/model:

    python scripts/mock_lm_studio.py &
    NEXUS_INFRA_BACKEND=memory \\
    NEXUS_LLM_BASE_URL=http://localhost:1234/v1 NEXUS_LLM_MODEL=qwen3.5-9b-mock \\
    NEXUS_BACKGROUND_LLM_BASE_URL=http://localhost:1234/v1 \\
    NEXUS_BACKGROUND_LLM_MODEL=qwen3.5-9b-mock OPENAI_API_KEY=local-no-key \\
    python -m uvicorn nexus.infrastructure.api.main:app --host 127.0.0.1 --port 8000

Stdlib only. Dev/demo tool — never used by the application itself.
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 0.0.0.0 so the sandbox preview proxy (and LAN) can see it too; loopback keeps working.
HOST = os.environ.get("MOCK_LM_HOST", "0.0.0.0")
PORT = int(os.environ.get("MOCK_LM_PORT", "1234"))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, obj, ctype="application/json"):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/api/v0/models"):
            return self._send(
                200,
                {
                    "object": "list",
                    "data": [{"id": "qwen3.5-9b-mock", "object": "model", "owned_by": "mock-lm-studio"}],
                },
            )
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        path = self.path.rstrip("/")
        if path == "/v1/embeddings":
            inputs = body.get("input", "")
            k = len(inputs) if isinstance(inputs, list) else 1
            return self._send(
                200,
                {
                    "object": "list",
                    "model": body.get("model", "mock-embed"),
                    "data": [
                        {"object": "embedding", "index": i, "embedding": [0.01] * 384}
                        for i in range(max(1, k))
                    ],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        if path == "/v1/chat/completions":
            msgs = body.get("messages", [])
            last = next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), "")
            content = (
                "FINAL ANSWER: (mock LM Studio) Wiring confirmed — I heard: "
                f"\u201c{last[:120]}\u201d. Point NEXUS_LLM_BASE_URL at a real LM Studio "
                "for genuine answers; the full loop (UI → /v1/chat → LLM) is live."
            )
            return self._send(
                200,
                {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body.get("model", "qwen3.5-9b-mock"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
            )
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"mock LM Studio on http://127.0.0.1:{PORT}/v1 (listening on {HOST}:{PORT})")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
