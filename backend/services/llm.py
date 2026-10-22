"""LLM service: config, provider state, health probe, and the unified call.

Extracted from backend/main.py (strangler refactor, Upgrade 1). All state here
is module-level so every router shares the same objects; callers should use
``llm_service._call_llm`` style access (or import this module) so tests can
monkeypatch the owning module.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

from nexus.infrastructure.adapters.llm.nvidia_nim_provider import (  # noqa: E402
    DEFAULT_NIM_BASE_URL,
    SUPPORTED_NIM_MODELS,
)


def _load_llm_config() -> dict[str, str]:
    """Read LLM settings from config/nexus.yaml then .env as fallback."""
    cfg: dict[str, str] = {}

    yaml_path = ROOT_DIR / "config" / "nexus.yaml"
    if yaml_path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            llm = raw.get("llm") or {}
            if isinstance(llm, dict):
                cfg["base_url"] = str(llm.get("base_url", ""))
                cfg["model"] = str(llm.get("model", ""))
                cfg["api_key"] = str(llm.get("api_key", ""))
        except Exception:
            pass

    cfg["base_url"] = os.getenv("NEXUS_LLM_BASE_URL", "") or cfg.get("base_url", "")
    cfg["model"] = os.getenv("NEXUS_LLM_MODEL", "") or cfg.get("model", "")
    cfg["api_key"] = os.getenv("OPENAI_API_KEY", "") or cfg.get("api_key", "")
    return cfg


LLM_CFG = _load_llm_config()

NIM_KEY_ENV_VARS = ("NEXUS_NIM_API_KEY", "NVIDIA_API_KEY", "NVAPI_KEY")
# Persisted state holds provider+model only - API keys never touch disk here.
LLM_STATE_PATH = BACKEND_DIR / "llm_state.json"

LLM_STATE: dict[str, str] = {
    "provider": "local",
    "model": LLM_CFG.get("model", ""),
    "api_key": next(
        (os.getenv(name, "").strip() for name in NIM_KEY_ENV_VARS if os.getenv(name, "").strip()),
        "",
    ),
}

if LLM_STATE_PATH.is_file():
    try:
        _saved_llm = json.loads(LLM_STATE_PATH.read_text(encoding="utf-8") or "{}")
        if _saved_llm.get("provider") in ("local", "nim"):
            LLM_STATE["provider"] = str(_saved_llm["provider"])
        if _saved_llm.get("model"):
            LLM_STATE["model"] = str(_saved_llm["model"])
    except Exception:
        pass


def _persist_llm_state() -> None:
    try:
        LLM_STATE_PATH.write_text(
            json.dumps({"provider": LLM_STATE["provider"], "model": LLM_STATE["model"]}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _nim_ready() -> bool:
    return bool(LLM_STATE["api_key"])


def _active_llm_target() -> tuple[str, str, str]:
    """Resolve (base_url, model, api_key) for the currently selected provider."""
    if LLM_STATE["provider"] == "nim" and _nim_ready():
        # EOL-proofing: a persisted id that NVIDIA retired (410/404) snaps to
        # the first verified catalog entry instead of failing every chat.
        nim_ids = {str(m["id"]) for m in SUPPORTED_NIM_MODELS}
        if LLM_STATE["model"] not in nim_ids:
            LLM_STATE["model"] = str(SUPPORTED_NIM_MODELS[0]["id"])
            _persist_llm_state()
        return DEFAULT_NIM_BASE_URL, LLM_STATE["model"], LLM_STATE["api_key"]
    model = (
        LLM_STATE["model"]
        if LLM_STATE["provider"] == "local" and LLM_STATE["model"]
        else LLM_CFG.get("model", "")
    )
    return LLM_CFG.get("base_url", "").rstrip("/"), model, LLM_CFG.get("api_key", "")


_LLM_LAST_CHECK = 0.0
_LLM_IS_ALIVE = False


async def _check_llm_alive() -> bool:
    """Fast probe with caching so offline LLM endpoints don't cause 10-second delays."""
    global _LLM_LAST_CHECK, _LLM_IS_ALIVE
    now = time.time()
    if (now - _LLM_LAST_CHECK) < 45.0:
        return _LLM_IS_ALIVE

    base, _model, key = _active_llm_target()
    if not base:
        _LLM_IS_ALIVE = False
        _LLM_LAST_CHECK = now
        return False

    import httpx

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    timeout = 3.0 if base.startswith("https://") else 0.8
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base}/models", headers=headers)
            _LLM_IS_ALIVE = resp.status_code == 200
    except Exception:
        _LLM_IS_ALIVE = False

    _LLM_LAST_CHECK = now
    return _LLM_IS_ALIVE


async def _call_llm(system: str, messages: list[dict[str, str]]) -> tuple[str, str]:
    """Call the active model. Returns (answer, reasoning) - reasoning may be ''.

    Reasoning-style NIM models stream their chain-of-thought in the separate
    ``reasoning_content`` field; ``content`` holds only the final answer.
    """
    import httpx

    base, model, key = _active_llm_target()

    if not base or not model:
        raise RuntimeError("LLM not configured")

    url = f"{base}/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        # Reasoning-style NIM models spend part of the budget thinking before
        # the final content lands - 4096 leaves room for the actual answer.
        "max_tokens": 4096 if LLM_STATE["provider"] == "nim" else 512,
        "temperature": 0.4,
    }

    # Cloud NIM models (70B+, reasoning traces) routinely exceed a few seconds;
    # a tight timeout silently degrades every chat to the canned fallback.
    llm_timeout = 120.0 if LLM_STATE["provider"] == "nim" else 30.0

    async with httpx.AsyncClient(timeout=llm_timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("No choices returned from LLM")
    msg = choices[0].get("message", {})
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or ""

    # Reasoning-heavy models can exhaust the whole budget while deliberating
    # and never emit content. One strict retry without deliberation rescues it.
    if not content.strip() and reasoning.strip():
        retry_payload = dict(payload)
        retry_payload["messages"] = [
            {"role": "system", "content": system},
            *messages,
            {
                "role": "system",
                "content": "IMPORTANT: Do not deliberate. Output only the final answer, immediately.",
            },
        ]
        retry_payload["max_tokens"] = min(payload["max_tokens"], 1024)
        async with httpx.AsyncClient(timeout=llm_timeout) as client:
            resp = await client.post(url, json=retry_payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "") or ""

    return content, reasoning


__all__ = [
    "DEFAULT_NIM_BASE_URL",
    "LLM_CFG",
    "LLM_STATE",
    "LLM_STATE_PATH",
    "SUPPORTED_NIM_MODELS",
    "_active_llm_target",
    "_call_llm",
    "_check_llm_alive",
    "_nim_ready",
    "_persist_llm_state",
]
