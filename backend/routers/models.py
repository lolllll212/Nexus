"""Model registry endpoints: local <-> NVIDIA NIM switching."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.schemas import ModelSwitchRequest
from backend.services import llm as llm_service

router = APIRouter()

# ─── Model registry endpoints (local + NVIDIA NIM) ───────────────────────────


@router.get("/api/llm/models")
async def api_llm_models():
    """Switcher payload: local models (probed live) + the NVIDIA NIM catalog."""
    # Resolve (and EOL-snap) the active selection so the UI never shows a
    # retired model id after the catalog was refreshed.
    _active_base, active_model, _active_key = llm_service._active_llm_target()
    local_models: list[str] = []
    base = llm_service.LLM_CFG.get("base_url", "").rstrip("/")
    if base:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.5) as client:
                resp = await client.get(f"{base}/models")
                if resp.status_code == 200:
                    local_models = [m.get("id", "") for m in resp.json().get("data", []) if m.get("id")]
        except Exception:
            local_models = []
    return JSONResponse(
        {
            "active": {"provider": llm_service.LLM_STATE["provider"], "model": active_model},
            "local": {"base_url": base, "reachable": bool(local_models), "models": local_models},
            "nim": {"configured": llm_service._nim_ready(), "models": llm_service.SUPPORTED_NIM_MODELS},
        }
    )


@router.post("/api/llm/model")
async def api_llm_switch(req: ModelSwitchRequest):
    """Switch the active chat model between the local server and NVIDIA NIM."""
    provider = (req.provider or "").strip().lower()
    if provider not in ("local", "nim"):
        return JSONResponse({"ok": False, "error": "provider must be 'local' or 'nim'"}, status_code=400)
    if req.api_key:
        llm_service.LLM_STATE["api_key"] = req.api_key.strip()
    if provider == "nim" and not llm_service._nim_ready():
        return JSONResponse(
            {
                "ok": False,
                "needs_key": True,
                "error": "NVIDIA NIM needs an API key (starts with nvapi-).",
            },
            status_code=400,
        )
    if req.model.strip():
        llm_service.LLM_STATE["model"] = req.model.strip()
    if provider == "nim":
        # The carried-over local id is not valid on NIM - snap to the catalog.
        nim_ids = {str(m["id"]) for m in llm_service.SUPPORTED_NIM_MODELS}
        if llm_service.LLM_STATE["model"] not in nim_ids:
            llm_service.LLM_STATE["model"] = str(llm_service.SUPPORTED_NIM_MODELS[0]["id"])
    elif not llm_service.LLM_STATE["model"]:
        llm_service.LLM_STATE["model"] = llm_service.LLM_CFG.get("model", "")
    llm_service.LLM_STATE["provider"] = provider
    llm_service._persist_llm_state()

    reachable = False
    try:
        import httpx

        probe_base = (
            llm_service.DEFAULT_NIM_BASE_URL
            if provider == "nim"
            else llm_service.LLM_CFG.get("base_url", "").rstrip("/")
        )
        headers = {"Authorization": f"Bearer {llm_service.LLM_STATE['api_key']}"} if provider == "nim" else {}
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{probe_base}/models", headers=headers)
            reachable = resp.status_code == 200
    except Exception:
        reachable = False
    return JSONResponse(
        {
            "ok": True,
            "active": {"provider": provider, "model": llm_service.LLM_STATE["model"]},
            "reachable": reachable,
        }
    )
