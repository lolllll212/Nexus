"""Hologram props endpoints.

Lists the .glb props available for the holo.html 3D viewer. Blender-based
generation (services/blender_gen.py) is deliberately NOT included: Blender is
not installed on this machine, so a bpy-execution service could never be
tested here. Add it only when a local Blender (>= 4.0, background mode)
exists.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
PROPS_DIR = ROOT_DIR / "frontend" / "props"


@router.get("/api/holo/props")
async def api_holo_props():
    """List every .glb prop served under /props/ for the hologram viewer."""
    props = []
    if PROPS_DIR.is_dir():
        for child in sorted(PROPS_DIR.iterdir()):
            if child.suffix.lower() == ".glb" and child.is_file():
                props.append(
                    {
                        "name": child.stem,
                        "url": f"/props/{child.name}",
                        "bytes": child.stat().st_size,
                    }
                )
    return JSONResponse({"count": len(props), "props": props})
