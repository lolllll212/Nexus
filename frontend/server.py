#!/usr/bin/env python3
"""HOLO — hand-gesture control deck (Jarvis V7 prototype). Stdlib only, port 4890.

Serves the deck page + the note cards it manipulates. Hand tracking is Google
MediaPipe (Apache-2.0) loaded from CDN in the page; every gesture on top is ours,
written clean — no third-party gesture code. Camera frames never leave the page.

Endpoints:
  GET  /               → holo.html
  GET  /api/notes      → [{name, title, body}] from the folder in holo.json
                         (falls back to ./sample-notes so it runs instantly)
  POST /api/state      → future Jarvis hook: writes state/holo-state.json so the
                         big brain can react to what the hands did ("Card pinned,
                         sir"). Nothing reads it yet by design — prototype stays
                         standalone until proven.
"""
import json, os, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("HOLO_PORT", "4890"))
HOST = os.environ.get("HOLO_HOST", "127.0.0.1")
# NEXUS backend to proxy brain calls to (chat, cosmos, graph, analyze, llm status)
BACKEND = os.environ.get("NEXUS_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

# the page, cached at boot: long-lived processes on macOS can silently lose file
# access (TCC) hours in — serving the boot-time copy beats a 500 "missing" page
try:
    PAGE_CACHE = [open(os.path.join(ROOT, "holo.html"), "rb").read()]
except OSError:
    PAGE_CACHE = [None]

def notes_dir():
    try:
        cfg = json.load(open(os.path.join(ROOT, "holo.json")))
        d = os.path.expanduser(cfg.get("folder", ""))
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return os.path.join(ROOT, "sample-notes")

def _note(path, n):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return None
    lines = [l for l in text.splitlines() if l.strip()]
    title = (lines[0].lstrip("# ").strip() if lines else n)[:48] or n
    rest = [l for l in lines[1:] if not l.startswith("#")]
    return {"name": n, "title": title, "body": "\n".join(rest)[:420],
            "full": "\n".join(lines[1:])[:4000]}

def load_notes(limit=18):
    out = []
    d = notes_dir()
    try:
        for n in sorted(x for x in os.listdir(d) if x.endswith((".md", ".txt")))[:limit]:
            note = _note(os.path.join(d, n), n)
            if note: out.append(note)
    except OSError:
        pass
    return out

def load_tree(limit_files=14):
    """One level deep: subfolders become ORBS; loose root files gather under 'NOTES'."""
    d = notes_dir()
    tree = []
    try:
        entries = sorted(os.listdir(d))
        loose = []
        for e in entries:
            p = os.path.join(d, e)
            if os.path.isdir(p) and not e.startswith("."):
                files = []
                for n in sorted(x for x in os.listdir(p) if x.endswith((".md", ".txt")))[:limit_files]:
                    note = _note(os.path.join(p, n), n)
                    if note: files.append(note)
                if files:
                    tree.append({"kind": "folder", "name": e.upper()[:22], "files": files})
            elif e.endswith((".md", ".txt")):
                note = _note(p, e)
                if note: loose.append(note)
        if loose:
            tree.append({"kind": "folder", "name": "NOTES", "files": loose[:limit_files]})
    except OSError:
        pass
    return tree

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if ctype.startswith("text/html"):
            self.send_header("Cache-Control", "no-store")   # a stale cached page hid real fixes once
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    # ---- proxy to the NEXUS backend: brain endpoints the deck/cosmos page call ----
    def _proxy(self, method):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        body = self.rfile.read(n) if n > 0 else None
        req = urllib.request.Request(BACKEND + self.path, data=body, method=method)
        for k in ("Content-Type", "Authorization", "Accept"):
            if self.headers.get(k):
                req.add_header(k, self.headers[k])
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
                self._send(resp.status, data, resp.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as e:
            try:
                data = e.read()
            except Exception:
                data = json.dumps({"error": f"backend {e.code}"}).encode()
            self._send(e.code, data, e.headers.get("Content-Type", "application/json") if e.headers else "application/json")
        except Exception as e:
            self._send(502, {"error": f"NEXUS backend unreachable at {BACKEND}: {e}"})

    def _is_brain_path(self, p):
        """Paths owned by the NEXUS backend (everything else stays local)."""
        if p.startswith("/v1/"):
            return True
        if p.startswith(("/api/graph", "/api/analyze", "/api/cosmos", "/api/llm")):
            return True
        return False

    MIME = {".mjs": "text/javascript", ".js": "text/javascript",
            ".wasm": "application/wasm", ".task": "application/octet-stream",
            ".glb": "model/gltf-binary"}

    def do_GET(self):
        p = self.path.split("?")[0]
        if self._is_brain_path(p):
            return self._proxy("GET")
        if p in ("/cosmos", "/cosmos.html"):
            try:
                return self._send(200, open(os.path.join(ROOT, "cosmos.html"), "rb").read(),
                                  "text/html; charset=utf-8")
            except OSError:
                return self._send(404, {"error": "cosmos.html missing"})
        if p.startswith(("/config/", "/state/", "/assets/")):
            # static cosmos config + deck state + assets, served from the repo
            safe = os.path.normpath(p.lstrip("/"))
            if ".." not in safe:
                full = os.path.join(ROOT, safe)
                if os.path.isfile(full):
                    ext = os.path.splitext(full)[1]
                    ctype = {"json": "application/json", ".png": "image/png",
                             ".jpg": "image/jpeg"}.get(ext, "application/octet-stream")
                    if ext == ".json":
                        ctype = "application/json"
                    try:
                        return self._send(200, open(full, "rb").read(), ctype)
                    except OSError:
                        pass
            return self._send(404, {"error": "not found"})
        if p in ("/", "/holo.html"):
            try:
                body = open(os.path.join(ROOT, "holo.html"), "rb").read()
                PAGE_CACHE[0] = body
            except OSError:
                body = PAGE_CACHE[0]          # disk access lost (TCC) — serve the boot copy
            if body is None:
                return self._send(500, {"error": "holo.html missing"})
            return self._send(200, body, "text/html; charset=utf-8")
        if p == "/api/props":
            # PROPS: any .glb dropped into props/ becomes a grabbable 3D object
            try:
                names = sorted(x for x in os.listdir(os.path.join(ROOT, "props"))
                               if x.endswith(".glb"))[:6]
            except OSError:
                names = []
            return self._send(200, names)
        if p.startswith(("/vendor/", "/props/")):
            # self-hosted tracking libs: no CDN in the path, so ad-block extensions
            # and offline machines can't kill the hand tracking
            safe = os.path.normpath(p.lstrip("/"))
            if safe.startswith(("vendor", "props")) and ".." not in safe:
                full = os.path.join(ROOT, safe)
                if os.path.isfile(full):
                    ext = os.path.splitext(full)[1]
                    try:
                        return self._send(200, open(full, "rb").read(),
                                          self.MIME.get(ext, "application/octet-stream"))
                    except OSError:
                        pass
            return self._send(404, {"error": "not found"})
        if p == "/api/notes":
            return self._send(200, load_notes())
        if p == "/api/tree":
            return self._send(200, load_tree())
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path.split("?")[0]
        if self._is_brain_path(p):
            return self._proxy("POST")
        if p == "/api/diag":              # the page phones home its own crash report
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                data = {}
            data["ts"] = time.time()
            try:
                os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
                with open(os.path.join(ROOT, "state", "holo-diag.json"), "w") as f:
                    json.dump(data, f, indent=2)
            except OSError:
                pass
            return self._send(200, {"ok": True})
        if p != "/api/state":
            if p.startswith("/api/"):       # unknown /api — let the backend answer
                return self._proxy("POST")
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
        data["ts"] = time.time()
        try:
            os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
            tmp = os.path.join(ROOT, "state", ".holo-state.tmp")
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, os.path.join(ROOT, "state", "holo-state.json"))
        except OSError:
            pass
        return self._send(200, {"ok": True})

if __name__ == "__main__":
    print(f"HOLO deck on http://{HOST}:{PORT}  ·  notes: {notes_dir()}  ·  brain: {BACKEND}")
    print(f"COSMOS mesh on http://{HOST}:{PORT}/cosmos")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
