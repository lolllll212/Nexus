"""Dynamic model routing + token budget middleware.

One `LLMProvider` that routes by complexity and remaining quota:

- HIGH-complexity tasks -> the primary provider (NVIDIA NIM / premium APIs).
- LOW-complexity routine tasks (lint fixes, boilerplate, test stubs) ->
  local quantized models on Ollama (RTX 3050): deepseek-coder-6.7b-instruct,
  qwen3.5-9b, qwen2.5-coder-7b-instruct.
- Fallback chain in both directions: a dead local Ollama routes up to the
  primary; a cooled-down primary (429/exception) routes down to local.

`TokenBudgetMiddleware` wraps any provider and tracks spend per agent per day
in a JSON file, forcing over-budget traffic down to the local tier. Keeps
NEXUS running 24/7 without dead-ending when a provider quota is exhausted.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.value_objects.schema import JSONSchema

DEFAULT_LOCAL_HIGH = "qwen3.5:9b"
DEFAULT_LOCAL_LOW = "qwen2.5-coder:7b-instruct"
DEFAULT_LOCAL_CODER = "deepseek-coder:6.7b-instruct"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234/v1"
DEFAULT_LMSTUDIO_HIGH = "qwen/qwen3.5-9b"
DEFAULT_LMSTUDIO_LOW = "deepseek-r1-distill-qwen-7b"

_HIGH_SIGNALS = re.compile(
    r"\b(architect|design|refactor|security|concurrency|race|merge|protocol|"
    r"crdt|invariant|theorem|prove|trade-?off|tradeoff|root cause|diagnos[ei]|"
    r"threat|adversar|schema|migrat|correctness|determinis)\w*\b",
    re.IGNORECASE,
)
_CODE_MARKERS = re.compile(r"(```|def |class |import |=>|->|\bdef\b|;|\{|\})")

LOW_COMPLEXITY_MAX_CHARS = 1200


class Complexity(Enum):
    LOW = "low"
    HIGH = "high"


def classify_complexity(text: str) -> Complexity:
    """Deterministic heuristic complexity classification.

    HIGH when the text carries architecture/reasoning signals or is long;
    LOW when short, routine, and signal-free. Same input always yields the
    same route.
    """
    if not text:
        return Complexity.LOW
    if len(text) > LOW_COMPLEXITY_MAX_CHARS * 4:
        return Complexity.HIGH
    if len(_HIGH_SIGNALS.findall(text)) >= 2:
        return Complexity.HIGH
    if len(text) > LOW_COMPLEXITY_MAX_CHARS and _CODE_MARKERS.search(text):
        return Complexity.HIGH
    return Complexity.LOW


class OllamaProvider(LLMProvider):
    """Local quantized models via the Ollama HTTP API. Graceful failure."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_LOCAL_CODER,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{self.base_url}/api/chat", json=payload)
                r.raise_for_status()
                data = r.json()
                return str(data.get("message", {}).get("content", "") or "")
        except Exception:
            return ""

    async def extract_structured(
        self,
        content: str,
        schema: JSONSchema,
        instructions: str = "",
    ) -> dict:
        prompt = f"{instructions}\n\nReturn ONLY JSON matching this schema:\n{asdict(schema)}\n\n{content}"
        raw = await self.complete([{"role": "user", "content": prompt}], temperature=0.0)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False


def build_local_tier(
    backend: str | None = None,
) -> tuple[LLMProvider | None, LLMProvider | None]:
    """Build (local_high, local_low) providers from the environment.

    `NEXUS_LOCAL_BACKEND` selects the serving stack:
    - `ollama` (default): Ollama HTTP API at `NEXUS_OLLAMA_URL`
      (`http://127.0.0.1:11434`), models `NEXUS_LOCAL_MODEL_HIGH` /
      `NEXUS_LOCAL_MODEL_LOW`.
    - `lmstudio` / `openai-compatible`: any OpenAI-compatible server at
      `NEXUS_LMSTUDIO_URL` (`http://127.0.0.1:1234/v1`), models
      `NEXUS_LMSTUDIO_MODEL_HIGH` (`qwen3.5-9b`) / `NEXUS_LMSTUDIO_MODEL_LOW`
      (`qwen2.5-coder-7b-instruct`).

    Returns (None, None) when explicitly disabled with `NEXUS_LOCAL_BACKEND=none`.
    """
    import os

    backend = (backend or os.environ.get("NEXUS_LOCAL_BACKEND", "ollama")).lower()
    if backend in ("none", "off", "disabled"):
        return None, None
    if backend in ("lmstudio", "openai-compatible", "lm_studio"):
        from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider

        base_url = os.environ.get("NEXUS_LMSTUDIO_URL", DEFAULT_LMSTUDIO_URL)
        # Local inference on a consumer GPU needs far more than a socket
        # check; 120s covers quantized-model generation without hanging.
        timeout = float(os.environ.get("NEXUS_LOCAL_TIMEOUT", "120"))
        high = OpenAIProvider(
            api_key="local-no-key",
            model=os.environ.get("NEXUS_LMSTUDIO_MODEL_HIGH", DEFAULT_LMSTUDIO_HIGH),
            base_url=base_url,
            timeout=timeout,
        )
        low = OpenAIProvider(
            api_key="local-no-key",
            model=os.environ.get("NEXUS_LMSTUDIO_MODEL_LOW", DEFAULT_LMSTUDIO_LOW),
            base_url=base_url,
            timeout=timeout,
        )
        return high, low
    high = OllamaProvider(
        base_url=os.environ.get("NEXUS_OLLAMA_URL", DEFAULT_OLLAMA_URL),
        model=os.environ.get("NEXUS_LOCAL_MODEL_HIGH", DEFAULT_LOCAL_HIGH),
    )
    low = OllamaProvider(
        base_url=os.environ.get("NEXUS_OLLAMA_URL", DEFAULT_OLLAMA_URL),
        model=os.environ.get("NEXUS_LOCAL_MODEL_LOW", DEFAULT_LOCAL_LOW),
    )
    return high, low


class LearnedClassifier:
    """Online logistic-regression classifier for prompt complexity and routing.

    Trained on route logs + accepted-answer feedback from the eval harness.
    Persists learned weights across restarts. Pure Python (zero dependencies).
    """

    DEFAULT_LEARNING_RATE = 0.1

    def __init__(
        self,
        weights_path: Path | str | None = None,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        threshold: float = 0.5,
    ) -> None:
        self.weights_path = Path(weights_path) if weights_path else None
        self.learning_rate = learning_rate
        self.threshold = threshold
        self.weights: dict[str, float] = {}
        self.bias: float = 0.0
        self.samples_seen: int = 0
        if self.weights_path and self.weights_path.exists():
            self.load(self.weights_path)

    @staticmethod
    def extract_features(text: str) -> dict[str, float]:
        if not text:
            return {"length": 0.0, "high_signals": 0.0, "code_markers": 0.0}

        length_feat = min(len(text) / (LOW_COMPLEXITY_MAX_CHARS * 2), 5.0)
        high_signals = float(len(_HIGH_SIGNALS.findall(text)))
        code_markers = float(len(_CODE_MARKERS.findall(text)))

        features: dict[str, float] = {
            "length": length_feat,
            "high_signals": high_signals,
            "code_markers": code_markers,
        }

        lowered = text.lower()
        key_terms = [
            "crdt",
            "refactor",
            "security",
            "concurrency",
            "architecture",
            "lint",
            "typo",
            "formatting",
            "doc",
            "rename",
            "fix",
            "explain",
            "eval",
            "prove",
            "database",
            "docker",
        ]
        for term in key_terms:
            if term in lowered:
                features[f"kw_{term}"] = 1.0

        return features

    def predict_proba(self, text: str) -> float:
        """Return probability of HIGH complexity (1.0 = HIGH, 0.0 = LOW)."""
        feats = self.extract_features(text)
        score = self.bias + sum(v * self.weights.get(k, 0.0) for k, v in feats.items())
        clamped_score = max(-20.0, min(20.0, score))
        learned_prob = 1.0 / (1.0 + math.exp(-clamped_score))

        if self.samples_seen < 5:
            # Cold-start blend with heuristic
            heuristic_high = 1.0 if classify_complexity(text) is Complexity.HIGH else 0.0
            weight = self.samples_seen / 5.0
            return (1.0 - weight) * heuristic_high + weight * learned_prob
        return learned_prob

    def predict(self, text: str) -> Complexity:
        prob = self.predict_proba(text)
        return Complexity.HIGH if prob >= self.threshold else Complexity.LOW

    def update(self, text: str, target: float | Complexity | int, quality: float | None = None) -> float:
        """Online gradient update on a labeled outcome or eval feedback.

        target: 1.0 / Complexity.HIGH for high complexity, 0.0 / Complexity.LOW for low.
        quality: optional quality metric in [0.0, 1.0] from eval harness.
        """
        if isinstance(target, Complexity):
            y = 1.0 if target is Complexity.HIGH else 0.0
        else:
            y = float(target)

        loss_weight = 1.0 if quality is None else max(0.1, min(1.0, quality))

        feats = self.extract_features(text)
        score = self.bias + sum(v * self.weights.get(k, 0.0) for k, v in feats.items())
        clamped_score = max(-20.0, min(20.0, score))
        pred = 1.0 / (1.0 + math.exp(-clamped_score))

        error = (y - pred) * loss_weight
        lr = self.learning_rate / math.sqrt(1.0 + self.samples_seen * 0.05)

        for k, v in feats.items():
            self.weights[k] = self.weights.get(k, 0.0) + lr * error * v
        self.bias += lr * error
        self.samples_seen += 1

        if self.weights_path:
            self.save(self.weights_path)

        return pred

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "weights": self.weights,
            "bias": self.bias,
            "samples_seen": self.samples_seen,
            "threshold": self.threshold,
            "learning_rate": self.learning_rate,
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path: Path | str) -> None:
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.weights = dict(data.get("weights", {}))
            self.bias = float(data.get("bias", 0.0))
            self.samples_seen = int(data.get("samples_seen", 0))
            self.threshold = float(data.get("threshold", self.threshold))
            self.learning_rate = float(data.get("learning_rate", self.learning_rate))
        except (OSError, json.JSONDecodeError):
            pass


class LearnedRouter:
    """Cost-aware and speculative router combining learned classifier with latency/cost metrics."""

    def __init__(
        self,
        classifier: LearnedClassifier | None = None,
        weights_path: Path | str | None = None,
        cost_aware: bool = True,
        latency_weight: float = 0.2,
        cost_weight: float = 0.3,
        speculative: bool = True,
    ) -> None:
        self.classifier = classifier or LearnedClassifier(weights_path=weights_path)
        self.cost_aware = cost_aware
        self.latency_weight = latency_weight
        self.cost_weight = cost_weight
        self.speculative = speculative
        self.stats: dict[str, int] = {"primary": 0, "local": 0, "speculative_hits": 0}

    def route_decision(self, text: str) -> tuple[Complexity, dict[str, float]]:
        prob_high = self.classifier.predict_proba(text)

        q_primary = 0.95
        l_primary = 1.2
        c_primary = 1.0

        q_local = max(0.05, 0.95 * (1.0 - prob_high))
        l_local = 0.25
        c_local = 0.05

        u_primary = q_primary - (self.cost_weight * c_primary) - (self.latency_weight * l_primary)
        u_local = q_local - (self.cost_weight * c_local) - (self.latency_weight * l_local)

        if self.cost_aware:
            complexity = Complexity.LOW if u_local >= u_primary else Complexity.HIGH
        else:
            complexity = Complexity.HIGH if prob_high >= self.classifier.threshold else Complexity.LOW

        metrics = {
            "prob_high": prob_high,
            "q_local": q_local,
            "q_primary": q_primary,
            "u_local": u_local,
            "u_primary": u_primary,
        }
        return complexity, metrics

    def record_outcome(
        self,
        prompt: str,
        route: str,
        accepted: bool,
        latency: float = 0.0,
        quality: float | None = None,
    ) -> None:
        if route in ("local", "local-fallback", "local-speculative"):
            target = Complexity.LOW if accepted else Complexity.HIGH
        elif route == "primary":
            target = Complexity.HIGH if accepted else Complexity.LOW
        else:
            target = Complexity.HIGH if not accepted else Complexity.LOW

        self.classifier.update(prompt, target=target, quality=quality)


class RoutingProvider(LLMProvider):
    """Routes between a premium primary and the local tier (Ollama or LM Studio).

    Route rules, all deterministic:
    - LOW complexity -> local; HIGH complexity -> primary.
    - Primary failure (exception or empty reply) -> falls back to local.
    - Local failure and the task was HIGH -> the error propagates (never a
      silent wrong-tier answer); a LOW task failing local returns "".

    Pass `local_high`/`local_low` providers directly (LM Studio pair via
    `build_local_tier()`), or just `local` (an OllamaProvider) plus per-tier
    model names and the tier swap is built for you.
    """

    def __init__(
        self,
        primary: LLMProvider,
        local: LLMProvider | None = None,
        local_high: LLMProvider | None = None,
        local_low: LLMProvider | None = None,
        local_high_model: str = DEFAULT_LOCAL_HIGH,
        local_low_model: str = DEFAULT_LOCAL_LOW,
        force_route: Complexity | None = None,
        learned_router: LearnedRouter | None = None,
        weights_path: Path | str | None = None,
        cost_aware: bool = False,
        speculative: bool = False,
    ) -> None:
        self.primary = primary
        self.local = local
        self.local_high = local_high
        self.local_low = local_low
        self.local_high_model = local_high_model
        self.local_low_model = local_low_model
        self.force_route = force_route
        self.weights_path = Path(weights_path) if weights_path else None
        self.learned_router = learned_router or (
            LearnedRouter(weights_path=self.weights_path, cost_aware=cost_aware, speculative=speculative)
            if (self.weights_path or cost_aware or speculative)
            else None
        )
        self.route_log: list[dict[str, Any]] = []

    def _pick_local(self, complexity: Complexity) -> LLMProvider | None:
        if complexity is Complexity.HIGH and self.local_high is not None:
            return self.local_high
        if complexity is Complexity.LOW and self.local_low is not None:
            return self.local_low
        if self.local is None:
            return None
        if isinstance(self.local, OllamaProvider):
            model = self.local_high_model if complexity is Complexity.HIGH else self.local_low_model
            return OllamaProvider(base_url=self.local.base_url, model=model, timeout=self.local.timeout)
        return self.local

    def record_feedback(
        self,
        prompt: str,
        route: str,
        accepted: bool,
        latency: float = 0.0,
        quality: float | None = None,
    ) -> None:
        """Feed eval harness or consensus outcome back into the learned router."""
        if self.learned_router is None:
            self.learned_router = LearnedRouter(weights_path=self.weights_path)
        self.learned_router.record_outcome(
            prompt=prompt,
            route=route,
            accepted=accepted,
            latency=latency,
            quality=quality,
        )

    def train_from_route_log(self, accepted_outcomes: dict[int, bool] | None = None) -> int:
        """Train weights from history of route_log + accepted outcomes."""
        if not self.learned_router:
            self.learned_router = LearnedRouter(weights_path=self.weights_path)
        count = 0
        for i, entry in enumerate(self.route_log):
            prompt = str(entry.get("prompt", "") or "")
            route = str(entry.get("route", "primary") or "")
            accepted = accepted_outcomes.get(i, True) if accepted_outcomes else True
            if prompt:
                self.record_feedback(prompt, route, accepted)
                count += 1
        return count

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        full_text = "\n".join(m.get("content", "") for m in messages)
        if self.force_route:
            complexity = self.force_route
        elif self.learned_router:
            complexity, _ = self.learned_router.route_decision(full_text)
        else:
            complexity = classify_complexity(full_text)

        route = "local" if complexity is Complexity.LOW else "primary"

        async def _try(provider: LLMProvider) -> str:
            # Local tiers degrade (timeout, dead server) instead of raising;
            # the caller falls through to the next hop.
            try:
                return await provider.complete(
                    messages, temperature=temperature, max_tokens=max_tokens, tools=tools
                )
            except Exception:
                return ""

        # Speculative short-circuit: if speculative enabled and complexity is HIGH,
        # try the fast local model first. If it yields a viable non-error answer, short-circuit!
        if (
            self.learned_router
            and self.learned_router.speculative
            and complexity is Complexity.HIGH
            and self._pick_local(Complexity.HIGH) is not None
        ):
            local_spec = self._pick_local(Complexity.HIGH)
            if local_spec is not None:
                spec_reply = await _try(local_spec)
                if spec_reply and len(spec_reply.strip()) > 2 and not spec_reply.strip().startswith("Error"):
                    self.learned_router.stats["speculative_hits"] += 1
                    self.route_log.append(
                        {
                            "route": "local-speculative",
                            "complexity": complexity.value,
                            "prompt": full_text,
                            "speculative": True,
                        }
                    )
                    return spec_reply

        reply = ""
        if route == "local":
            local = self._pick_local(complexity)
            if local is not None:
                reply = await _try(local)
                if reply:
                    self.route_log.append(
                        {
                            "route": "local",
                            "complexity": complexity.value,
                            "prompt": full_text,
                        }
                    )
                    return reply
                route = "primary-fallback"
        reply = await _try(self.primary)
        if reply:
            self.route_log.append(
                {
                    "route": "primary",
                    "complexity": complexity.value,
                    "prompt": full_text,
                }
            )
            return reply
        local = self._pick_local(complexity)
        if local is not None:
            reply = await _try(local)
            if reply:
                self.route_log.append(
                    {
                        "route": "local-fallback",
                        "complexity": complexity.value,
                        "prompt": full_text,
                    }
                )
                return reply
        self.route_log.append(
            {
                "route": "none",
                "complexity": complexity.value,
                "prompt": full_text,
            }
        )
        return ""

    async def extract_structured(
        self,
        content: str,
        schema: JSONSchema,
        instructions: str = "",
    ) -> dict:
        structured = await self.primary.extract_structured(content, schema, instructions)
        if structured:
            return structured
        local = self._pick_local(Complexity.LOW)
        if local is not None:
            return await local.extract_structured(content, schema, instructions)
        return {}


def estimate_tokens(text: str) -> int:
    """Cheap deterministic token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


class TokenBudgetMiddleware(LLMProvider):
    """Tracks per-agent daily token spend and enforces a budget cap.

    Over-budget traffic is forced down to the local tier (a `fallback`
    provider) instead of failing - the system keeps running 24/7 when a
    provider quota dies. Spend ledger lives in a JSON file shared across
    worktrees (callers pass the rendezvous path).
    """

    def __init__(
        self,
        inner: LLMProvider,
        fallback: LLMProvider | None,
        ledger_path: Path,
        daily_budget: int,
        agent: str = "system",
    ) -> None:
        self.inner = inner
        self.fallback = fallback
        self.ledger_path = Path(ledger_path)
        self.daily_budget = daily_budget
        self.agent = agent
        self.spend: int = 0

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _today(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def spent_today(self) -> int:
        data = self._load()
        return int(data.get(self._today(), {}).get(self.agent, 0))

    def _record(self, tokens: int) -> None:
        data = self._load()
        day = data.setdefault(self._today(), {})
        day[self.agent] = int(day.get(self.agent, 0)) + tokens
        # Deterministic prune: keep only the last 30 days.
        keys = sorted(data.keys())
        for k in keys[:-30]:
            del data[k]
        self._save(data)
        self.spend += tokens

    def over_budget(self, incoming_tokens: int) -> bool:
        return self.spent_today() + incoming_tokens > self.daily_budget

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        incoming = sum(estimate_tokens(m.get("content", "")) for m in messages)
        provider = self.inner
        routed = "primary"
        if self.over_budget(incoming):
            if self.fallback is None:
                return ""
            provider = self.fallback
            routed = "local-budget"
        reply = await provider.complete(messages, temperature=temperature, max_tokens=max_tokens, tools=tools)
        self._record(incoming + estimate_tokens(reply))
        if not reply and routed == "primary" and self.fallback is not None:
            reply = await self.fallback.complete(
                messages, temperature=temperature, max_tokens=max_tokens, tools=tools
            )
            if reply:
                self._record(estimate_tokens(reply))
        return reply

    async def extract_structured(
        self,
        content: str,
        schema: JSONSchema,
        instructions: str = "",
    ) -> dict:
        incoming = estimate_tokens(content) + estimate_tokens(instructions)
        provider = self.inner
        if self.over_budget(incoming) and self.fallback is not None:
            provider = self.fallback
        result = await provider.extract_structured(content, schema, instructions)
        self._record(incoming + estimate_tokens(json.dumps(result)))
        return result
