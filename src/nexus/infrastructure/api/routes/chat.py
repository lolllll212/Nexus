"""
Chat API - the conscious loop's entry point.

This layer is a THIN adapter. It parses HTTP, calls the ProcessMessage
use case, and serializes the result. Zero business logic lives here.

Identity comes from the verified bearer token (dependencies.require_identity);
the body no longer accepts a client-supplied user_id.

Multimodal (P3):
  - `image_urls`: attached to the user turn as vision content blocks.
  - `audio`: a base64 data URI (`data:audio/<mime>;base64,...`) transcribed via
    the SpeechToText adapter and used as (or prefixed to) the message text.
  - `voice`: when set, the response is synthesized to speech via TextToSpeech
    and returned as an audio data URI.

Model changer + Claude-style capabilities:
  - `model`: `"auto"` (default) uses the configured cortex LLM. Any NVIDIA
    NIM model id from `GET /api/models` runs THIS request on a fresh provider
    instance bound to that model — the shared container provider is never
    mutated, so concurrent requests cannot bleed models into each other.
  - `extended_thinking`: instructs step-by-step reasoning and returns the
    `thinking` trace (streamed as `thought` events on the SSE endpoint).
  - `deep_research`: multi-source, evidence-citing research behaviour.
  - `artifacts`: deliverables (code/documents) rendered as artifacts.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from nexus.domain.value_objects.coding_excellence import (
    CODING_FOCUSES,
    LANGUAGE_PLAYBOOKS,
    normalize_coding_focus,
)
from nexus.domain.value_objects.execution_quality import (
    ExecutionProfile,
    build_execution_profile,
    normalize_effort,
)
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.adapters.execution.extended_tools import set_execution_context
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import (
    SUPPORTED_NIM_MODELS,
    NvidiaNimProvider,
)
from nexus.infrastructure.api.dependencies import (
    get_container,
    require_identity,
    require_quota,
    require_rate_limit,
)
from nexus.infrastructure.di.container import Container

router = APIRouter(
    prefix="/v1/chat",
    tags=["chat"],
    dependencies=[
        Depends(require_identity),
        Depends(require_rate_limit("chat")),
        Depends(require_quota("chat")),
    ],
)


def _set_tool_execution_context(identity: Identity) -> None:
    """Bind tool approval checks to the authenticated caller, never the prompt."""
    role = getattr(identity.role, "value", identity.role)
    set_execution_context(
        {"tenant_id": identity.tenant_id, "actor": identity.user_id, "role": str(role)}
    )


class ChatRequest(BaseModel):
    message: str = Field("", min_length=0)
    session_id: str | None = None
    stream: bool = False
    image_urls: list[str] | None = None
    audio: str | None = None  # data URI: data:audio/<mime>;base64,...
    voice: str | None = None
    mode: str = "general"  # general, coding, or a coding-focus id
    coding_focus: Literal[
        "auto",
        "frontend",
        "c",
        "cpp",
        "rust",
        "python",
        "php",
        "html5",
        "xml",
        "ruby",
        "c++",
        "html",
        "front-end",
        "ui",
        "py",
        "rs",
        "rb",
    ] = "auto"
    # ── Model changer + capabilities ──────────────────────────────────────
    model: str | None = None  # "auto" or a NVIDIA NIM model id (GET /api/models)
    effort: Literal["auto", "fast", "balanced", "deep", "max"] = "auto"
    extended_thinking: bool = False
    deep_research: bool = False
    artifacts: bool = True


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tools_used: list
    memories_recalled: int
    thought_count: int
    audio: str | None = None  # data URI of synthesized speech (P3)
    model: str | None = None  # model that actually answered
    model_source: str | None = None  # "nexus-default" | "nvidia-nim"
    provider_status: str | None = None  # "live" | "simulation" | "configured"
    thinking: list[str] = []  # reasoning trace (extended_thinking only)
    response_id: str | None = None  # stable ID for /api/ai/feedback
    guardrail: dict[str, Any] | None = None  # safe input/output policy metadata
    context_sources: list[dict[str, Any]] = Field(default_factory=list)  # cited evidence provenance
    execution: dict[str, Any] | None = None  # adaptive effort/evidence profile
    quality: dict[str, Any] | None = None  # deterministic final-answer quality verdict
    coding: dict[str, Any] | None = None  # frontend/polyglot specialist profile


def _parse_data_uri(data_uri: str) -> tuple[str, bytes]:
    """Split `data:<mime>;base64,<payload>` into (mime, bytes)."""
    head, _, payload = data_uri.partition(",")
    mime = head.removeprefix("data:").split(";")[0] or "audio/mpeg"
    return mime, base64.b64decode(payload, validate=True)


def _to_data_uri(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


# ── Model changer ───────────────────────────────────────────────────────── #

_NIM_MODEL_IDS = {m["id"] for m in SUPPORTED_NIM_MODELS}


def _nim_provider_status(provider) -> str:
    return "live" if bool(getattr(provider, "has_api_key", False)) else "simulation"


def _execution_config(container: Container) -> dict[str, Any]:
    config = getattr(container, "ai_execution_config", None)
    return dict(config) if isinstance(config, dict) else {}


def _request_effort(container: Container, req: ChatRequest) -> str:
    """Resolve request effort, falling back to the operator's default."""

    requested = normalize_effort(req.effort)
    if requested != "auto":
        return requested
    return normalize_effort(str(_execution_config(container).get("default_effort", "auto")))


def _request_coding_focus(req: ChatRequest) -> str:
    """Resolve the canonical frontend/language focus for one chat request."""

    focus = normalize_coding_focus(req.coding_focus)
    if focus != "auto":
        return focus
    return normalize_coding_focus(req.mode)


def _request_mode(req: ChatRequest) -> str:
    """Return the effective cortex mode after applying coding focus."""

    focus = _request_coding_focus(req)
    if focus in CODING_FOCUSES and focus != "auto":
        return focus
    mode = str(req.mode or "general").strip().lower()
    return mode if mode in {"general", "coding"} else "general"


def _result_coding(result: Any) -> dict[str, Any] | None:
    execution = getattr(result, "execution", None)
    if isinstance(execution, dict) and isinstance(execution.get("coding"), dict):
        return execution["coding"]
    return None


def _fresh_nim_provider(nim: Any, model_id: str) -> NvidiaNimProvider:
    return NvidiaNimProvider(
        api_key=getattr(nim, "_api_key", "") if nim is not None else "",
        model=model_id,
        temperature=getattr(nim, "_temperature", 0.5) if nim is not None else 0.5,
        base_url=getattr(nim, "base_url", None) if nim is not None else None,
        default_max_tokens=getattr(nim, "_default_max_tokens", 4096) if nim is not None else 4096,
    )


def _select_auto_nim_model(profile: ExecutionProfile, current_model: str | None) -> str | None:
    """Choose a NIM model whose catalog strengths match the work profile."""

    catalog = list(SUPPORTED_NIM_MODELS)

    def string_set(entry: dict[str, Any], key: str) -> set[str]:
        value = entry.get(key)
        return {str(item) for item in value} if isinstance(value, list) else set()

    def find(*, capability: str | None = None, tag: str | None = None, speed: str | None = None):
        for entry in catalog:
            capabilities = string_set(entry, "capabilities")
            tags = string_set(entry, "tags")
            if "tool_use" not in capabilities:
                continue
            if capability and capability not in capabilities:
                continue
            if tag and tag not in tags:
                continue
            if speed and entry.get("speed") != speed:
                continue
            return str(entry["id"])
        return None

    if profile.has_images:
        return find(capability="vision") or current_model
    coding_profile = getattr(profile, "coding_profile", None)
    if coding_profile is not None and getattr(coding_profile, "is_coding", False):
        if profile.effective_effort in {"deep", "max"}:
            return (
                find(capability="code", tag="flagship")
                or find(capability="code")
                or find(tag="flagship")
                or find(speed="deep")
                or current_model
            )
        if profile.effective_effort == "fast":
            return find(capability="code", speed="fastest") or find(speed="fastest") or current_model
        current = next((entry for entry in catalog if entry.get("id") == current_model), None)
        if current and "code" in string_set(current, "capabilities"):
            return str(current["id"])
        return find(capability="code") or find(tag="default") or current_model
    if profile.effective_effort == "max":
        return find(tag="flagship") or find(speed="deep") or current_model
    if profile.effective_effort == "deep":
        return find(tag="flagship") or find(speed="deep") or current_model
    if profile.effective_effort == "fast":
        return find(speed="fastest") or current_model

    current = next((entry for entry in catalog if entry.get("id") == current_model), None)
    if current and "tool_use" in string_set(current, "capabilities"):
        return str(current["id"])
    return find(tag="default") or current_model


def _resolve_request_llm(
    container: Container,
    model_id: str | None,
    *,
    message: str = "",
    effort: str = "auto",
    mode: str = "general",
    extended_thinking: bool = False,
    deep_research: bool = False,
    has_images: bool = False,
):
    """Resolve the model changer's selection for one request.

    Returns ``(llm_override, model_label, model_source, provider_status)``.
    ``llm_override=None`` means "use the container's configured cortex LLM".
    A NIM selection builds a NEW provider bound to that model (copying the
    shared provider's credentials/endpoint) — the shared instance is never
    mutated, unlike the legacy nim.py per-request override pattern.

    In Auto mode on a NIM-backed cortex, the execution profile chooses
    between fast, balanced, deep/flagship, and vision catalog entries.  An
    explicit model selection always wins over adaptive routing.
    """
    nim = getattr(container, "nim_provider", None)
    requested = (model_id or "auto").strip()

    if requested in ("", "auto"):
        label = (
            getattr(getattr(container, "llm", None), "model", None)
            or getattr(nim, "model", None)
            or "auto"
        )
        if nim is not None and getattr(container, "llm", None) is nim:
            status = _nim_provider_status(nim)
            profile = build_execution_profile(
                message,
                requested_effort=effort,
                mode=mode,
                extended_thinking=extended_thinking,
                deep_research=deep_research,
                has_images=has_images,
            )
            selected = _select_auto_nim_model(profile, getattr(nim, "model", None))
            if selected and selected != getattr(nim, "model", None):
                provider = _fresh_nim_provider(nim, selected)
                return provider, selected, "nexus-auto", _nim_provider_status(provider)
            return None, label, "nexus-default", status
        return None, label, "nexus-default", "configured"

    if requested not in _NIM_MODEL_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{requested}'. Use GET /api/models to list selectable models.",
        )

    provider = _fresh_nim_provider(nim, requested)
    return provider, requested, "nvidia-nim", _nim_provider_status(provider)


def _capability_system_prompt(
    base_prompt: str | None,
    req: ChatRequest,
    *,
    effort: str = "auto",
) -> str | None:
    """Translate Claude-style capability toggles into prompt instructions."""
    instructions: list[str] = []
    normalized_effort = normalize_effort(effort)
    if normalized_effort == "fast":
        instructions.append(
            "EXECUTION EFFORT — FAST: Be direct and economical. Use a tool only "
            "when it is necessary for correctness, then answer without filler."
        )
    elif normalized_effort == "deep":
        instructions.append(
            "EXECUTION EFFORT — DEEP: Work like a senior operator: decompose the "
            "job, gather evidence, consider edge cases, verify the result, and "
            "make every completion claim auditable."
        )
    elif normalized_effort == "max":
        instructions.append(
            "EXECUTION EFFORT — MAX: Use the strongest available execution path. "
            "Plan the workstreams, cross-check important claims, use tools for "
            "evidence and actions, run verification, and do a final self-audit "
            "against every constraint before answering."
        )
    elif normalized_effort == "balanced":
        instructions.append(
            "EXECUTION EFFORT — BALANCED: Be thorough where correctness or work "
            "completion depends on it, and concise everywhere else."
        )
    coding_focus = _request_coding_focus(req)
    if coding_focus == "frontend":
        instructions.append(
            "CODING FOCUS — FRONTEND/CLEAN UI: Design with tokens, clear hierarchy, "
            "semantic landmarks, labelled controls, visible focus, responsive layout, "
            "and complete loading/empty/error/success states. Verify frontend_quality "
            "and the relevant typecheck/build after changes."
        )
    elif coding_focus in LANGUAGE_PLAYBOOKS:
        playbook = LANGUAGE_PLAYBOOKS[coding_focus]
        instructions.append(
            f"CODING FOCUS — {playbook.label}: Use {playbook.standard}. "
            + "Apply these priorities: "
            + "; ".join(playbook.principles[:2])
            + ". Verify with: "
            + ", ".join(playbook.verification_checks)
            + "."
        )
    if req.extended_thinking:
        instructions.append(
            "EXTENDED THINKING: Reason carefully step by step before answering — "
            "decompose the problem, consider alternatives and edge cases, and "
            "verify your conclusion. Your reasoning may be shown to the user in "
            "a collapsible Thinking panel, separate from the final answer."
        )
    if req.deep_research:
        instructions.append(
            "DEEP RESEARCH: Treat this as a research task. Use your tools to "
            "gather and cross-check multiple sources before answering. Structure "
            "the answer with clear headings, cite the evidence behind each key "
            "claim, call out disagreements between sources, and flag uncertainty."
        )
    if req.artifacts:
        instructions.append(
            "ARTIFACTS: When you produce a reusable deliverable — code, a "
            "document, a plan, data — present it as a self-contained artifact: "
            "code in a fenced block with its language tag, documents under a "
            "clear title. Keep explanation outside the artifact brief."
        )
    else:
        instructions.append(
            "Answer in plain, direct prose. Avoid large code blocks or document "
            "artifacts unless the user explicitly asks for them."
        )
    if not instructions and not base_prompt:
        return None
    parts = [p for p in [base_prompt, *instructions] if p]
    return "\n\n".join(parts) if parts else None


def _clean_thinking(text: str) -> str:
    """Strip the answer envelope from a reasoning trace for display."""
    upper = text.upper()
    idx = upper.find("FINAL ANSWER:")
    if idx != -1:
        text = text[:idx]
    return text.strip()


def _coding_prompt(message: str) -> str:
    from nexus.application.training.coding_prompt import CodingRAG
    from nexus.application.training.coding_store import CodingStore

    store = CodingStore("data/coding_examples.json")
    rag = CodingRAG(store, max_examples=3)
    return rag.build_coding_prompt(message)


async def _prepare_message(req: ChatRequest, container: Container) -> str:
    message = req.message
    if req.audio:
        try:
            mime, audio_bytes = _parse_data_uri(req.audio)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid audio data URI")
        transcription = await container.speech_to_text.transcribe(audio_bytes, mime)
        message = f"{transcription}\n{message}" if message else transcription
    if not message:
        raise HTTPException(status_code=422, detail="Provide a message, audio, or image")
    return message


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> ChatResponse:
    message = await _prepare_message(req, container)
    request_effort = _request_effort(container, req)
    request_mode = _request_mode(req)
    llm_override, model_label, model_source, provider_status = _resolve_request_llm(
        container,
        req.model,
        message=message,
        effort=request_effort,
        mode=request_mode,
        extended_thinking=req.extended_thinking,
        deep_research=req.deep_research,
        has_images=bool(req.image_urls),
    )

    system_prompt = _coding_prompt(message) if request_mode != "general" else None
    system_prompt = _capability_system_prompt(system_prompt, req, effort=request_effort)

    _set_tool_execution_context(identity)
    try:
        result = await container.process_message.execute(
            user_id=identity.user_id,
            message=message,
            session_id=req.session_id,
            stream=req.stream,
            tenant_id=identity.tenant_id,
            image_urls=req.image_urls,
            system_prompt=system_prompt,
            llm=llm_override,
            effort=request_effort,
            mode=request_mode,
        )
    finally:
        set_execution_context(None)

    audio = None
    if req.voice:
        audio_bytes = await container.text_to_speech.synthesize(result.response, req.voice)
        audio = _to_data_uri(audio_bytes, "audio/mpeg")

    thinking: list[str] = []
    if req.extended_thinking:
        thinking = [
            cleaned
            for t in result.thoughts
            if (cleaned := _clean_thinking(str(getattr(t, "content", t))))
        ]

    return ChatResponse(
        response=result.response,
        session_id=result.session_id,
        tools_used=result.tools_used,
        memories_recalled=result.memories_recalled,
        thought_count=len(result.thoughts),
        audio=audio,
        model=model_label,
        model_source=model_source,
        provider_status=provider_status,
        thinking=thinking,
        response_id=getattr(result, "response_id", None),
        guardrail=getattr(result, "guardrail", None),
        context_sources=getattr(result, "context_sources", []),
        execution=getattr(result, "execution", None),
        quality=getattr(result, "quality", None),
        coding=_result_coding(result),
    )


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
):
    """True SSE streaming — runs the full cognitive ReAct loop and emits events
    per thought, tool call, and observation as they happen, then the answer.

    Frame types: `start`, `thought`, `tool_call`, `observation`, `answer`,
    `done`, `error`. The `start` and `answer` frames carry `model`,
    `model_source` and `provider_status` from the model changer. Consume
    with `fetch`/SSE and render each reasoning step.
    """
    message = await _prepare_message(req, container)
    request_effort = _request_effort(container, req)
    request_mode = _request_mode(req)
    # Resolve before streaming so an unknown model is a clean HTTP 400,
    # not an error frame halfway through the response.
    llm_override, model_label, model_source, provider_status = _resolve_request_llm(
        container,
        req.model,
        message=message,
        effort=request_effort,
        mode=request_mode,
        extended_thinking=req.extended_thinking,
        deep_research=req.deep_research,
        has_images=bool(req.image_urls),
    )

    system_prompt = _coding_prompt(message) if request_mode != "general" else None
    system_prompt = _capability_system_prompt(system_prompt, req, effort=request_effort)

    model_meta = {
        "model": model_label,
        "model_source": model_source,
        "provider_status": provider_status,
        "effort": request_effort,
        "mode": request_mode,
        "coding_focus": _request_coding_focus(req),
    }

    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'session_id': req.session_id, **model_meta})}\n\n"

        try:
            # The ReAct loop pushes events into a queue; we yield each frame as
            # it is produced so users watch the brain think in real time.
            import asyncio

            queue: asyncio.Queue = asyncio.Queue()

            async def sink(ev: dict) -> None:
                await queue.put(ev)

            # create_task copies the current ContextVar context, so bind the
            # authenticated tenant/actor immediately before spawning ReAct.
            _set_tool_execution_context(identity)
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                container.process_message.execute(
                    user_id=identity.user_id,
                    message=message,
                    session_id=req.session_id,
                    stream=True,
                    tenant_id=identity.tenant_id,
                    image_urls=req.image_urls,
                    system_prompt=system_prompt,
                    on_event=sink,
                    llm=llm_override,
                    effort=request_effort,
                    mode=request_mode,
                )
            )

            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=30.0)
                except TimeoutError:
                    break
                if ev.get("type") == "answer":
                    ev = {**ev, **model_meta}
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") == "answer":
                    break

            result = await task
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "metadata",
                        "session_id": getattr(result, "session_id", req.session_id),
                        "response_id": getattr(result, "response_id", None),
                        "guardrail": getattr(result, "guardrail", None),
                        "context_sources": getattr(result, "context_sources", []),
                        "execution": getattr(result, "execution", None),
                        "quality": getattr(result, "quality", None),
                        "coding": _result_coding(result),
                    }
                )
                + "\n\n"
            )
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            set_execution_context(None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
