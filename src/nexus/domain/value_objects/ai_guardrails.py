"""Deterministic AI guardrails for prompts, tool output, and responses.

This module is deliberately pure domain logic: no network calls, model calls,
or infrastructure imports.  It gives Nexus a fast local safety/privacy layer
that can run on every request, including fully offline deployments.

The policy makes three kinds of decisions:

* redact high-confidence secrets and personal data before text is sent to a
  model, persisted, or returned to a caller;
* block direct attempts to exfiltrate credentials or hidden instructions;
* flag (without automatically refusing) prompt-override language so metrics
  and operators can see attempted manipulation while legitimate security
  discussions remain possible.

Findings never contain the sensitive value that matched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class GuardrailAction(StrEnum):
    ALLOW = "allow"
    REDACT = "redact"
    FLAG = "flag"
    BLOCK = "block"


@dataclass(frozen=True)
class GuardrailFinding:
    """One policy finding, safe to expose in API metadata and metrics."""

    category: str
    action: GuardrailAction
    severity: str
    count: int = 1
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "action": self.action.value,
            "severity": self.severity,
            "count": self.count,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GuardrailDecision:
    """The result of evaluating one piece of text at one pipeline stage."""

    action: GuardrailAction
    text: str
    stage: str
    findings: tuple[GuardrailFinding, ...] = ()
    blocked_reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action is not GuardrailAction.BLOCK

    @property
    def blocked(self) -> bool:
        return self.action is GuardrailAction.BLOCK

    @property
    def redacted(self) -> bool:
        return any(f.action is GuardrailAction.REDACT for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "stage": self.stage,
            "findings": [finding.to_dict() for finding in self.findings],
            "blocked_reason": self.blocked_reason,
            "redaction_count": sum(
                finding.count for finding in self.findings if finding.action is GuardrailAction.REDACT
            ),
        }


_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{10,}\b"),
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|secret)\b"
    r"(\s*[:=]\s*)(\"[^\"]+\"|'[^']+'|[^\s,;]+)"
)
_URL_CREDENTIAL_RE = re.compile(r"([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+\d[\d ()-]{7,}\d|\b(?:\(?\d{3}\)?[\s.-])\d{3}[\s.-]\d{4}\b)"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_SECRET_OBJECT = (
    r"(?:\.env\b|credentials?\b|private keys?\b|api keys?\b|access tokens?\b|passwords?\b|"
    r"secrets?\b|system prompt\b|developer prompt\b|hidden instructions?\b|id_rsa\b|"
    r"id_ed25519\b|/etc/shadow\b|instance credentials?\b)"
)
_SECRET_EXFILTRATION_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\b(?:read|show|print|dump|cat|reveal|expose|leak|exfiltrate|steal|send|list|give me)\b"
        rf".{{0,64}}{_SECRET_OBJECT}",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        rf"{_SECRET_OBJECT}.{{0,48}}\b(?:read|show|print|dump|reveal|leak|exfiltrate)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\b169\.254\.169\.254\b"),
)
_PROMPT_OVERRIDE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\b.{0,32}\b(?:previous|prior|above|system|developer)\b"
        r".{0,24}\b(?:instructions?|prompts?|rules?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\b(?:jailbreak|developer mode|bypass (?:safety|policy|guardrails?|restrictions?))\b", re.I),
    re.compile(r"\bpretend\b.{0,48}\b(?:no restrictions?|rules? do not apply|without limitations?)\b", re.I | re.S),
)
_TOOL_BYPASS_RE = re.compile(
    r"\b(?:call|run|invoke|use)\b.{0,48}\b(?:tool|shell|run_shell|delete_file|write_file)\b"
    r".{0,64}\b(?:without approval|bypass|exfiltrate|steal|secret|credential)\b",
    re.IGNORECASE | re.DOTALL,
)

_PLACEHOLDER_VALUES = {
    "...",
    "changeme",
    "example",
    "placeholder",
    "redacted",
    "your-api-key",
    "your_api_key",
}


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = ord(char) - ord("0")
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


@dataclass(frozen=True)
class GuardrailPolicy:
    """Configurable local policy used by the cortex and API surfaces."""

    enabled: bool = True
    redact_secrets: bool = True
    redact_pii: bool = True
    block_secret_exfiltration: bool = True
    block_tool_bypass: bool = True

    def evaluate_input(self, text: str) -> GuardrailDecision:
        """Evaluate a user/tool-bound prompt before model or memory use."""
        original = text or ""
        if not self.enabled:
            return GuardrailDecision(GuardrailAction.ALLOW, original, "input")

        findings: list[GuardrailFinding] = []
        blocked_reason: str | None = None

        exfiltration = any(pattern.search(original) for pattern in _SECRET_EXFILTRATION_RES)
        override = any(pattern.search(original) for pattern in _PROMPT_OVERRIDE_RES)
        tool_bypass = bool(_TOOL_BYPASS_RE.search(original))

        if tool_bypass:
            findings.append(
                GuardrailFinding(
                    category="tool_bypass",
                    action=GuardrailAction.BLOCK if self.block_tool_bypass else GuardrailAction.FLAG,
                    severity="high",
                    detail="Request attempts to bypass tool approval or use tools for exfiltration.",
                )
            )
            if self.block_tool_bypass:
                blocked_reason = "tool approval and safety controls cannot be bypassed"

        if exfiltration:
            findings.append(
                GuardrailFinding(
                    category="secret_exfiltration",
                    action=(
                        GuardrailAction.BLOCK if self.block_secret_exfiltration else GuardrailAction.FLAG
                    ),
                    severity="critical",
                    detail="Request asks for credentials, secrets, or hidden instructions.",
                )
            )
            if self.block_secret_exfiltration and blocked_reason is None:
                blocked_reason = "credentials, secrets, and hidden instructions cannot be revealed"

        if override and not exfiltration:
            findings.append(
                GuardrailFinding(
                    category="prompt_override",
                    action=GuardrailAction.FLAG,
                    severity="high",
                    detail="Prompt-override language was detected and will not change system policy.",
                )
            )

        sanitized, redaction_findings = self._redact(original, "input")
        findings.extend(redaction_findings)

        if blocked_reason is not None:
            action = GuardrailAction.BLOCK
        elif redaction_findings:
            action = GuardrailAction.REDACT
        elif findings:
            action = GuardrailAction.FLAG
        else:
            action = GuardrailAction.ALLOW
        return GuardrailDecision(
            action=action,
            text=sanitized,
            stage="input",
            findings=tuple(findings),
            blocked_reason=blocked_reason,
        )

    def evaluate_output(self, text: str) -> GuardrailDecision:
        """Scrub a model/tool response before it is displayed or persisted."""
        original = text or ""
        if not self.enabled:
            return GuardrailDecision(GuardrailAction.ALLOW, original, "output")
        sanitized, findings = self._redact(original, "output")
        return GuardrailDecision(
            action=GuardrailAction.REDACT if findings else GuardrailAction.ALLOW,
            text=sanitized,
            stage="output",
            findings=tuple(findings),
        )

    # Backwards-friendly short names for adapters and scripts.
    def inspect_input(self, text: str) -> GuardrailDecision:
        return self.evaluate_input(text)

    def inspect_output(self, text: str) -> GuardrailDecision:
        return self.evaluate_output(text)

    def _redact(self, text: str, stage: str) -> tuple[str, list[GuardrailFinding]]:
        findings: list[GuardrailFinding] = []
        sanitized = text

        if self.redact_secrets:
            sanitized, count = _PRIVATE_KEY_RE.subn("[REDACTED_PRIVATE_KEY]", sanitized)
            if count:
                findings.append(
                    GuardrailFinding("secret", GuardrailAction.REDACT, "critical", count, "Private key material")
                )

            secret_count = 0
            for pattern in _SECRET_PATTERNS:
                sanitized, count = pattern.subn("[REDACTED_SECRET]", sanitized)
                secret_count += count
            sanitized, count = _BEARER_RE.subn(r"\1[REDACTED_SECRET]", sanitized)
            secret_count += count
            sanitized, count = _URL_CREDENTIAL_RE.subn(r"\1[REDACTED_SECRET]\3", sanitized)
            secret_count += count

            assignment_count = 0

            def replace_assignment(match: re.Match[str]) -> str:
                nonlocal assignment_count
                raw_value = match.group(3).strip("\"'")
                normalized = raw_value.lower().strip("[]<>")
                if normalized in _PLACEHOLDER_VALUES or set(normalized) <= {"*"}:
                    return match.group(0)
                assignment_count += 1
                return f"{match.group(1)}{match.group(2)}[REDACTED_SECRET]"

            sanitized = _ASSIGNMENT_RE.sub(replace_assignment, sanitized)
            secret_count += assignment_count
            if secret_count:
                findings.append(
                    GuardrailFinding(
                        "secret",
                        GuardrailAction.REDACT,
                        "high",
                        secret_count,
                        f"Credential-like value in {stage} text",
                    )
                )

        if self.redact_pii:
            pii_count = 0
            sanitized, count = _EMAIL_RE.subn("[REDACTED_EMAIL]", sanitized)
            pii_count += count
            sanitized, count = _SSN_RE.subn("[REDACTED_PII]", sanitized)
            pii_count += count
            sanitized, count = _PHONE_RE.subn("[REDACTED_PHONE]", sanitized)
            pii_count += count

            card_count = 0

            def replace_card(match: re.Match[str]) -> str:
                nonlocal card_count
                digits = re.sub(r"\D", "", match.group(0))
                if 13 <= len(digits) <= 19 and _luhn_valid(digits):
                    card_count += 1
                    return "[REDACTED_PAYMENT_CARD]"
                return match.group(0)

            sanitized = _CARD_CANDIDATE_RE.sub(replace_card, sanitized)
            pii_count += card_count
            if pii_count:
                findings.append(
                    GuardrailFinding(
                        "pii",
                        GuardrailAction.REDACT,
                        "medium",
                        pii_count,
                        f"Personal or payment data in {stage} text",
                    )
                )

        return sanitized, findings


def combine_guardrail_decisions(*decisions: GuardrailDecision | None) -> dict[str, Any] | None:
    """Combine stage decisions into one JSON-safe run metadata object."""
    present = [decision for decision in decisions if decision is not None]
    if not present:
        return None
    if any(decision.blocked for decision in present):
        action = GuardrailAction.BLOCK
    elif any(decision.redacted for decision in present):
        action = GuardrailAction.REDACT
    elif any(decision.action is GuardrailAction.FLAG for decision in present):
        action = GuardrailAction.FLAG
    else:
        action = GuardrailAction.ALLOW
    return {
        "action": action.value,
        "stages": [decision.to_dict() for decision in present],
        "findings": [finding.to_dict() for decision in present for finding in decision.findings],
        "redaction_count": sum(decision.to_dict()["redaction_count"] for decision in present),
    }


# A shared immutable default is safe: policy objects carry configuration only.
DEFAULT_GUARDRAIL_POLICY = GuardrailPolicy()
