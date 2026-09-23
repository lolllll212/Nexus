"""HOLO deck API - the hand-gesture UI's own endpoints, served by NEXUS.

These mirror what ``frontend/server.py`` (the standalone stdlib server)
provides, so the deck behaves identically whether it is opened from the
NEXUS backend (mounted at ``/``) or from ``python3 frontend/server.py``.
Pure local file I/O - no ports required - so these are public read/write
of the user's own notes folder and deck state, exactly like the standalone
server on localhost.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Body

from nexus.infrastructure.api.paths import frontend_dir

router = APIRouter(prefix="/api", tags=["holo"])

_NOTE_EXTS = (".md", ".txt")


def _notes_dir() -> str | None:
    """Notes folder from ``frontend/holo.json`` (falls back to sample-notes)."""
    root = frontend_dir()
    if root is None:
        return None
    try:
        cfg = json.loads((root / "holo.json").read_text(encoding="utf-8"))
        d = os.path.expanduser(str(cfg.get("folder", "")))
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    sample = root / "sample-notes"
    return str(sample) if sample.is_dir() else None


def _note(path: str, name: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    title = (lines[0].lstrip("# ").strip() if lines else name)[:48] or name
    rest = [ln for ln in lines[1:] if not ln.startswith("#")]
    return {
        "name": name,
        "title": title,
        "body": "\n".join(rest)[:420],
        "full": "\n".join(lines[1:])[:4000],
    }


def _load_notes(limit: int = 18) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    d = _notes_dir()
    if not d:
        return out
    try:
        for n in sorted(x for x in os.listdir(d) if x.endswith(_NOTE_EXTS))[:limit]:
            note = _note(os.path.join(d, n), n)
            if note:
                out.append(note)
    except OSError:
        pass
    return out


def _load_tree(limit_files: int = 14) -> list[dict[str, Any]]:
    """One level deep: subfolders become ORBS; loose files gather under NOTES."""
    d = _notes_dir()
    tree: list[dict[str, Any]] = []
    if not d:
        return tree
    try:
        loose: list[dict[str, Any]] = []
        for e in sorted(os.listdir(d)):
            p = os.path.join(d, e)
            if os.path.isdir(p) and not e.startswith("."):
                files = []
                for n in sorted(x for x in os.listdir(p) if x.endswith(_NOTE_EXTS))[:limit_files]:
                    note = _note(os.path.join(p, n), n)
                    if note:
                        files.append(note)
                if files:
                    tree.append({"kind": "folder", "name": e.upper()[:22], "files": files})
            elif e.endswith(_NOTE_EXTS):
                note = _note(p, e)
                if note:
                    loose.append(note)
        if loose:
            tree.append({"kind": "folder", "name": "NOTES", "files": loose[:limit_files]})
    except OSError:
        pass
    return tree


@router.get("/notes")
async def get_notes() -> list[dict[str, Any]]:
    return _load_notes()


@router.get("/tree")
async def get_tree() -> list[dict[str, Any]]:
    return _load_tree()


@router.get("/props")
async def get_props() -> list[str]:
    """Any .glb dropped into ``frontend/props/`` becomes a grabbable 3D object."""
    root = frontend_dir()
    if root is None:
        return []
    try:
        return sorted(x for x in os.listdir(root / "props") if x.endswith(".glb"))[:6]
    except OSError:
        return []


def _diag_file() -> str | None:
    root = frontend_dir()
    if root is None:
        return None
    try:
        os.makedirs(root / "state", exist_ok=True)
    except OSError:
        return None
    return str(root / "state" / "holo-diag.json")


def _write_diag(data: dict[str, Any]) -> None:
    path = _diag_file()
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


@router.post("/diag")
async def post_holo_diag(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """The deck phones home its own crash report (as in the standalone server)."""
    data = dict(payload or {})
    data["ts"] = time.time()
    await asyncio.to_thread(_write_diag, data)
    return {"ok": True}


def _state_file() -> str | None:
    root = frontend_dir()
    if root is None:
        return None
    try:
        os.makedirs(root / "state", exist_ok=True)
    except OSError:
        return None
    return str(root / "state" / "holo-state.json")


def _read_state() -> dict[str, Any]:
    path = _state_file()
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state_atomic(data: dict[str, Any]) -> None:
    path = _state_file()
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        pass


@router.get("/state")
async def get_holo_state() -> dict[str, Any]:
    return await asyncio.to_thread(_read_state)


@router.post("/state")
async def post_holo_state(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """The deck reports what the hands did ('Card pinned, sir').

    Written atomically so any other process (the big brain) can react to
    gestures. Same semantics as the standalone server's /api/state.
    """
    data = dict(payload or {})
    data["ts"] = time.time()
    await asyncio.to_thread(_write_state_atomic, data)
    return {"ok": True}
