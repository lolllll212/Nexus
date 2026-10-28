"""Adaptive execution profiles and deterministic answer-quality checks.

This module is the pure-domain core of Nexus's Elite Execution Engine.  It
turns the existing :class:`~nexus.domain.value_objects.solution_brief.SolutionBrief`
into an auditable work contract: how much effort a request deserves, which
kinds of evidence are required before the model may claim success, which
sampling budget to use, and how many bounded repair passes are allowed.

The quality gate is deliberately conservative and evidence-based.  It does
not pretend to judge taste or prove that one base model is universally
better than another.  It catches failures that make agent work unreliable in
practice: unsupported "done" claims, missing tools or sources, ignored tool
failures, broken output formats, omitted files/constraints, unverified code
changes, and shallow answers to compound requests.  The cortex can then ask
the model to gather evidence or revise the draft before anything reaches the
user.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from nexus.domain.value_objects.coding_excellence import (
    CodingProfile,
    analyze_coding_request,
    assess_coding_answer,
    build_coding_contract,
    normalize_coding_focus,
)
from nexus.domain.value_objects.solution_brief import (
    SolutionBrief,
    analyze_solution_request,
    detect_read_only_tool_call,
)

EFFORT_LEVELS = ("auto", "fast", "balanced", "deep", "max")
_EFFORT_ORDER = {"fast": 0, "balanced": 1, "deep": 2, "max": 3}
_EFFORT_ALIASES = {
    "": "auto",
    "automatic": "auto",
    "quick": "fast",
    "rapid": "fast",
    "standard": "balanced",
    "default": "balanced",
    "normal": "balanced",
    "thorough": "deep",
    "research": "deep",
    "maximum": "max",
    "ultra": "max",
    "highest": "max",
}

_RESEARCH_TOOLS = frozenset({"web_search", "web_fetch", "http_request"})
_CALCULATION_TOOLS = frozenset({"calculator", "run_python"})
_MUTATION_TOOLS = frozenset(
    {
        "batch_edit_files",
        "copy_path",
        "create_directory",
        "create_repository",
        "delete_directory",
        "delete_file",
        "edit_file",
        "json_transform",
        "move_path",
        "write_file",
        "write_files",
    }
)
_VERIFICATION_TOOLS = frozenset(
    {
        "code_diagnostics",
        "dependency_audit",
        "git_diff",
        "project_checks",
        "pytest_runner",
        "release_readiness",
        "run_python",
        "secret_scan",
    }
)
_WORKSPACE_EVIDENCE_TOOLS = frozenset(
    {
        "changelog_draft",
        "code_diagnostics",
        "code_search_semantic",
        "csv_query",
        "dependency_audit",
        "directory_tree",
        "file_outline",
        "find_databases",
        "find_files",
        "find_symbol",
        "git_diff",
        "git_info",
        "grep",
        "json_query",
        "list_directory",
        "process_multimodal_media",
        "project_checks",
        "project_scan",
        "pytest_runner",
        "query_database",
        "read_file",
        "read_files",
        "regex_extract",
        "release_readiness",
        "secret_scan",
    }
)

_TOOL_WORKSTREAMS = frozenset(
    {
        "calculation",
        "code_change",
        "current_research",
        "data_analysis",
        "diagnosis_and_fix",
        "file_change",
        "git_inspection",
        "repository_creation",
        "verification",
        "workspace_inspection",
    }
)
_MUTATION_WORKSTREAMS = frozenset({"code_change", "file_change", "repository_creation"})

_URL_RE = re.compile(r"https?://[^\s)\]]+", re.I)
_MEMORY_CITATION_RE = re.compile(r"\[M\d+\]")
_CODE_FENCE_RE = re.compile(r"```")
_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.M,
)
_LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", re.M)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.M)
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+", re.M)
_CHECKLIST_RE = re.compile(r"^\s*(?:[-*+]\s+\[[ xX]\]|\d+[.)]\s+|[-*+]\s+)", re.M)
_STRUCTURE_RE = re.compile(r"(^#{1,6}\s+|^\s*(?:[-*+]\s+|\d+[.)]\s+)|\|.+\||```)", re.M)
_SUCCESS_CLAIM_RE = re.compile(
    r"\b(?:done|completed|complete|finished|fixed|resolved|implemented|created|updated|"
    r"changed|written|successfully|all set|ready to use|tests? (?:pass|passed|passing)|"
    r"verified|works now|working now)\b",
    re.I,
)
_VERIFIED_CLAIM_RE = re.compile(
    r"\b(?:tests? (?:pass|passed|passing)|test suite (?:passes|passed)|verified|"
    r"build (?:passes|passed|succeeds)|lint (?:passes|passed)|all checks pass)\b",
    re.I,
)
_EXTERNAL_CLAIM_RE = re.compile(
    r"\b(?:I(?:'ve| have)?\s+)?(?:sent|emailed|deployed|published|pushed|merged|"
    r"booked|paid|submitted)\b",
    re.I,
)
_BLOCKER_RE = re.compile(
    r"\b(?:blocked|blocker|could not|couldn't|cannot|can't|unable|failed|failure|error|"
    r"approval|permission|not completed|not changed|pending|needs? (?:your )?"
    r"(?:approval|input|confirmation)|access (?:was )?denied|timed out|not found)\b",
    re.I,
)
_FUTURE_PROMISE_RE = re.compile(
    r"\b(?:I(?:'ll| will)|let me|I'm going to|I am going to)\b[^.!?]{0,80}"
    r"\b(?:check|inspect|look|search|fix|create|write|run|start|do that)\b",
    re.I,
)
_SOURCE_CLAIM_RE = re.compile(
    r"\b(?:according to|source[s]? (?:say|show|report)|official(?:ly)?|reuters|"
    r"associated press|press release)\b|\[\d+\]",
    re.I,
)
_MEMORY_CLAIM_RE = re.compile(
    r"\b(?:you (?:previously|earlier|already)|we (?:previously )?(?:decided|discussed)|"
    r"as (?:we )?(?:discussed|decided)|your saved|from (?:our|the) (?:previous|earlier))\b",
    re.I,
)
_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "and",
        "are",
        "can",
        "could",
        "for",
        "from",
        "have",
        "into",
        "make",
        "please",
        "that",
        "the",
        "then",
        "this",
        "using",
        "want",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
        "you",
        "your",
    }
)


def normalize_effort(value: str | None) -> str:
    """Normalize a user/API effort value to one of :data:`EFFORT_LEVELS`."""

    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized in EFFORT_LEVELS:
        return normalized
    return _EFFORT_ALIASES.get(normalized, "auto")


def _at_least(current: str, minimum: str) -> str:
    return minimum if _EFFORT_ORDER[minimum] > _EFFORT_ORDER[current] else current


def _detect_formats(
    message: str,
    brief: SolutionBrief,
    coding_profile: CodingProfile | None = None,
) -> tuple[str, ...]:
    text = f" {message.lower()} "
    formats: list[str] = []

    def add(name: str) -> None:
        if name not in formats:
            formats.append(name)

    if re.search(
        r"\b(?:as|in|return|output|valid|raw)(?:\s+only)?\s+json\b|"
        r"\bonly\s+json\b|\bjson\s+(?:object|only|format)\b",
        text,
    ):
        add("json")
    if "output format: table" in {constraint.lower() for constraint in brief.constraints} or re.search(
        r"\b(?:markdown\s+table|as\s+a\s+table|in\s+a\s+table|table\s+format|tabular)\b", text
    ):
        add("table")
    if "checklist" in text:
        add("checklist")
    if re.search(r"\b(?:bullet\s+points?|bulleted\s+list|bullet\s+list)\b", text):
        add("bullet_list")
    if re.search(r"\b(?:numbered\s+list|numbered\s+steps?)\b", text):
        add("numbered_list")
    if re.search(r"\b(?:one|single)[-\s]+sentence\b", text):
        add("one_sentence")
    if "code block" in text or "fenced code" in text:
        add("code")
    elif brief.operation_level == "answer_only" and re.search(
        r"\b(?:write|create|implement|code|function|script|program|snippet|markup)\b", text
    ) and (
        bool(coding_profile and (coding_profile.languages or coding_profile.is_frontend))
        or re.search(
            r"\b(?:python|javascript|typescript|java|c\+\+|rust|php|ruby|html5?|xml|css|go|sql|bash|shell|function|script|program|code)\b",
            text,
        )
    ):
        # A request to *produce code in chat* should return a reusable fenced
        # block.  Workspace edits are exempt: the file itself is the artifact.
        add("code")
    return tuple(formats)


@dataclass(frozen=True)
class ExecutionProfile:
    """One request's adaptive effort, sampling, and evidence contract."""

    request_text: str = field(repr=False)
    brief: SolutionBrief
    requested_effort: str = "auto"
    effective_effort: str = "balanced"
    complexity: float = 0.0
    temperature: float = 0.3
    max_tokens: int = 2600
    repair_attempts: int = 1
    min_quality_score: int = 78
    mode: str = "general"
    has_images: bool = False
    needs_tools: bool = False
    needs_current_sources: bool = False
    needs_workspace_evidence: bool = False
    needs_calculation: bool = False
    needs_verification: bool = False
    needs_memory_citations: bool = False
    required_formats: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    coding_profile: CodingProfile | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return API-safe metadata; the raw request is intentionally omitted."""

        return {
            "requested_effort": self.requested_effort,
            "effective_effort": self.effective_effort,
            "complexity": round(float(self.complexity), 3),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "repair_attempts": self.repair_attempts,
            "min_quality_score": self.min_quality_score,
            "mode": self.mode,
            "has_images": self.has_images,
            "intent": self.brief.intent,
            "operation_level": self.brief.operation_level,
            "readiness": self.brief.readiness,
            "workstreams": list(self.brief.workstreams),
            "needs_tools": self.needs_tools,
            "needs_current_sources": self.needs_current_sources,
            "needs_workspace_evidence": self.needs_workspace_evidence,
            "needs_calculation": self.needs_calculation,
            "needs_verification": self.needs_verification,
            "needs_memory_citations": self.needs_memory_citations,
            "required_formats": list(self.required_formats),
            "expected_tools": list(self.expected_tools),
            "reasons": list(self.reasons),
            "coding": self.coding_profile.as_dict() if self.coding_profile else None,
            "coding_languages": list(self.coding_profile.languages if self.coding_profile else ()),
            "frontend_kind": self.coding_profile.frontend_kind if self.coding_profile else None,
        }


def build_execution_profile(
    message: str,
    *,
    history: Sequence[str] | str | None = None,
    requested_effort: str = "auto",
    mode: str = "general",
    extended_thinking: bool = False,
    deep_research: bool = False,
    has_images: bool = False,
    brief: SolutionBrief | None = None,
    coding_focus: str | None = None,
) -> ExecutionProfile:
    """Build the effort/evidence profile for one user request."""

    request_text = " ".join(str(message or "").split())
    solution = brief or analyze_solution_request(request_text, history=history)
    requested = normalize_effort(requested_effort)
    normalized_mode = str(mode or "general").strip().lower() or "general"
    workstreams = set(solution.workstreams)
    lower = request_text.lower()
    normalized_focus = normalize_coding_focus(coding_focus or normalized_mode)
    coding_profile = analyze_coding_request(
        request_text,
        mode=normalized_mode,
        focus=normalized_focus,
        paths=solution.referenced_paths,
        workstreams=solution.workstreams,
        operation_level=solution.operation_level,
        repository_template=solution.repository.template if solution.repository else None,
    )
    coding_mode = bool(
        normalized_mode == "coding" or normalized_focus != "auto" or coding_profile.is_coding
    )

    reasons: list[str] = []
    complexity = 0.12
    complexity += min(len(request_text) / 1800.0, 0.18)
    if len(workstreams) > 1:
        complexity += min(0.09 * (len(workstreams) - 1), 0.27)
        reasons.append("compound_workstreams")
    if workstreams & _MUTATION_WORKSTREAMS or solution.repository is not None:
        complexity += 0.14
        reasons.append("workspace_action")
    if solution.needs_current_info or deep_research:
        complexity += 0.12
        reasons.append("current_evidence")
    if "verification" in workstreams:
        complexity += 0.08
        reasons.append("verification_required")
    if workstreams & {"calculation", "data_analysis"}:
        complexity += 0.07
        reasons.append("exact_calculation_or_data")
    if solution.constraints:
        complexity += min(0.035 * len(solution.constraints), 0.12)
        reasons.append("explicit_constraints")
    if len(solution.deliverables) > 1:
        complexity += 0.06
        reasons.append("multiple_deliverables")
    if solution.sensitive_domain or solution.urgent:
        complexity += 0.08
        reasons.append("sensitive_or_urgent")
    if "```" in request_text or "traceback" in lower or "exception" in lower:
        complexity += 0.1
        reasons.append("technical_context")
    if has_images:
        complexity += 0.08
        reasons.append("visual_input")
    if coding_mode:
        complexity += 0.12 + coding_profile.complexity_boost
        reasons.append("coding_mode")
        reasons.extend(coding_profile.reasons)
    if extended_thinking:
        complexity += 0.07
        reasons.append("extended_thinking")
    if deep_research:
        complexity += 0.1
        reasons.append("deep_research")
    complexity = max(0.0, min(1.0, complexity))

    simple = (
        solution.intent in {"direct_answer", "greeting"}
        and len(workstreams) <= 1
        and not solution.needs_current_info
        and not solution.sensitive_domain
        and not has_images
        and not coding_mode
    )
    if requested != "auto":
        effective = requested
        reasons.append("user_selected_effort")
    elif simple and complexity < 0.34:
        effective = "fast"
        reasons.append("simple_request")
    elif complexity < 0.3:
        effective = "fast"
    elif complexity < 0.58:
        effective = "balanced"
    elif complexity < 0.84:
        effective = "deep"
    else:
        effective = "max"

    # Explicit user controls are floors for the corresponding work, not
    # decorative labels.  A manually selected Fast stays Fast unless the user
    # also turned on deep research/extended thinking.
    if deep_research:
        effective = _at_least(effective, "deep")
    if extended_thinking and complexity >= 0.45:
        effective = _at_least(effective, "deep")
    if coding_mode and requested == "auto":
        effective = _at_least(effective, "balanced")
    if (
        coding_profile.is_frontend
        and requested == "auto"
        and (
            workstreams & _MUTATION_WORKSTREAMS
            or solution.repository is not None
            or re.search(r"\b(?:build|create|design|implement|redesign|make)\b", lower)
        )
    ):
        effective = _at_least(effective, "deep")
    if workstreams & _MUTATION_WORKSTREAMS and requested == "auto":
        effective = _at_least(effective, "deep")
    if solution.sensitive_domain and requested == "auto":
        effective = _at_least(effective, "balanced")
    if solution.needs_current_info and requested == "auto":
        effective = _at_least(effective, "balanced")

    temperature_by_effort = {"fast": 0.35, "balanced": 0.3, "deep": 0.22, "max": 0.18}
    temperature = temperature_by_effort[effective]
    creative = bool(
        re.search(r"\b(?:story|poem|brainstorm|creative|names? for|song|joke)\b", lower)
    ) and not (workstreams & _TOOL_WORKSTREAMS)
    if creative:
        temperature = {"fast": 0.65, "balanced": 0.6, "deep": 0.55, "max": 0.5}[effective]
        reasons.append("creative_generation")
    elif workstreams & {"calculation", "code_change", "diagnosis_and_fix"} or coding_mode:
        temperature = min(temperature, 0.28 if coding_profile.is_frontend else 0.25)
    if solution.sensitive_domain:
        temperature = min(temperature, 0.2)

    formats = _detect_formats(request_text, solution, coding_profile)
    needs_current = bool(solution.needs_current_info or deep_research)
    needs_workspace = bool(
        workstreams
        & {
            "code_change",
            "data_analysis",
            "diagnosis_and_fix",
            "file_change",
            "git_inspection",
            "repository_creation",
            "verification",
            "workspace_inspection",
        }
        or (solution.referenced_paths and solution.operation_level != "answer_only")
    )
    # Suggested tools are opportunities, not acceptance criteria.  Require a
    # calculator only for an explicit calculation workstream; a price
    # comparison may benefit from one but is not an arithmetic proof task.
    needs_calculation = "calculation" in workstreams
    needs_verification = bool(
        "verification" in workstreams
        or workstreams & _MUTATION_WORKSTREAMS
        or re.search(r"\b(?:run|execute|check|verify|test|validate|lint|build)\b", lower)
    )
    needs_tools = bool(
        needs_current
        or needs_workspace
        or needs_calculation
        or workstreams & _TOOL_WORKSTREAMS
        or solution.repository is not None
    )
    needs_memory = bool(
        re.search(
            r"\b(?:remember|previously|earlier|last time|we decided|we discussed|"
            r"what did (?:i|we)|my saved|our decision)\b",
            lower,
        )
    )
    expected_tools = list(solution.suggested_tools)
    if coding_profile.is_coding and (needs_workspace or solution.repository is not None):
        for tool in ("project_scan", "code_diagnostics", "project_checks"):
            if tool not in expected_tools:
                expected_tools.append(tool)

    return ExecutionProfile(
        request_text=request_text,
        brief=solution,
        requested_effort=requested,
        effective_effort=effective,
        complexity=complexity,
        temperature=temperature,
        max_tokens={"fast": 1400, "balanced": 2600, "deep": 4600, "max": 8192}[effective],
        repair_attempts={"fast": 1, "balanced": 1, "deep": 2, "max": 3}[effective],
        min_quality_score={"fast": 70, "balanced": 78, "deep": 85, "max": 90}[effective],
        mode=normalized_mode,
        has_images=has_images,
        needs_tools=needs_tools,
        needs_current_sources=needs_current,
        needs_workspace_evidence=needs_workspace,
        needs_calculation=needs_calculation,
        needs_verification=needs_verification,
        needs_memory_citations=needs_memory,
        required_formats=formats,
        expected_tools=tuple(expected_tools),
        reasons=tuple(dict.fromkeys(reasons)),
        coding_profile=coding_profile if coding_profile.is_coding else None,
    )


def build_execution_contract(profile: ExecutionProfile) -> str:
    """Render a compact, model-facing contract for the current task."""

    brief = profile.brief
    evidence: list[str] = []
    if profile.needs_current_sources:
        evidence.append("current sources with links/dates")
    if profile.needs_workspace_evidence:
        evidence.append("actual workspace/tool observations")
    if profile.needs_calculation:
        evidence.append("tool-checked or explicitly shown arithmetic")
    if profile.needs_verification:
        evidence.append("targeted verification after any change")
    if profile.needs_memory_citations:
        evidence.append("[M#] citations for recalled facts")
    if not evidence:
        evidence.append("the user's supplied facts; do not invent missing facts")

    lines = [
        (
            f"ELITE EXECUTION CONTRACT — effort={profile.effective_effort}, "
            f"complexity={profile.complexity:.2f}. Keep a silent task ledger and "
            "finish every workstream before FINAL ANSWER."
        ),
        f"Outcome: {brief.goal}",
    ]
    if brief.workstreams:
        lines.append("Workstreams: " + ", ".join(brief.workstreams) + ".")
    if brief.referenced_paths:
        lines.append("Paths in scope: " + ", ".join(brief.referenced_paths[:6]) + ".")
    if brief.constraints:
        lines.append("Hard constraints: " + "; ".join(brief.constraints[:6]) + ".")
    if profile.required_formats:
        lines.append("Required format: " + ", ".join(profile.required_formats) + ".")
    lines.append("Evidence required: " + "; ".join(evidence) + ".")
    if profile.coding_profile is not None:
        coding_contract = build_coding_contract(profile.coding_profile, max_chars=520)
        if coding_contract:
            lines.append(coding_contract)
    lines.append(
        "Before answering, silently audit: requested parts covered, claims backed "
        "by observations, tool failures disclosed, mutations verified, format exact, "
        "and blockers stated instead of guessed. Never say done/tested/sent unless "
        "an observation proves it."
    )
    rendered = "\n".join(lines)
    if len(rendered) > 1400 and profile.coding_profile is not None:
        compact = build_coding_contract(profile.coding_profile, max_chars=300)
        lines = [compact if line.startswith("CODING EXCELLENCE") else line for line in lines]
        rendered = "\n".join(lines)
    return rendered[:1400]


@dataclass(frozen=True)
class QualityIssue:
    """One objective reason a draft answer is not ready to ship."""

    code: str
    severity: str  # critical | major | minor
    detail: str
    repair_instruction: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
            "repair_instruction": self.repair_instruction,
        }


@dataclass(frozen=True)
class ResponseQualityReport:
    """Deterministic quality verdict for one candidate/final answer."""

    score: int
    passed: bool
    status: str = "needs_repair"
    issues: tuple[QualityIssue, ...] = ()
    checks: tuple[str, ...] = ()
    word_count: int = 0
    tools_used: tuple[str, ...] = ()
    repair_attempts_used: int = 0

    @property
    def blocking_issues(self) -> tuple[QualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity in {"critical", "major"})

    def with_repair_attempts(self, attempts: int, *, exhausted: bool = False) -> ResponseQualityReport:
        status = "verified" if self.passed else ("degraded" if exhausted else "needs_repair")
        return replace(self, repair_attempts_used=max(0, int(attempts)), status=status)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
            "checks": list(self.checks),
            "word_count": self.word_count,
            "tools_used": list(self.tools_used),
            "repair_attempts_used": self.repair_attempts_used,
        }


def _safe_eval_expression(expression: str) -> float | None:
    """Evaluate a tiny arithmetic subset without executing arbitrary code."""

    try:
        tree = ast.parse(str(expression), mode="eval")
    except (SyntaxError, ValueError):
        return None

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
        ):
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            return left**right
        raise ValueError("unsupported expression")

    try:
        result = visit(tree)
    except (ArithmeticError, ValueError, OverflowError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def _expected_calculation(profile: ExecutionProfile) -> float | None:
    if not profile.needs_calculation:
        return None
    call = detect_read_only_tool_call(profile.request_text)
    if call is None or call.tool_id != "calculator":
        return None
    expression = call.params().get("expression")
    return _safe_eval_expression(str(expression)) if expression is not None else None


_NUMBER_WORD_VALUES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_NUMBER_SCALE_VALUES = {
    "hundred": 100,
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
}


def _number_words_in(text: str) -> list[float]:
    """Extract simple English number phrases such as ``twenty-four``.

    This is used only for explicit calculation checks. Number words are not
    enabled for general constraint matching, where words such as "one" are
    often pronouns rather than quantities.
    """

    tokens = re.findall(r"[a-z]+", str(text or "").lower())
    numbers: list[float] = []
    index = 0
    while index < len(tokens):
        start = index
        negative = False
        if tokens[index] in {"minus", "negative"} and index + 1 < len(tokens):
            negative = True
            index += 1

        token = tokens[index] if index < len(tokens) else ""
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        starts_number = (
            token in _NUMBER_WORD_VALUES
            or token in _NUMBER_SCALE_VALUES
            or (token == "a" and next_token in _NUMBER_SCALE_VALUES)
        )
        if not starts_number:
            index = start + 1
            continue

        total = 0.0
        current = 0.0
        consumed = False
        while index < len(tokens):
            token = tokens[index]
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            if (
                token == "and"
                and consumed
                and (next_token in _NUMBER_WORD_VALUES or next_token in _NUMBER_SCALE_VALUES)
            ):
                index += 1
                continue
            if token in _NUMBER_WORD_VALUES:
                current += float(_NUMBER_WORD_VALUES[token])
                consumed = True
                index += 1
                continue
            if token == "a" and next_token in _NUMBER_SCALE_VALUES:
                current += 1.0
                consumed = True
                index += 1
                continue
            if token in _NUMBER_SCALE_VALUES:
                scale = float(_NUMBER_SCALE_VALUES[token])
                if scale == 100:
                    current = (current or 1.0) * scale
                else:
                    total += (current or 1.0) * scale
                    current = 0.0
                consumed = True
                index += 1
                continue
            break

        if not consumed:
            index = start + 1
            continue

        value = total + current
        if index < len(tokens) and tokens[index] == "point":
            digits: list[str] = []
            digit_index = index + 1
            while digit_index < len(tokens):
                digit = _NUMBER_WORD_VALUES.get(tokens[digit_index])
                if digit is None or digit > 9:
                    break
                digits.append(str(digit))
                digit_index += 1
            if digits:
                value += float("0." + "".join(digits))
                index = digit_index
        numbers.append(-value if negative else value)
    return numbers


def _numbers_in(text: str, *, include_words: bool = False) -> list[float]:
    numbers: list[float] = []
    for raw in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", text or ""):
        try:
            numbers.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    if include_words:
        numbers.extend(_number_words_in(text))
    return numbers


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return ("%f" % value).rstrip("0").rstrip(".")


def _observation_texts(observations: Sequence[Any]) -> list[str]:
    texts: list[str] = []
    for item in observations:
        if item is None:
            continue
        if isinstance(item, Mapping):
            try:
                texts.append(json.dumps(dict(item), default=str)[:4000])
            except (TypeError, ValueError):
                texts.append(str(item)[:4000])
        else:
            texts.append(str(item)[:4000])
    return texts


def _valid_json_answer(answer: str) -> bool:
    candidate = answer.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.I | re.S)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        json.loads(candidate)
        return True
    except (json.JSONDecodeError, TypeError, ValueError):
        return False


def _format_constraint_satisfied(
    value: str,
    candidate: str,
    satisfied_formats: set[str],
) -> bool:
    """Whether a format phrased as a generic constraint was actually met.

    The solution brief may preserve an instruction such as ``only JSON with
    a "result" field`` as an explicit constraint. That instruction should be
    validated by parsing the answer, not by requiring the instruction text
    itself to appear inside the JSON (which would make the request
    impossible to satisfy).
    """

    normalized = " ".join(str(value or "").lower().split())
    if not normalized or not satisfied_formats:
        return False

    # Do not let a format match erase a separate numeric hard constraint
    # packed into the same phrase (e.g. "table under 20000").
    value_numbers = _numbers_in(normalized)
    if value_numbers:
        answer_numbers = _numbers_in(candidate, include_words=True)
        if not all(
            any(
                abs(expected - actual) <= max(0.01, abs(expected) * 0.001)
                for actual in answer_numbers
            )
            for expected in value_numbers
        ):
            return False

    if "json" in satisfied_formats and re.search(r"\bjson\b", normalized):
        fields = re.findall(r"[\"']([^\"']+)[\"']\s+fields?\b", normalized)
        if not fields:
            return True
        payload_text = candidate.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", payload_text, re.I | re.S)
        if fenced:
            payload_text = fenced.group(1).strip()
        try:
            payload = json.loads(payload_text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return False
        return isinstance(payload, dict) and all(field in payload for field in fields)

    format_terms = {
        "table": r"\b(?:table|tabular)\b",
        "code": r"\b(?:code block|fenced code)\b",
        "checklist": r"\bchecklist\b",
        "bullet_list": r"\b(?:bullet|bulleted)\b",
        "numbered_list": r"\bnumbered\b",
        "one_sentence": r"\b(?:one|single)[-\s]+sentence\b",
    }
    return any(
        required_format in satisfied_formats
        and re.search(pattern, normalized)
        for required_format, pattern in format_terms.items()
    )


def _constraint_value_present(value: str, answer: str) -> bool:
    normalized_value = " ".join(value.lower().split())
    normalized_answer = " ".join(answer.lower().split())
    if normalized_value in normalized_answer:
        return True
    value_numbers = _numbers_in(normalized_value)
    if value_numbers:
        answer_numbers = _numbers_in(normalized_answer)
        if all(
            any(abs(expected - actual) <= max(0.01, abs(expected) * 0.001) for actual in answer_numbers)
            for expected in value_numbers
        ):
            return True
    compact_value = re.sub(r"[₹$€£,\s]", "", normalized_value)
    compact_answer = re.sub(r"[₹$€£,\s]", "", normalized_answer)
    return bool(compact_value and compact_value in compact_answer)


def _substantive_terms(text: str) -> set[str]:
    """Return relevance terms without counting identifier fragments.

    A wrapper may include opaque IDs (for example swarm worker UUIDs) around
    a very short task. Splitting those IDs into alphabetic fragments must not
    manufacture a substantive request and trigger a false off-task repair.
    Digit-bearing whitespace tokens are therefore ignored here; referenced
    paths are already handled by dedicated checks.
    """

    terms: set[str] = set()
    for raw_token in re.findall(r"\S+", str(text or "")):
        if any(character.isdigit() for character in raw_token):
            continue
        for word in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", raw_token):
            normalized = word.lower()
            if len(normalized) >= 3 and normalized not in _STOPWORDS:
                terms.add(normalized)
    return terms


def assess_response_quality(
    profile: ExecutionProfile,
    answer: str,
    *,
    tools_used: Sequence[str] = (),
    observations: Sequence[Any] = (),
    context_sources: Sequence[Mapping[str, Any] | str] = (),
) -> ResponseQualityReport:
    """Assess whether a draft answer is complete, grounded, and safe to ship."""

    candidate = str(answer or "").strip()
    lower = candidate.lower()
    brief = profile.brief
    tools = tuple(dict.fromkeys(str(tool) for tool in tools_used if str(tool)))
    tool_set = set(tools)
    observation_text = "\n".join(_observation_texts(observations))
    observation_lower = observation_text.lower()
    word_count = len(re.findall(r"\S+", candidate))
    issues: list[QualityIssue] = []
    checks: list[str] = []

    def issue(code: str, severity: str, detail: str, repair: str) -> None:
        if not any(existing.code == code for existing in issues):
            issues.append(QualityIssue(code, severity, detail, repair))

    def passed(name: str) -> None:
        if name not in checks:
            checks.append(name)

    if not candidate:
        issue("empty_answer", "critical", "The draft answer is empty.", "Produce a complete answer.")
        return ResponseQualityReport(
            score=0,
            passed=False,
            status="needs_repair",
            issues=tuple(issues),
            checks=tuple(checks),
            word_count=0,
            tools_used=tools,
        )
    passed("nonempty_answer")

    if "final answer:" in lower or "tool_call:" in lower:
        issue(
            "protocol_leak",
            "critical",
            "Internal ReAct protocol text leaked into the user-visible answer.",
            "Remove protocol markers and return only the polished final answer.",
        )
    else:
        passed("no_protocol_leak")

    if re.search(r"\b(?:TODO|TBD|lorem ipsum|\[insert\b|implementation here)\b", candidate, re.I):
        issue(
            "placeholder_content",
            "major",
            "The draft still contains placeholder content.",
            "Replace placeholders with the requested content or clearly state the exact missing input.",
        )

    has_blocker_language = bool(_BLOCKER_RE.search(candidate))
    has_success_claim = bool(_SUCCESS_CLAIM_RE.search(candidate))

    if brief.readiness in {"clarify_first", "safety_first"}:
        if "?" in candidate and not has_success_claim:
            passed("clarification_first")
        elif has_success_claim:
            issue(
                "premature_completion_claim",
                "critical",
                "The request needs clarification/safety handling, but the draft claims completion.",
                "Ask the necessary clarifying or safety questions instead of claiming the task is done.",
            )
        else:
            issue(
                "missing_clarifying_question",
                "major",
                "The request is not ready to execute, but the draft does not ask what is missing.",
                "Ask concise clarifying questions and do not pretend the work was performed.",
            )

    if (
        profile.needs_tools
        and not tools
        and _FUTURE_PROMISE_RE.search(candidate)
        and word_count < 90
        and not has_blocker_language
    ):
        issue(
            "incomplete_promise",
            "major",
            "The draft promises future work instead of doing it.",
            "Use the necessary tools now, then report the observed result or the exact blocker.",
        )

    # Explicit output formats are acceptance criteria, not styling hints.
    satisfied_formats: set[str] = set()
    for required_format in profile.required_formats:
        ok = True
        if required_format == "json":
            ok = _valid_json_answer(candidate)
        elif required_format == "table":
            ok = "|" in candidate and bool(_TABLE_SEPARATOR_RE.search(candidate))
        elif required_format == "code":
            ok = bool(_CODE_FENCE_RE.search(candidate))
        elif required_format == "checklist":
            ok = len(_CHECKLIST_RE.findall(candidate)) >= 2
        elif required_format == "bullet_list":
            ok = len(_BULLET_RE.findall(candidate)) >= 2
        elif required_format == "numbered_list":
            ok = len(_NUMBERED_RE.findall(candidate)) >= 2
        elif required_format == "one_sentence":
            without_links = _URL_RE.sub("", candidate)
            ok = len(re.findall(r"[.!?](?:\s|$)", without_links)) <= 1
        if ok:
            satisfied_formats.add(required_format)
            passed(f"format_{required_format}")
        else:
            issue(
                f"format_{required_format}",
                "major",
                f"The user explicitly requested {required_format.replace('_', ' ')} output.",
                f"Revise the answer into valid {required_format.replace('_', ' ')} format without losing content.",
            )

    if profile.coding_profile is not None:
        coding_findings, coding_checks = assess_coding_answer(profile.coding_profile, candidate)
        for finding in coding_findings:
            issue(finding.code, finding.severity, finding.detail, finding.repair_instruction)
        for check in coding_checks:
            passed(check)

    # Referenced files/directories must not silently disappear from the result.
    missing_paths: list[str] = []
    for path in brief.referenced_paths[:4]:
        if path == ".":
            continue
        basename = path.replace("\\", "/").rstrip("/").split("/")[-1]
        if path.lower() not in lower and basename.lower() not in lower:
            missing_paths.append(path)
    if missing_paths and not has_blocker_language:
        issue(
            "missing_path_coverage",
            "major",
            "The draft does not address referenced path(s): " + ", ".join(missing_paths) + ".",
            "Inspect/use each referenced path as requested and name the relevant file or exact blocker.",
        )
    elif brief.referenced_paths:
        passed("referenced_paths_covered")

    # Numeric/location/deadline constraints are checked lexically after
    # normalization; output-format and technology labels are handled elsewhere.
    missing_constraints: list[str] = []
    for constraint in brief.constraints:
        if ":" not in constraint:
            continue
        key, value = (part.strip() for part in constraint.split(":", 1))
        if key.lower() in {"output format", "technology"} or value.lower() in {"today", "now"}:
            continue
        if _format_constraint_satisfied(value, candidate, satisfied_formats):
            continue
        if len(value) >= 2 and not _constraint_value_present(value, candidate):
            missing_constraints.append(constraint)
    if missing_constraints and not has_blocker_language and brief.readiness != "clarify_first":
        issue(
            "missing_constraints",
            "major",
            "The draft omits explicit constraint(s): " + "; ".join(missing_constraints[:3]) + ".",
            "Respect and explicitly reflect every hard constraint, or explain why one cannot be met.",
        )
    elif brief.constraints:
        passed("constraints_reflected")

    expected_calculation = _expected_calculation(profile)
    if expected_calculation is not None:
        answer_numbers = _numbers_in(candidate, include_words=True)
        tolerance = max(0.01, abs(expected_calculation) * 0.000001)
        if any(abs(number - expected_calculation) <= tolerance for number in answer_numbers):
            passed("calculation_result")
        else:
            issue(
                "incorrect_calculation",
                "critical",
                f"The arithmetic result should be {_format_number(expected_calculation)}.",
                "Use the calculator, correct the arithmetic, and show the checked result.",
            )
    elif profile.needs_calculation:
        shown_arithmetic = bool(re.search(r"\d\s*(?:[+\-*/×÷%]|\*\*|=)", candidate))
        if tool_set & _CALCULATION_TOOLS or shown_arithmetic:
            passed("calculation_evidence")
        elif not has_blocker_language:
            issue(
                "missing_calculation_evidence",
                "major",
                "A numeric answer was given without a calculation tool or visible arithmetic.",
                "Use the calculator or show the arithmetic so the number can be checked.",
            )

    if profile.needs_current_sources and brief.readiness not in {"clarify_first", "safety_first"}:
        has_source_tool = bool(tool_set & _RESEARCH_TOOLS)
        has_url = bool(_URL_RE.search(candidate))
        has_currency_marker = bool(
            re.search(r"\b(?:as of|checked|current|currently|latest|today|20\d{2})\b", lower)
        )
        if has_source_tool and has_url and has_currency_marker:
            passed("current_source_evidence")
        elif not has_blocker_language:
            issue(
                "missing_current_evidence",
                "major",
                "Current information needs live source evidence, links, and a date/currency marker.",
                "Use web search/fetch, cite source URLs, state when the information was checked, and separate estimates from confirmed facts.",
            )

    if profile.needs_workspace_evidence and brief.readiness not in {"clarify_first", "safety_first"}:
        if tool_set & (_WORKSPACE_EVIDENCE_TOOLS | _MUTATION_TOOLS | _VERIFICATION_TOOLS):
            passed("workspace_evidence")
        elif not has_blocker_language:
            issue(
                "missing_workspace_evidence",
                "major",
                "The draft discusses workspace work without an inspection, data, Git, or verification tool observation.",
                "Inspect the relevant workspace evidence with tools before diagnosing, changing, or summarizing it.",
            )

    mutation_expected = bool(set(brief.workstreams) & _MUTATION_WORKSTREAMS or brief.repository)
    mutation_done = bool(tool_set & _MUTATION_TOOLS)
    if has_success_claim and mutation_expected and not mutation_done:
        if _EXTERNAL_CLAIM_RE.search(candidate) or re.search(
            r"\b(?:fixed|implemented|created|updated|changed|written|completed|done)\b", lower
        ):
            issue(
                "unsupported_action_claim",
                "critical",
                "The draft claims a workspace action was completed, but no mutation tool ran.",
                "Perform the approved mutation with a tool or honestly state that no change was made and why.",
            )
    elif mutation_expected and not mutation_done and not has_blocker_language:
        if brief.readiness not in {"clarify_first", "safety_first"}:
            issue(
                "action_not_executed",
                "major",
                "The user asked for a workspace/repository action, but no mutation tool ran.",
                "Carry out the requested action with the appropriate approved tool instead of only describing it.",
            )
    if mutation_done:
        passed("mutation_evidence")

    if _VERIFIED_CLAIM_RE.search(candidate) and not (tool_set & _VERIFICATION_TOOLS):
        issue(
            "unsupported_verification_claim",
            "critical",
            "The draft claims tests/checks passed without a verification tool observation.",
            "Run targeted verification and report its real outcome, or remove the passing claim.",
        )
    elif profile.needs_verification and (mutation_done or "verification" in brief.workstreams):
        if tool_set & _VERIFICATION_TOOLS:
            passed("verification_evidence")
        elif not has_blocker_language:
            issue(
                "missing_verification",
                "major",
                "A change or explicit verification request has no verification tool evidence.",
                "Run the targeted test/check/diagnostic tool and report the actual pass or failure.",
            )

    tool_failure = bool(
        re.search(
            r"(?:approval_required\s*[:=]\s*true|requires approval|\"ok\"\s*:\s*false|"
            r"\"success\"\s*:\s*false|permissionerror|traceback|timed out|"
            r"errors?\s*:|failed|not found|iserror\s*[:=]\s*true)",
            observation_lower,
        )
    )
    if tool_failure and has_success_claim and not has_blocker_language:
        issue(
            "contradicted_by_tool_evidence",
            "critical",
            "A tool observation indicates failure, approval, or missing data, but the draft still claims success.",
            "Align the answer with the tool observation: disclose the failure/blocker and do not claim completion.",
        )
    elif tools:
        passed("tool_outcomes_considered")

    if _EXTERNAL_CLAIM_RE.search(candidate) and not (
        tool_set & {"http_request", "web_fetch", "web_search"}
    ):
        # Sending/deploying/publishing is not proven by drafting text in chat.
        if re.search(r"\b(?:sent|emailed|deployed|published|pushed|merged|booked|paid|submitted)\b", lower):
            issue(
                "unsupported_external_action",
                "critical",
                "The draft claims an external action without evidence from a corresponding tool/result.",
                "Only claim the external action if a tool/result proves it; otherwise say it is drafted or pending.",
            )

    if _SOURCE_CLAIM_RE.search(candidate) and not (_URL_RE.search(candidate) or tool_set & _RESEARCH_TOOLS):
        issue(
            "unsupported_source_claim",
            "major",
            "The draft invokes a source without a link or research-tool evidence.",
            "Add a real source link or remove the source attribution and mark the statement as general guidance.",
        )

    source_count = len(tuple(context_sources))
    if _MEMORY_CLAIM_RE.search(candidate) and not _MEMORY_CITATION_RE.search(candidate):
        issue(
            "unsupported_memory_claim",
            "major",
            "The draft claims recalled prior context without an [M#] citation.",
            "Cite the relevant retrieved memory as [M#] or remove the memory claim.",
        )
    elif profile.needs_memory_citations and source_count and not _MEMORY_CITATION_RE.search(candidate):
        if not has_blocker_language:
            issue(
                "missing_memory_citation",
                "major",
                "The user asked Nexus to use prior context, but the answer has no [M#] citation.",
                "Use the cited context pack and place [M#] citations next to recalled facts.",
            )
    elif source_count:
        passed("context_citation_policy")

    workstream_count = len(brief.workstreams)
    if brief.readiness not in {"clarify_first", "safety_first"} and not has_blocker_language:
        if workstream_count >= 3 and word_count < 55:
            issue(
                "shallow_compound_answer",
                "major",
                "A compound request received an unusually terse answer.",
                "Cover every workstream with the result, evidence, verification, and any blockers.",
            )
        elif (
            profile.effective_effort in {"deep", "max"}
            and profile.complexity >= 0.75
            and word_count < 85
            and not (tools and _STRUCTURE_RE.search(candidate))
        ):
            issue(
                "insufficient_depth",
                "major",
                "The selected deep execution profile needs more complete coverage.",
                "Expand the answer with the missing analysis, evidence, trade-offs, or verification—not filler.",
            )
        elif workstream_count or profile.complexity >= 0.3:
            passed("task_depth")

        if workstream_count >= 3 and not _STRUCTURE_RE.search(candidate):
            issue(
                "missing_structure",
                "minor" if profile.effective_effort in {"fast", "balanced"} else "major",
                "A multi-part result is hard to audit without headings, a list, a table, or a code block.",
                "Structure the result so each requested part and its evidence can be checked quickly.",
            )

    if brief.sensitive_domain:
        definitive = bool(
            re.search(
                r"\b(?:you definitely have|diagnosed with|guaranteed returns?|risk[- ]free|"
                r"legally binding|100%\s+(?:safe|certain|legal))\b",
                lower,
            )
        )
        caveat = bool(
            re.search(
                r"\b(?:professional|doctor|lawyer|advisor|emergency|not a substitute|"
                r"general information|seek (?:medical|legal|professional))\b",
                lower,
            )
        )
        if definitive and not caveat:
            issue(
                "missing_sensitive_caveat",
                "major",
                "A sensitive-domain draft makes a definitive claim without an appropriate professional caveat.",
                "Soften unsupported certainty, state limits, and direct the user to a qualified professional when appropriate.",
            )
        else:
            passed("sensitive_domain_caveat")

    # A zero-overlap answer to a substantive request is usually off-task.
    # This check is intentionally last and narrow to avoid punishing synonyms.
    request_terms = _substantive_terms(profile.request_text)
    answer_terms = _substantive_terms(candidate)
    if (
        len(request_terms) >= 5
        and not (request_terms & answer_terms)
        and not brief.referenced_paths
        and brief.readiness not in {"clarify_first", "safety_first"}
        and not has_blocker_language
    ):
        issue(
            "off_task_answer",
            "major",
            "The draft shares no substantive vocabulary with the user's request.",
            "Answer the actual request directly and cover its named subject, constraints, and deliverable.",
        )
    elif request_terms:
        passed("task_relevance")

    penalty = sum(
        35 if item.severity == "critical" else 16 if item.severity == "major" else 6
        for item in issues
    )
    score = max(0, min(100, 100 - penalty))
    has_blocking = any(item.severity in {"critical", "major"} for item in issues)
    verdict_passed = not has_blocking and score >= profile.min_quality_score
    return ResponseQualityReport(
        score=score,
        passed=verdict_passed,
        status="verified" if verdict_passed else "needs_repair",
        issues=tuple(issues),
        checks=tuple(checks),
        word_count=word_count,
        tools_used=tools,
    )


def build_quality_repair_prompt(
    profile: ExecutionProfile,
    report: ResponseQualityReport,
    *,
    attempt: int,
) -> str:
    """Build a private ReAct instruction that repairs objective draft flaws."""

    lines = [
        f"QUALITY REPAIR {attempt}: Your draft FINAL ANSWER is not ready. Do not mention this gate.",
        "Fix only the objective problems below. You may call tools next when evidence is missing; otherwise return a revised FINAL ANSWER.",
        "Preserve correct content. Never fabricate tool results, sources, dates, tests, mutations, or external actions. If genuinely blocked, state the blocker plainly.",
    ]
    for item in report.blocking_issues[:8]:
        lines.append(f"- {item.code}: {item.repair_instruction}")
    if profile.expected_tools:
        lines.append(
            "Relevant tools for this task include: "
            + ", ".join(profile.expected_tools[:10])
            + "."
        )
    lines.append(
        "Before the next FINAL ANSWER, silently re-audit every workstream, path, constraint, requested format, and success claim against observations."
    )
    return "\n".join(lines)


__all__ = [
    "EFFORT_LEVELS",
    "ExecutionProfile",
    "QualityIssue",
    "ResponseQualityReport",
    "assess_response_quality",
    "build_execution_contract",
    "build_execution_profile",
    "build_quality_repair_prompt",
    "normalize_effort",
]
