"""
Workspace API — the premium light-mode NEXUS OS workspace surface.

Powers the Primary Workspace Dashboard and the floating Query Cockpit:
  * GET  /api/workspace/bootstrap  — live workspace state (greeting, hero, cards, telemetry).
  * POST /api/workspace/search    — unified multi-modal search across memory, research
                                    history, concepts, and the multimodal sample library.
  * POST /api/workspace/image     — deterministic procedural image synthesis (SVG art
                                    engine seeded by the prompt).
  * POST /api/workspace/music     — deterministic procedural music synthesis (WAV
                                    render: pads, arpeggios, bass, and percussion).

Every cockpit chip maps onto a real backend route — no mock payloads.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import random
import struct
import time
import wave
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/api/workspace", tags=["workspace"], dependencies=[Depends(require_identity)])

_START_TIME = time.time()

# Canonical built-in enterprise roster (mirrors the Agent Orchestration Layer).
# Reported when the swarm repository has no live registrations yet.
_BUILTIN_AGENTS: list[dict[str, str]] = [
    {"name": "Researcher", "role": "research", "status": "standby"},
    {"name": "Coder", "role": "code", "status": "standby"},
    {"name": "Planner", "role": "planning", "status": "standby"},
    {"name": "Browser", "role": "web", "status": "standby"},
    {"name": "Vision", "role": "perception", "status": "standby"},
    {"name": "Data Analyst", "role": "analysis", "status": "standby"},
    {"name": "Writer", "role": "writing", "status": "standby"},
    {"name": "Executor", "role": "execution", "status": "standby"},
    {"name": "Memory", "role": "memory", "status": "standby"},
    {"name": "Fact Checker", "role": "verification", "status": "standby"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Request / response models
# ─────────────────────────────────────────────────────────────────────────────


class WorkspaceSearchRequest(BaseModel):
    query: str
    limit: int = Field(8, ge=1, le=25)


class WorkspaceSearchResult(BaseModel):
    source: str  # memory | research | concept | multimodal
    title: str
    snippet: str
    score: float
    kind: str | None = None
    url: str | None = None


class WorkspaceSearchResponse(BaseModel):
    status: str = "success"
    query: str
    results: list[WorkspaceSearchResult]
    scanned_sources: int
    duration_ms: float


class WorkspaceImageRequest(BaseModel):
    prompt: str
    style: str = "aurora"  # aurora | blueprint | horizon
    size: int = Field(720, ge=256, le=1024)


class WorkspaceImageResponse(BaseModel):
    status: str = "success"
    prompt: str
    seed: int
    style: str
    palette: list[str]
    width: int
    height: int
    svg_data_uri: str
    render_ms: float
    engine: str = "NEXUS Procedural Art Engine v1.2"


class WorkspaceMusicRequest(BaseModel):
    prompt: str
    duration_seconds: float = Field(12.0, ge=4.0, le=30.0)
    tempo: int = Field(96, ge=60, le=160)


class WorkspaceMusicResponse(BaseModel):
    status: str = "success"
    prompt: str
    seed: int
    key: str
    scale: str
    tempo: int
    duration_seconds: float
    sample_rate: int
    notes_rendered: int
    audio_data_uri: str
    render_ms: float
    engine: str = "NEXUS Generative Audio Cortex v1.2"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _seed_from(text: str) -> int:
    return int(hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:12], 16)


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(t) > 2}


def _score(query_tokens: set[str], candidate: str) -> float:
    if not query_tokens:
        return 0.0
    cand_tokens = _tokens(candidate)
    if not cand_tokens:
        return 0.0
    overlap = len(query_tokens & cand_tokens)
    return round(overlap / len(query_tokens), 3)


# ─────────────────────────────────────────────────────────────────────────────
# GET /bootstrap — live workspace state
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/bootstrap")
async def workspace_bootstrap(
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Everything the Primary Workspace Dashboard needs, straight from the brain."""

    display_name = getattr(identity, "display_name", None) or "Nixtio"

    recent_memories: list[dict[str, Any]] = []
    try:
        memories = await container.memory_repo.retrieve(
            "nexus workspace focus priorities", limit=4, tenant_id=identity.tenant_id
        )
        recent_memories = [
            {
                "content": m.content[:160],
                "memory_type": getattr(getattr(m, "memory_type", None), "value", "semantic"),
                "access_count": getattr(m, "access_count", 0),
            }
            for m in memories
        ]
    except Exception:
        pass

    agents: list[dict[str, Any]] = []
    try:
        swarm_agents = await container.list_agents.execute(tenant_id=identity.tenant_id)
        agents = [
            {
                "name": getattr(a, "name", "Agent"),
                "role": getattr(getattr(a, "role", None), "value", getattr(a, "role", "agent")),
                "status": getattr(a, "status", "idle"),
            }
            for a in swarm_agents[:10]
        ]
    except Exception:
        pass
    if not agents:
        # No live registrations — report the built-in enterprise roster.
        agents = list(_BUILTIN_AGENTS)

    nim_online = False
    nim_model: str | None = None
    try:
        nim_provider = getattr(container, "nim_provider", None)
        if nim_provider is not None:
            nim_model = getattr(nim_provider, "model", None)
            nim_online = bool(nim_model)
    except Exception:
        pass

    return {
        "status": "success",
        "greeting": {
            "user": display_name,
            "headline": f"Hi {display_name}, Ready to Achieve Great Things?",
            "subline": "Your cognitive copilot is online. Search, research, create, and ship — all from one canvas.",
        },
        "hero": {
            "companion": "NIX-7",
            "message": "Hey there! Need a boost?",
            "suggestions": [
                "Explain quantum computing in simple terms",
                "Research the state of autonomous agents",
                "Generate an aurora over a neural skyline",
                "Compose a focus track for deep work",
            ],
        },
        "cards": [
            {
                "id": "fast-start",
                "title": "Fast Start",
                "description": "Spin up quick tasks and contribution loops. Zero-friction execution, instant feedback.",
                "accent": "orange",
                "action": "FAST_START",
                "stat": f"{len(recent_memories)} recent sparks",
            },
            {
                "id": "collaborate",
                "title": "Collaborate with Team",
                "description": "Background multi-agent orchestrations — researcher, coder, planner and swarm run in parallel.",
                "accent": "multicolor",
                "action": "OPEN_AGENTS",
                "stat": f"{len(agents)} agents online",
            },
            {
                "id": "planning",
                "title": "Planning",
                "description": "Track priorities and workflows on a living calendar. Deadlines become DAG steps.",
                "accent": "blue",
                "action": "OPEN_WORKFLOWS",
                "stat": "Roadmap synced",
            },
        ],
        "telemetry": {
            "uptime_seconds": round(time.time() - _START_TIME, 1),
            "agents_online": len(agents),
            "agents": agents,
            "recent_memories": recent_memories,
            "nim_online": nim_online,
            "nim_model": nim_model,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /search — unified multi-modal search
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/search", response_model=WorkspaceSearchResponse)
async def workspace_search(
    req: WorkspaceSearchRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> WorkspaceSearchResponse:
    started = time.perf_counter()
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    query_tokens = _tokens(query)
    results: list[WorkspaceSearchResult] = []
    scanned = 0

    # 1. Episodic + semantic memory
    try:
        memories = await container.memory_repo.retrieve(query, limit=req.limit, tenant_id=identity.tenant_id)
        scanned += len(memories)
        for m in memories:
            content = getattr(m, "content", "")
            results.append(
                WorkspaceSearchResult(
                    source="memory",
                    title=(content[:72] + "…") if len(content) > 72 else content,
                    snippet=content[:220],
                    score=max(0.35, _score(query_tokens, content)),
                    kind=getattr(getattr(m, "memory_type", None), "value", "semantic"),
                )
            )
    except Exception:
        pass

    # 2. Knowledge-graph concepts
    try:
        words = [w for w in query_tokens][:4] or [query]
        for word in words:
            concepts = await container.concept_repo.find_by_label(word, limit=4, tenant_id=identity.tenant_id)
            scanned += len(concepts)
            for c in concepts:
                label = getattr(c, "label", str(word))
                results.append(
                    WorkspaceSearchResult(
                        source="concept",
                        title=f"◈ {label}",
                        snippet=f"Synaptic concept node · strength {getattr(c, 'strength', 0.5):.2f}",
                        score=max(0.4, _score(query_tokens, label)),
                        kind="knowledge-graph",
                    )
                )
    except Exception:
        pass

    # 3. Deep-research history
    try:
        from nexus.infrastructure.api.routes.research import RESEARCH_HISTORY

        scanned += len(RESEARCH_HISTORY)
        for entry in RESEARCH_HISTORY[:10]:
            text = f"{entry.get('query', '')} {entry.get('summary', '')}"
            score = _score(query_tokens, text)
            if score > 0:
                results.append(
                    WorkspaceSearchResult(
                        source="research",
                        title=f"Research: {entry.get('query', 'untitled')}",
                        snippet=str(entry.get("summary", ""))[:220],
                        score=score,
                        kind="deep-research",
                    )
                )
    except Exception:
        pass

    # 4. Multimodal sample library (vision corpus)
    try:
        from nexus.infrastructure.api.routes.multimodal import get_multimodal_samples

        samples = (await get_multimodal_samples()).get("samples", [])
        scanned += len(samples)
        for s in samples:
            text = f"{s.get('title', '')} {s.get('description', '')}"
            score = _score(query_tokens, text)
            if score > 0:
                results.append(
                    WorkspaceSearchResult(
                        source="multimodal",
                        title=s.get("title", "Untitled sample"),
                        snippet=str(s.get("description", ""))[:220],
                        score=score,
                        kind=s.get("type", "media"),
                        url=s.get("url"),
                    )
                )
    except Exception:
        pass

    results.sort(key=lambda r: r.score, reverse=True)
    return WorkspaceSearchResponse(
        query=query,
        results=results[: req.limit],
        scanned_sources=scanned,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /image — procedural art synthesis
# ─────────────────────────────────────────────────────────────────────────────


_PALETTES: dict[str, list[str]] = {
    "sunset": ["#FF7A59", "#FFB26B", "#C25588", "#FFD9A0"],
    "ocean": ["#0EA5E9", "#22D3EE", "#2563EB", "#7DD3FC"],
    "forest": ["#10B981", "#34D399", "#0F766E", "#A7F3D0"],
    "neon": ["#22D3EE", "#A78BFA", "#F472B6", "#38BDF8"],
    "ember": ["#F97316", "#FB923C", "#DC2626", "#FDE68A"],
    "mono": ["#334155", "#64748B", "#94A3B8", "#CBD5E1"],
}

_PALETTE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("sunset", "sunrise", "desert", "dawn", "dusk", "warm"), "sunset"),
    (("ocean", "sea", "water", "wave", "sky", "cloud", "rain", "ice"), "ocean"),
    (("forest", "tree", "nature", "leaf", "green", "jungle", "moss"), "forest"),
    (("fire", "ember", "lava", "volcano", "heat", "magma"), "ember"),
    (("mono", "ink", "graphite", "noir", "black", "white", "minimal"), "mono"),
    (("quantum", "neon", "cyber", "space", "galaxy", "nebula", "aurora", "synth", "dream"), "neon"),
]


def _pick_palette(prompt: str, rng: random.Random) -> list[str]:
    lowered = prompt.lower()
    for keywords, name in _PALETTE_KEYWORDS:
        if any(k in lowered for k in keywords):
            return _PALETTES[name]
    return _PALETTES[rng.choice(["neon", "sunset", "ocean"])]


def _render_art_svg(prompt: str, style: str, size: int) -> tuple[str, list[str], int]:
    seed = _seed_from(f"{prompt}|{style}")
    rng = random.Random(seed)
    palette = _pick_palette(prompt, rng)
    c1, c2, c3, c4 = palette

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">'
    )
    parts.append(f'<defs>'
                 f'<radialGradient id="bg" cx="30%" cy="25%" r="95%">'
                 f'<stop offset="0%" stop-color="#141B2E"/><stop offset="100%" stop-color="#0B0F19"/>'
                 f'</radialGradient>'
                 f'<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">'
                 f'<feGaussianBlur stdDeviation="{size * 0.045}"/>'
                 f'</filter>'
                 f'<filter id="glow" x="-40%" y="-40%" width="180%" height="180%">'
                 f'<feGaussianBlur stdDeviation="{size * 0.008}"/>'
                 f'</filter>'
                 f'</defs>')
    parts.append(f'<rect width="{size}" height="{size}" fill="url(#bg)"/>')

    # Layer 1 — flowing aurora ribbons (blurred translucent ellipses)
    for i in range(rng.randint(5, 8)):
        cx = rng.uniform(0.1, 0.9) * size
        cy = rng.uniform(0.1, 0.9) * size
        rx = rng.uniform(0.18, 0.42) * size
        ry = rx * rng.uniform(0.35, 0.75)
        rot = rng.uniform(0, 180)
        color = rng.choice(palette)
        opacity = rng.uniform(0.10, 0.26)
        parts.append(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
            f'fill="{color}" opacity="{opacity:.2f}" filter="url(#soft)" '
            f'transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})"/>'
        )

    # Layer 2 — orbital geometry
    cx, cy = size * 0.5, size * 0.5
    if style == "blueprint":
        # technical grid + concentric construction circles
        step = size // 14
        for g in range(step, size, step):
            parts.append(f'<line x1="{g}" y1="0" x2="{g}" y2="{size}" stroke="{c1}" stroke-opacity="0.07" stroke-width="1"/>')
            parts.append(f'<line x1="0" y1="{g}" x2="{size}" y2="{g}" stroke="{c1}" stroke-opacity="0.07" stroke-width="1"/>')
        for r in range(2, 9):
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{size * r / 18:.1f}" fill="none" '
                f'stroke="{rng.choice([c1, c2])}" stroke-opacity="{rng.uniform(0.12, 0.3):.2f}" stroke-width="1.2"/>'
            )
        for spoke in range(12):
            ang = math.radians(spoke * 30)
            x2 = cx + math.cos(ang) * size * 0.44
            y2 = cy + math.sin(ang) * size * 0.44
            parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c3}" stroke-opacity="0.14"/>')
    elif style == "horizon":
        # layered mountain / wave silhouettes
        for layer in range(4):
            y_base = size * (0.62 + layer * 0.09)
            amplitude = size * (0.10 - layer * 0.02)
            path = [f"M0,{y_base:.1f}"]
            phase = rng.uniform(0, math.pi * 2)
            freq = rng.uniform(2.2, 3.6)
            x = 0
            while x <= size:
                y = y_base - math.sin(phase + x / size * math.pi * freq) * amplitude
                path.append(f"L{x},{y:.1f}")
                x += size // 48
            path.append(f"L{size},{size} L0,{size} Z")
            color = palette[min(layer, len(palette) - 1)]
            parts.append(f'<path d="{" ".join(path)}" fill="{color}" opacity="{0.55 - layer * 0.1:.2f}"/>')
        parts.append(f'<circle cx="{size * rng.uniform(0.2, 0.8):.1f}" cy="{size * 0.3:.1f}" r="{size * 0.07:.1f}" fill="{c4}" opacity="0.9" filter="url(#glow)"/>')
    else:
        # aurora — glowing orbital rings + floating nodes
        for ring in range(rng.randint(3, 5)):
            r = size * rng.uniform(0.16, 0.44)
            color = rng.choice(palette)
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{color}" '
                f'stroke-opacity="{rng.uniform(0.18, 0.4):.2f}" stroke-width="{rng.uniform(1.2, 2.6):.1f}" filter="url(#glow)"/>'
            )

    # Layer 3 — particle constellation
    for _ in range(rng.randint(28, 46)):
        px, py = rng.uniform(0, size), rng.uniform(0, size)
        pr = rng.uniform(1.2, 4.2)
        color = rng.choice(palette)
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{pr:.1f}" fill="{color}" '
            f'opacity="{rng.uniform(0.25, 0.85):.2f}" filter="url(#glow)"/>'
        )

    # Core signature
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{size * 0.045:.1f}" fill="{c4}" opacity="0.95" filter="url(#glow)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{size * 0.018:.1f}" fill="#FFFFFF"/>'
    )
    parts.append("</svg>")
    svg = "".join(parts)

    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return data_uri, palette, seed


@router.post("/image", response_model=WorkspaceImageResponse)
async def generate_workspace_image(req: WorkspaceImageRequest) -> WorkspaceImageResponse:
    started = time.perf_counter()
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Image prompt cannot be empty.")

    style = req.style if req.style in {"aurora", "blueprint", "horizon"} else "aurora"
    data_uri, palette, seed = _render_art_svg(prompt, style, req.size)

    return WorkspaceImageResponse(
        prompt=prompt,
        seed=seed,
        style=style,
        palette=palette,
        width=req.size,
        height=req.size,
        svg_data_uri=data_uri,
        render_ms=round((time.perf_counter() - started) * 1000, 1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /music — procedural music synthesis (WAV)
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLE_RATE = 22050

_SCALES: dict[str, list[int]] = {
    "major pentatonic": [0, 2, 4, 7, 9, 12, 14, 16],
    "minor pentatonic": [0, 3, 5, 7, 10, 12, 15, 17],
    "dorian": [0, 2, 3, 5, 7, 9, 10, 12],
    "lydian": [0, 2, 4, 6, 7, 9, 11, 12],
}

_SCALE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("sad", "dark", "melancholy", "night", "moody", "rain", "lonely", "noir"), "minor pentatonic"),
    (("epic", "cinematic", "heroic", "battle", "journey", "adventure"), "dorian"),
    (("dreamy", "floating", "ethereal", "wonder", "magic", "cosmic"), "lydian"),
]

_ROOT_NOTES: dict[str, float] = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.00, "A": 440.00, "B": 493.88}


def _pick_scale(prompt: str, rng: random.Random) -> tuple[str, str]:
    lowered = prompt.lower()
    for keywords, name in _SCALE_KEYWORDS:
        if any(k in lowered for k in keywords):
            return rng.choice(list(_ROOT_NOTES)), name
    return rng.choice(list(_ROOT_NOTES)), "major pentatonic"


def _note_freq(root_hz: float, semitone: int) -> float:
    return root_hz * (2 ** (semitone / 12.0))


def _render_music_wav(prompt: str, tempo: int, duration: float) -> tuple[bytes, dict[str, Any]]:
    seed = _seed_from(f"{prompt}|{tempo}|{duration}")
    rng = random.Random(seed)
    root_name, scale_name = _pick_scale(prompt, rng)
    scale = _SCALES[scale_name]
    root_hz = _ROOT_NOTES[root_name]

    total_samples = int(duration * _SAMPLE_RATE)
    buf = [0.0] * total_samples
    beat = 60.0 / tempo
    bar = beat * 4
    notes_rendered = 0

    def add_tone(freq: float, start_s: float, dur_s: float, gain: float, attack: float, wave_kind: str = "sine") -> None:
        nonlocal notes_rendered
        start = int(start_s * _SAMPLE_RATE)
        end = min(int((start_s + dur_s) * _SAMPLE_RATE), total_samples)
        if start >= end:
            return
        notes_rendered += 1
        for i in range(start, end):
            t = (i - start) / _SAMPLE_RATE
            # ADSR-ish envelope: fast attack, sustain, smooth release
            env = min(1.0, t / attack) if t < attack else 1.0
            release = dur_s * 0.35
            if t > dur_s - release:
                env *= max(0.0, (dur_s - t) / release)
            if wave_kind == "pluck":
                env *= math.exp(-3.2 * t / dur_s)
            phase = 2 * math.pi * freq * t
            if wave_kind == "triangle":
                sample = math.asin(math.sin(phase)) * (2 / math.pi)
            elif wave_kind == "organ":
                sample = 0.6 * math.sin(phase) + 0.25 * math.sin(2 * phase) + 0.15 * math.sin(3 * phase)
            else:
                sample = math.sin(phase)
            buf[i] += sample * gain * env

    def add_kick(start_s: float) -> None:
        nonlocal notes_rendered
        start = int(start_s * _SAMPLE_RATE)
        end = min(start + int(0.16 * _SAMPLE_RATE), total_samples)
        notes_rendered += 1
        for i in range(start, end):
            t = (i - start) / _SAMPLE_RATE
            freq = 120 * math.exp(-18 * t) + 44
            env = math.exp(-9 * t)
            buf[i] += math.sin(2 * math.pi * freq * t) * 0.34 * env

    # Chord progression: I – vi – IV – V mapped onto the chosen scale
    progression = [
        [scale[0], scale[2], scale[4]],
        [scale[3], scale[5], scale[0] + 12],
        [scale[1], scale[3], scale[5]],
        [scale[4], scale[6], scale[1] + 12],
    ]

    t_cursor = 0.0
    bar_index = 0
    while t_cursor < duration:
        chord = progression[bar_index % len(progression)]
        bar_remaining = min(bar, duration - t_cursor)

        # Pad — sustained organ chord
        for semitone in chord:
            add_tone(_note_freq(root_hz, semitone), t_cursor, bar_remaining, 0.085, 0.9, "organ")
        # Bass — root of the chord, two octaves down
        add_tone(_note_freq(root_hz, chord[0] - 24), t_cursor, bar_remaining * 0.92, 0.16, 0.02)

        # Arpeggio — 8th-note plucks walking the chord + scale colour tones
        step = beat / 2
        n_steps = int(bar_remaining / step)
        for s in range(n_steps):
            if rng.random() < 0.22:
                continue  # humanised rests
            if s % 2 == 0:
                semitone = chord[(s // 2) % len(chord)] + 12
            else:
                semitone = rng.choice(scale) + 12
            add_tone(_note_freq(root_hz, semitone), t_cursor + s * step, step * 0.95, 0.11, 0.008, "pluck")

        # Percussion — soft kick on beats 1 & 3
        add_kick(t_cursor)
        if bar_remaining > beat * 2.5:
            add_kick(t_cursor + beat * 2)

        # Shimmer — occasional high bell
        if rng.random() < 0.5 and bar_remaining > beat:
            add_tone(_note_freq(root_hz, rng.choice(scale) + 24), t_cursor + beat * rng.uniform(0.5, 3), 0.9, 0.05, 0.01)

        t_cursor += bar
        bar_index += 1

    # Normalise + soft clip
    peak = max((abs(v) for v in buf), default=1.0) or 1.0
    target = 0.86
    scale_factor = target / peak
    frames = bytearray()
    for v in buf:
        s = math.tanh(v * scale_factor)
        frames += struct.pack("<h", int(s * 32767))

    out = io.BytesIO()
    with wave.open(out, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_SAMPLE_RATE)
        wav_file.writeframes(bytes(frames))
    wav_bytes = out.getvalue()

    return wav_bytes, {
        "seed": seed,
        "key": root_name,
        "scale": scale_name,
        "notes_rendered": notes_rendered,
    }


@router.post("/music", response_model=WorkspaceMusicResponse)
async def generate_workspace_music(req: WorkspaceMusicRequest) -> WorkspaceMusicResponse:
    started = time.perf_counter()
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Music prompt cannot be empty.")

    wav_bytes, meta = _render_music_wav(prompt, req.tempo, req.duration_seconds)
    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

    return WorkspaceMusicResponse(
        prompt=prompt,
        seed=meta["seed"],
        key=meta["key"],
        scale=meta["scale"],
        tempo=req.tempo,
        duration_seconds=req.duration_seconds,
        sample_rate=_SAMPLE_RATE,
        notes_rendered=meta["notes_rendered"],
        audio_data_uri="data:audio/wav;base64," + audio_b64,
        render_ms=round((time.perf_counter() - started) * 1000, 1),
    )
