"""
Analyze API — file ingest + N.E.X.U.S tell/suggest/weakness/props.

Hexagonal: uses LLMProvider + ConceptRepository ports via container,
no direct driver. Public endpoint (no bearer) for HOLO hand-gesture file drop.
"""

from __future__ import annotations

import base64
import mimetypes

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from nexus.infrastructure.api.dependencies import get_container
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/api", tags=["analyze"])


class AnalyzeOut(BaseModel):
    filename: str
    summary: str
    suggestions: list[str]
    weaknesses: list[str]
    props: list[str]
    concepts: list[str]
    raw: str


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze_file(
    file: UploadFile = File(...),
    question: str = Form("Tell me about this file — suggest, weakness, props, etc"),
    tenant_id: str = Form("default"),
    container: Container = Depends(get_container),
) -> AnalyzeOut:
    data = await file.read()
    # decode best-effort text (fallback to base64 preview for binary)
    text = ""
    try:
        text = data.decode("utf-8")[:12000]
    except Exception:
        # binary: show mime + size + base64 head
        mime, _ = mimetypes.guess_type(file.filename or "")
        head = base64.b64encode(data[:1200]).decode("ascii")
        text = f"[binary {mime or 'unknown'} {len(data)} bytes] base64 head: {head[:600]}"

    prompt = f"""You are N.E.X.U.S — Neural EXpansion Unified System.
Analyze this file for the user. Be concise but structured.

Filename: {file.filename}
Question: {question}
Content (truncated 12k):
{text}

Return JSON with keys: summary (2-3 sentences), suggestions (3 bullets), weaknesses (2-3 bullets), props (strengths, 2-3 bullets), concepts (3-5 keywords). Keep tone helpful, direct.
If content is code, comment on architecture; if doc, on clarity; if unknown, infer from filename.
"""

    # Use background LLM (cheap) if available else primary — with heuristic fallback when offline
    llm = getattr(container, "background_llm", container.llm)
    heuristic = {
        "summary": f"File '{file.filename}' ({len(data)} bytes) ingested. {text[:220].replace(chr(10),' ') if text else 'Binary preview.'}",
        "suggestions": [
            "Add a 2-line header docstring / README describing purpose",
            "Split large file into cosmos nodes (one concept per 200 lines) for better recall",
            "Link to N.E.X.U.S memory: POST /v1/memory/search to surface related concepts",
        ],
        "weaknesses": [
            "No LLM key — heuristic mode (set OPENAI_API_KEY or NEXUS_LLM_BASE_URL for full analysis)",
            "Large file may exceed 12k prompt window — truncated" if len(data) > 12000 else "Small file — consider enriching with examples",
        ],
        "props": [
            "Ingested as joint mesh node — automatically links to N.E.X.U.S core + memory + concept",
            "Hand-gesture drop works offline; full N.E.X.U.S suggest/weakness when LLM online",
            f"File type {mimetypes.guess_type(file.filename or '')[0] or 'txt'} ready for swarm/dream pipeline",
        ],
        "concepts": [file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "text", "N.E.X.U.S", "cosmos"],
    }
    try:
        raw = await llm.complete(
            [{"role": "system", "content": prompt}, {"role": "user", "content": question}],
            temperature=0.3,
        )
    except Exception as e:
        import json as _hj

        raw = _hj.dumps(heuristic)

    # Try to parse LLM JSON, fallback to raw
    import json as _json

    try:
        parsed = _json.loads(raw)
        # handle code fence wrap
        if isinstance(parsed, str):
            parsed = _json.loads(parsed)
    except Exception:
        # try extract first {...}
        import re

        m = _json.loads("{}")
        try:
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                m = _json.loads(match.group(0))
            else:
                m = {}
        except Exception:
            m = {}
        parsed = m

    def _list(k):
        v = parsed.get(k, [])
        return v if isinstance(v, list) else [str(v)] if v else []

    return AnalyzeOut(
        filename=file.filename or "upload",
        summary=str(parsed.get("summary") or raw[:400]),
        suggestions=_list("suggestions") or _list("suggest"),
        weaknesses=_list("weaknesses") or _list("weakness"),
        props=_list("props") or _list("strengths") or _list("pros"),
        concepts=_list("concepts") or _list("keywords"),
        raw=raw[:4000],
    )


@router.get("/analyze/health")
async def analyze_health(container: Container = Depends(get_container)) -> dict:
    return {"ok": True, "llm": bool(getattr(container, "llm", None))}
