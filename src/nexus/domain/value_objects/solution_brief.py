"""Deterministic real-world solution briefs.

This small, dependency-free domain service classifies what kind of outcome a
user is asking for and turns it into a compact operating brief for the cortex.
The live LLM still does the reasoning; the brief makes that reasoning
consistently practical: outcome first, facts separated from assumptions,
safe verification steps, and a concrete next action.

The same classifier powers the offline simulation fallback, so even without a
live model NEXUS returns a useful structured plan rather than a canned
acknowledgement. It must stay pure domain code: no I/O, no infrastructure.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

_WORD_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_PATH_EXTENSIONS = (
    "py|js|jsx|ts|tsx|json|csv|tsv|md|txt|toml|ya?ml|html|css|scss|sql|sh|"
    "xml|ini|cfg|lock|pdf|docx?|xlsx?|pptx?"
)
_FILE_PATH_RE = re.compile(
    rf"(?<![\w./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:{_PATH_EXTENSIONS}))\b",
    re.IGNORECASE,
)
_KNOWN_DIR_RE = re.compile(
    r"(?<![\w./-])((?:src|tests|docs|web|frontend|projects|scripts|data)(?:/[A-Za-z0-9_.-]+)+)/?(?=$|[\s,.;:)])",
    re.IGNORECASE,
)
_ATTACHED_FILE_RE = re.compile(r"\[Attached file:\s*([^\]\n]+?)(?:\]|\s+\()", re.IGNORECASE)
_FOLLOW_UP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:yes|yeah|ok(?:ay)?|sure)\s*(?:[,.:;-]\s*|\s+))?"
    r"(?:continue|go ahead|do it|yes|yeah|ok(?:ay)?|proceed|"
    r"make it\b.*|change it\b.*|update it\b.*|fix it\b.*|create it\b.*|build it\b.*|"
    r"same but\b.*|now\s+(?:make|change|update|fix|create|build)\s+(?:it|that|this)\b.*|"
    r"(?:shorter|longer|simpler|cheaper|more detailed|less formal|more formal)\b.*)\s*[.!?]*$",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(r"^\s*(?:hi|hello|hey|good (?:morning|afternoon|evening)|namaste)\b[!. ]*$", re.I)

_CURRENT_RE = re.compile(
    r"\b(latest|today|tonight|current|currently|recent|news|price|cost now|weather|"
    r"election|law|legal requirement|regulation|deadline|version|release|stock|"
    r"exchange rate|admission|exam date|job opening|vacancy)\b",
    re.IGNORECASE,
)
_TROUBLESHOOT_RE = re.compile(
    r"\b(not working|won't work|doesn't work|stopped working|not (?:cooling|heating|"
    r"starting|charging|turning on|responding|printing|connecting)|broken|error|"
    r"failed|failure|issue|problem|fix|repair|troubleshoot|stuck|slow|leak|noise|"
    r"won't start|crash|overheating|no (?:power|sound|signal|internet))\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"\b(should i|which (?:one|is better)|choose|choice|compare|comparison|vs\.?|versus|"
    r"buy|purchase|pick|decide|decision|better option)\b",
    re.IGNORECASE,
)
_CODE_RE = re.compile(
    r"\b(code|coding|program|function|bug|debug|api|app|website|software|python|"
    r"javascript|typescript|react|fastapi|database|sql|deploy|test|script)\b",
    re.IGNORECASE,
)
_RESEARCH_RE = re.compile(
    r"\b(research|investigate|evidence|sources?|cite|citation|compare studies|"
    r"market analysis|deep dive|find out)\b",
    re.IGNORECASE,
)
_WRITING_RE = re.compile(
    r"\b(write|draft|rewrite|email|letter|resume|cv|cover letter|essay|message|"
    r"application|proposal|caption|script for|speech)\b",
    re.IGNORECASE,
)
_LEARNING_RE = re.compile(
    r"\b(explain|teach|learn|understand|tutorial|lesson|study|exam|prepare for|"
    r"revision|syllabus|practice)\b",
    re.IGNORECASE,
)
_PLAN_RE = re.compile(
    r"\b(plan|roadmap|steps?|checklist|schedule|routine|strategy|how (?:can|do|to)|"
    r"help me|solve|solution|start|launch|organize|prepare)\b",
    re.IGNORECASE,
)
_REPO_ACTION_RE = re.compile(
    r"\b(create|make|build|generate|scaffold|start|set up|setup|initialise|initialize)\b",
    re.IGNORECASE,
)
_REPO_NOUN_RE = re.compile(r"\b(repo|repository|github project|project scaffold)\b", re.IGNORECASE)
_PROJECT_RE = re.compile(
    r"\b(create|make|build|generate|scaffold|start|set up|setup)\b.{0,48}\b"
    r"(project|codebase|starter|boilerplate)\b",
    re.IGNORECASE | re.DOTALL,
)

_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "medical",
        re.compile(
            r"\b(symptom|fever|pain|medicine|dose|diagnos|disease|infection|pregnan|"
            r"blood pressure|diabetes|doctor|hospital|mental health|depress|anxiety)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "legal",
        re.compile(
            r"\b(legal|court|lawyer|contract|notice|fir|police complaint|visa|immigration|"
            r"tenant|landlord|property dispute|consumer case)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "financial",
        re.compile(
            r"\b(invest|stock|mutual fund|loan|emi|debt|tax|income tax|gst|budget|savings?|"
            r"insurance|credit card|salary|profit|revenue)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "safety",
        re.compile(
            r"\b(electrical|wiring|gas leak|fire|chemical|poison|accident|unsafe|injury|"
            r"bleeding|chest pain|stroke|suicide|self-harm|hurt myself)\b",
            re.IGNORECASE,
        ),
    ),
)

_URGENT_RE = re.compile(
    r"\b(chest pain|can't breathe|cannot breathe|stroke|heavy bleeding|unconscious|"
    r"gas leak|fire|poisoned|suicide|kill myself|self-harm|hurt myself|emergency)\b",
    re.IGNORECASE,
)

_DOMAIN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "business",
        re.compile(
            r"\b(business|startup|shop|store|sell|sales|marketing|customer|client|brand|"
            r"product|service business|franchise|ecommerce|online store|cloud kitchen|"
            r"restaurant|cafe|bakery|salon|agency|coaching|tiffin|food business|"
            r"youtube channel|creator business)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "career",
        re.compile(
            r"\b(job|career|interview|resume|cv|promotion|freelance|client|salary|internship)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "study",
        re.compile(r"\b(exam|study|syllabus|class|college|school|marks|revision|course)\b", re.I),
    ),
    (
        "money",
        re.compile(r"\b(money|budget|save|loan|debt|emi|invest|expense|income|tax)\b", re.I),
    ),
    (
        "health",
        re.compile(r"\b(health|fitness|weight|diet|exercise|sleep|pain|fever|doctor)\b", re.I),
    ),
    (
        "travel",
        re.compile(r"\b(travel|trip|visit|tour|hotel|flight|train|itinerary|vacation)\b", re.I),
    ),
    (
        "home",
        re.compile(
            r"\b(home|house|room|kitchen|plumbing|electric|appliance|fridge|washing machine|ac|fan)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class RepositoryRequest:
    """A normalized local-repository creation request inferred from chat."""

    name: str
    template: str = "python-fastapi"
    description: str = ""

    def tool_params(self) -> dict[str, object]:
        return {
            "name": self.name,
            "template": self.template,
            "description": self.description,
            "initialize_git": True,
            "initial_commit": True,
            "include_ci": True,
        }


@dataclass(frozen=True)
class DeterministicToolCall:
    """A narrow, explicit tool action that can be routed without an LLM guess."""

    tool_id: str
    parameters: tuple[tuple[str, object], ...] = ()
    reason: str = ""

    def params(self) -> dict[str, object]:
        return dict(self.parameters)


@dataclass(frozen=True)
class SolutionBrief:
    """The cortex-facing plan for producing a useful, grounded answer.

    ``intent`` remains the dominant route for backwards-compatible callers,
    while ``workstreams`` preserves every part of a compound, Claude-style
    request such as "research this, inspect the code, fix it, test it, and
    summarize the result". The execution fields turn that classification into
    an auditable operating plan instead of a one-label guess.
    """

    intent: str
    mode: str
    goal: str
    needs_current_info: bool = False
    sensitive_domain: str | None = None
    urgent: bool = False
    suggested_tools: tuple[str, ...] = ()
    missing_context: tuple[str, ...] = ()
    answer_sections: tuple[str, ...] = ()
    repository: RepositoryRequest | None = None
    workstreams: tuple[str, ...] = ()
    operation_level: str = "answer_only"
    readiness: str = "ready"
    constraints: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    referenced_paths: tuple[str, ...] = ()
    execution_phases: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    clarifying_questions: tuple[str, ...] = ()
    context_used: bool = False


def _clean_message(message: str) -> str:
    return _WHITESPACE_RE.sub(" ", (message or "")).strip()


def _goal_text(message: str, limit: int = 220) -> str:
    cleaned = _clean_message(message)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def slugify_project_name(value: str) -> str:
    """Convert free text into a conservative repository folder name."""
    words = _WORD_RE.findall((value or "").lower())
    stopwords = {
        "a",
        "an",
        "the",
        "please",
        "create",
        "make",
        "build",
        "generate",
        "scaffold",
        "start",
        "setup",
        "set",
        "up",
        "repo",
        "repository",
        "project",
        "for",
        "me",
        "my",
        "new",
        "with",
        "using",
        "called",
        "named",
    }
    useful = [word for word in words if word not in stopwords]
    slug = "-".join(useful[:6]).strip("-")[:64].strip("-")
    return slug or "nexus-project"


def _repository_name(message: str) -> str:
    quoted = re.search(r"['\"]([A-Za-z0-9][A-Za-z0-9 _.-]{1,63})['\"]", message)
    if quoted:
        return slugify_project_name(quoted.group(1))

    named = re.search(
        r"\b(?:called|named|name(?:d)?\s+(?:it|as)?)\s+([A-Za-z0-9][A-Za-z0-9_-]{1,63})\b",
        message,
        re.IGNORECASE,
    )
    if named:
        return slugify_project_name(named.group(1))

    # Prefer the subject after "for" ("make a repo for a school fee tracker"),
    # then fall back to the whole request with command verbs removed.
    for_subject = re.search(r"\bfor\s+(?:a|an|the|my)?\s*(.+)$", message, re.IGNORECASE)
    if for_subject:
        candidate = slugify_project_name(for_subject.group(1))
        if candidate != "nexus-project":
            return candidate
    return slugify_project_name(message)


def _repository_template(message: str) -> str:
    lower = message.lower()
    if any(token in lower for token in ("empty", "blank", "just git", "only readme")):
        return "empty"
    if any(
        token in lower
        for token in ("design system", "component library", "ui kit", "clean ui", "frontend design")
    ):
        return "frontend-design-system"
    if re.search(r"c\+\+|cplusplus|\bcpp\b", lower):
        return "cpp-cmake"
    if re.search(
        r"\bC\s*(?:11|17|23)\b|\b(?:ANSI|ISO)\s+C\b|\bC language\b|"
        r"\b(?:in|using|with|written in|program in|code in)\s+C(?:\b|[.,;:])|\.c\b",
        message,
    ):
        return "c-cmake"
    if any(token in lower for token in ("rust", "cargo")):
        return "rust-cli"
    if any(token in lower for token in ("php", "composer", "laravel", "symfony")):
        return "php-web"
    if any(token in lower for token in ("ruby", "rails", "gemfile", "rspec", "minitest")):
        return "ruby-cli"
    if re.search(r"\bxml\b|\bxsd\b|\bxslt?\b", lower):
        return "xml-toolkit"
    if any(
        token in lower
        for token in ("html5", "html site", "html page", "landing page", "static site", "semantic html")
    ):
        return "html5-clean-ui"
    if any(token in lower for token in ("react", "vite", "frontend", "web app", "dashboard ui")):
        return "react-vite"
    if any(token in lower for token in ("static", "portfolio")):
        return "static-site"
    if any(token in lower for token in ("node", "express", "javascript api", "node api")):
        return "node-api"
    if any(token in lower for token in ("cli", "command line", "python package", "automation script")):
        return "python-cli"
    return "python-fastapi"


def detect_repository_request(message: str) -> RepositoryRequest | None:
    """Return a repository request when the user clearly asks to create one."""
    cleaned = _clean_message(message)
    if not cleaned:
        return None
    is_repo = bool(_REPO_NOUN_RE.search(cleaned) and _REPO_ACTION_RE.search(cleaned))
    if not is_repo and not _PROJECT_RE.search(cleaned):
        return None
    return RepositoryRequest(
        name=_repository_name(cleaned),
        template=_repository_template(cleaned),
        description=_goal_text(cleaned, limit=280),
    )


def _sensitive_domain(message: str) -> str | None:
    for domain, pattern in _SENSITIVE_PATTERNS:
        if pattern.search(message):
            return domain
    return None


def _life_domain(message: str) -> str | None:
    for domain, pattern in _DOMAIN_PATTERNS:
        if pattern.search(message):
            return domain
    return None


def _analyze_primary_solution_request(message: str) -> SolutionBrief:
    """Classify the dominant route before multi-workstream enrichment."""
    cleaned = _clean_message(message)
    goal = _goal_text(cleaned) or "Help the user"
    lower = cleaned.lower()
    repository = detect_repository_request(cleaned)
    sensitive = _sensitive_domain(cleaned)
    urgent = bool(_URGENT_RE.search(cleaned))
    needs_current = bool(_CURRENT_RE.search(cleaned))
    life_domain = _life_domain(cleaned)

    if urgent or sensitive == "safety" and any(
        token in lower for token in ("chest pain", "bleeding", "gas leak", "fire", "poison")
    ):
        return SolutionBrief(
            intent="urgent_safety",
            mode="safety_first",
            goal=goal,
            needs_current_info=needs_current,
            sensitive_domain=sensitive or "safety",
            urgent=True,
            missing_context=("exact location and whether anyone is in immediate danger",),
            answer_sections=("Do this now", "Avoid", "Get professional/emergency help"),
        )

    if repository is not None:
        return SolutionBrief(
            intent="create_repository",
            mode="build_and_verify",
            goal=goal,
            needs_current_info=needs_current,
            sensitive_domain=sensitive,
            suggested_tools=("create_repository", "git_info", "pytest_runner"),
            missing_context=(
                "repository purpose and must-have features",
                "preferred stack (a sensible template default is acceptable)",
            ),
            answer_sections=(
                "Created",
                "Project structure",
                "Run and test commands",
                "Next build steps",
                "GitHub push steps",
            ),
            repository=repository,
        )

    if _TROUBLESHOOT_RE.search(cleaned):
        tools = (
            ("list_directory", "grep", "read_file", "pytest_runner")
            if _CODE_RE.search(cleaned)
            else ("web_search", "web_fetch")
        )
        return SolutionBrief(
            intent="troubleshooting",
            mode="diagnose_then_fix",
            goal=goal,
            needs_current_info=needs_current,
            sensitive_domain=sensitive,
            suggested_tools=tools,
            missing_context=(
                "exact symptom or error text",
                "what changed just before it started",
                "device/model/version or setup details",
            ),
            answer_sections=(
                "Most likely causes",
                "Safest checks first",
                "Fix steps",
                "If that does not work",
                "When to stop and get expert help",
            ),
        )

    if _CODE_RE.search(cleaned) and _PLAN_RE.search(cleaned):
        return SolutionBrief(
            intent="build_software",
            mode="build_and_verify",
            goal=goal,
            needs_current_info=needs_current,
            sensitive_domain=sensitive,
            suggested_tools=(
                "list_directory",
                "code_search_semantic",
                "read_file",
                "edit_file",
                "pytest_runner",
            ),
            missing_context=("desired user outcome", "stack or existing project constraints"),
            answer_sections=("Plan", "Implementation", "Verification", "Files changed"),
        )

    if _DECISION_RE.search(cleaned):
        return SolutionBrief(
            intent="decision",
            mode="compare_and_recommend",
            goal=goal,
            needs_current_info=needs_current,
            sensitive_domain=sensitive,
            suggested_tools=("web_search", "web_fetch", "calculator") if needs_current else (),
            missing_context=("budget", "deadline", "the one outcome that matters most"),
            answer_sections=(
                "Recommendation",
                "Options compared",
                "Trade-offs",
                "Choose differently if",
                "Next action",
            ),
        )

    if _RESEARCH_RE.search(cleaned) or needs_current:
        return SolutionBrief(
            intent="research",
            mode="evidence_first",
            goal=goal,
            needs_current_info=True,
            sensitive_domain=sensitive,
            suggested_tools=("web_search", "web_fetch"),
            missing_context=("location/jurisdiction if local rules or prices matter", "date range"),
            answer_sections=("Answer", "Evidence", "Uncertainty", "Sources", "Practical takeaway"),
        )

    if _WRITING_RE.search(cleaned):
        return SolutionBrief(
            intent="writing",
            mode="produce_deliverable",
            goal=goal,
            sensitive_domain=sensitive,
            missing_context=("audience", "tone", "length or deadline"),
            answer_sections=("Ready-to-use draft", "Shorter/politer variant if useful"),
        )

    if _LEARNING_RE.search(cleaned):
        return SolutionBrief(
            intent="learning",
            mode="teach_and_practice",
            goal=goal,
            sensitive_domain=sensitive,
            missing_context=("current level", "exam/deadline if any"),
            answer_sections=("Simple explanation", "Example", "Practice", "Check yourself"),
        )

    if life_domain or _PLAN_RE.search(cleaned):
        missing = ["budget", "deadline", "location if local options matter"]
        if life_domain == "study":
            missing = ["exam date", "current level", "hours available per day"]
        elif life_domain == "business":
            missing = ["target customer", "starting budget", "city/online market"]
        elif life_domain == "travel":
            missing = ["travel dates", "budget", "starting city"]
        return SolutionBrief(
            intent=f"real_world_{life_domain or 'problem'}",
            mode="practical_plan",
            goal=goal,
            needs_current_info=needs_current,
            sensitive_domain=sensitive,
            suggested_tools=("web_search", "web_fetch", "calculator") if needs_current else (),
            missing_context=tuple(missing),
            answer_sections=(
                "Best first move",
                "Step-by-step plan",
                "Checklist",
                "Costs/time and risks",
                "If blocked",
            ),
        )

    return SolutionBrief(
        intent="direct_answer",
        mode="direct",
        goal=goal,
        needs_current_info=needs_current,
        sensitive_domain=sensitive,
        answer_sections=("Answer", "Useful next step if relevant"),
    )


def _dedupe(values: Sequence[str], *, limit: int | None = None) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean_message(str(value))
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if limit is not None and len(result) >= limit:
            break
    return tuple(result)


def _normalize_history(
    history: Sequence[str] | str | None,
    *,
    current: str = "",
) -> tuple[str, ...]:
    """Keep only recent human turns that are safe to use as request context."""

    if history is None:
        return ()
    raw_values: Sequence[str] = (history,) if isinstance(history, str) else history
    current_key = _clean_message(current).lower()
    cleaned: list[str] = []
    for value in raw_values:
        text = _clean_message(str(value))
        if not text:
            continue
        lowered = text.lower()
        if lowered == current_key:
            continue
        if "[observation" in lowered or "<tool_output" in lowered:
            continue
        cleaned.append(text)
    return tuple(cleaned[-6:])


def _is_follow_up(message: str) -> bool:
    return bool(_FOLLOW_UP_RE.match(_clean_message(message)))


def _extract_referenced_paths(message: str) -> tuple[str, ...]:
    """Extract likely workspace paths without treating URLs as local files."""

    without_urls = _URL_RE.sub(" ", message or "")
    candidates: list[str] = []

    for match in _ATTACHED_FILE_RE.finditer(without_urls):
        candidates.append(match.group(1))
    for match in _FILE_PATH_RE.finditer(without_urls):
        candidates.append(match.group(1))
    for match in _KNOWN_DIR_RE.finditer(without_urls):
        candidates.append(match.group(1))
    for match in re.finditer(
        r"['`\"]([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)['`\"]",
        without_urls,
    ):
        candidates.append(match.group(1))

    normalized: list[str] = []
    for candidate in candidates:
        path = candidate.strip().strip("`'\".,:;)").replace("\\", "/")
        if path.startswith("./"):
            path = path[2:]
        path = path.rstrip("/")
        if not path or "://" in path or path.lower().startswith(("http:", "https:")):
            continue
        normalized.append(path)
    return _dedupe(normalized, limit=8)


def _constraint_suffix(inherited: bool) -> str:
    return " (earlier context)" if inherited else ""


def _extract_constraints_for_text(text: str, *, inherited: bool = False) -> tuple[str, ...]:
    """Extract user-stated constraints in a compact, model-readable form."""

    cleaned = _clean_message(text)
    suffix = _constraint_suffix(inherited)
    constraints: list[str] = []

    money_patterns = (
        r"(?:₹|Rs\.?|INR|\$|€|£)\s?\d[\d,]*(?:\.\d+)?\s?(?:k|thousand|lakh|crore|million)?",
        r"\b\d[\d,]*(?:\.\d+)?\s?(?:rupees|dollars|euros|pounds)\b",
    )
    for pattern in money_patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            constraints.append(f"budget/amount: {match.group(0)}{suffix}")

    deadline_patterns = (
        r"\b(?:by|before|until|due(?:\s+on)?|deadline(?:\s+is)?)\s+"
        r"(?:today|tomorrow|tonight|next week|this weekend|end of (?:the )?(?:day|week|month)|"
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?)\b",
        r"\b(?:today|tomorrow|tonight|asap|urgently)\b",
    )
    deadline_values: list[str] = []
    for pattern in deadline_patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            value = match.group(0)
            if any(
                value.lower() in existing.lower() or existing.lower() in value.lower()
                for existing in deadline_values
            ):
                continue
            deadline_values.append(value)
            constraints.append(f"deadline/time: {value}{suffix}")

    for match in re.finditer(
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|"
        r"\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+\d{4})?)\b",
        cleaned,
        re.IGNORECASE,
    ):
        if not any(match.group(0).lower() in value.lower() for value in deadline_values):
            constraints.append(f"date: {match.group(0)}{suffix}")

    for match in re.finditer(
        r"\b(\d+(?:\.\d+)?)[-\s]*(days?|weeks?|months?|hours?|minutes?|words?|pages?|people|persons|students|users|items|questions?)\b",
        cleaned,
        re.IGNORECASE,
    ):
        unit = match.group(2).lower().rstrip("s")
        constraints.append(f"quantity/{unit}: {match.group(0)}{suffix}")

    known_locations = (
        "Patna",
        "Bihar",
        "Delhi",
        "New Delhi",
        "India",
        "Mumbai",
        "Kolkata",
        "Chennai",
        "Bengaluru",
        "Bangalore",
        "Hyderabad",
        "Pune",
        "Ahmedabad",
        "Jaipur",
        "Lucknow",
        "United States",
        "United Kingdom",
        "Dubai",
        "Singapore",
    )
    for location in known_locations:
        if re.search(rf"\b{re.escape(location)}\b", cleaned, re.IGNORECASE):
            constraints.append(f"location: {location}{suffix}")
    route = re.search(
        r"\bfrom\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        cleaned,
    )
    if route:
        constraints.append(f"route: {route.group(1)} to {route.group(2)}{suffix}")

    format_patterns: tuple[tuple[str, str], ...] = (
        (r"\btable\b", "table"),
        (r"\bchecklist\b", "checklist"),
        (r"\bbullet(?:\s+points?)?\b", "bullet points"),
        (r"\bstep[-\s]by[-\s]step\b", "step-by-step"),
        (r"\b(?:short|brief|concise)\b", "short/brief"),
        (r"\b(?:detailed|in detail|deep dive)\b", "detailed"),
        (r"\bone paragraph\b", "one paragraph"),
        (r"\bcode only\b", "code only"),
        (r"\b(?:in\s+)?hindi\b", "Hindi"),
        (r"\bhinglish\b", "Hinglish"),
        (r"\bsimple english\b", "simple English"),
    )
    for pattern, label in format_patterns:
        if re.search(pattern, cleaned, re.IGNORECASE):
            constraints.append(f"output format: {label}{suffix}")

    audience = re.search(
        r"\bfor\s+(beginners?|students?|children|kids|developers?|managers?|clients?|customers?|my team|interviewers?|non-technical users?)\b",
        cleaned,
        re.IGNORECASE,
    )
    if audience:
        constraints.append(f"audience: {audience.group(1)}{suffix}")

    stack_names = (
        "Python",
        "FastAPI",
        "React",
        "Vite",
        "TypeScript",
        "JavaScript",
        "Node.js",
        "Node",
        "Express",
        "SQL",
        "SQLite",
        "PostgreSQL",
        "Docker",
        "HTML5",
        "CSS",
        "Rust",
        "PHP",
        "Ruby",
        "XML",
        "Cargo",
        "CMake",
        "Laravel",
        "Rails",
    )
    for name in stack_names:
        if re.search(rf"\b{re.escape(name)}\b", cleaned, re.IGNORECASE):
            constraints.append(f"technology: {name}{suffix}")
    if re.search(r"c\+\+|cplusplus|\bcpp\b", cleaned, re.IGNORECASE):
        constraints.append(f"technology: C++{suffix}")
    if re.search(
        r"\bC\s*(?:11|17|23)\b|\b(?:ANSI|ISO)\s+C\b|\bC language\b|"
        r"\b(?:in|using|with|written in|program in|code in)\s+C(?:\b|[.,;:])",
        cleaned,
    ):
        constraints.append(f"technology: C{suffix}")
    if not any(item == f"technology: HTML5{suffix}" for item in constraints) and re.search(
        r"\bhtml\b", cleaned, re.IGNORECASE
    ):
        constraints.append(f"technology: HTML5{suffix}")

    for label, pattern in (
        ("formal", r"\bformal\b"),
        ("polite", r"\bpolite\b"),
        ("friendly", r"\bfriendly\b"),
        ("professional", r"\bprofessional\b"),
        ("simple/no jargon", r"\b(?:no jargon|simple language|easy language)\b"),
    ):
        if re.search(pattern, cleaned, re.IGNORECASE):
            constraints.append(f"tone: {label}{suffix}")

    if re.search(r"\b(?:offline|local only|private|confidential|do not share|don't share)\b", cleaned, re.I):
        constraints.append(f"privacy/scope: keep the work local/private as requested{suffix}")

    for match in re.finditer(
        r"\b(?:must not|must|do not|don't|avoid|without|only|keep|never)\b[^.;\n]{0,72}",
        cleaned,
        re.IGNORECASE,
    ):
        value = _clean_message(match.group(0)).rstrip(",")
        if len(value.split()) >= 2:
            constraints.append(f"explicit constraint: {value}{suffix}")

    return _dedupe(constraints, limit=12)


def _constraint_key(value: str) -> str:
    return value.split(":", 1)[0].strip().lower()


def _merge_constraints(
    current: str,
    history: Sequence[str],
) -> tuple[tuple[str, ...], bool]:
    merged = list(_extract_constraints_for_text(current))
    present_keys = {
        _constraint_key(value) for value in merged if not value.startswith("explicit constraint:")
    }
    present_values = {value.lower() for value in merged}
    context_used = False

    for previous in reversed(history):
        for constraint in _extract_constraints_for_text(previous, inherited=True):
            key = _constraint_key(constraint)
            normalized = constraint.replace(" (earlier context)", "").lower()
            if key in present_keys or normalized in present_values:
                continue
            merged.append(constraint)
            present_values.add(normalized)
            if not constraint.startswith("explicit constraint:"):
                present_keys.add(key)
            context_used = True
            if len(merged) >= 12:
                return tuple(merged), context_used
    return tuple(merged), context_used


_WORKSTREAM_ORDER: tuple[str, ...] = (
    "immediate_safety",
    "workspace_inspection",
    "git_inspection",
    "current_research",
    "data_analysis",
    "diagnosis_and_fix",
    "decision_and_tradeoffs",
    "calculation",
    "repository_creation",
    "code_change",
    "file_change",
    "verification",
    "writing_deliverable",
    "learning",
    "practical_planning",
    "direct_answer",
)


def _ordered_workstreams(values: set[str]) -> tuple[str, ...]:
    return tuple(name for name in _WORKSTREAM_ORDER if name in values)


def _detect_workstreams(
    message: str,
    base: SolutionBrief,
    paths: Sequence[str],
) -> tuple[str, ...]:
    cleaned = _clean_message(message)
    lower = cleaned.lower()
    found: set[str] = set()
    has_file_path = any(re.search(rf"\.(?:{_PATH_EXTENSIONS})$", path, re.I) for path in paths)
    has_data_path = any(path.lower().endswith((".csv", ".tsv", ".json")) for path in paths)

    if base.urgent or base.intent == "urgent_safety":
        found.add("immediate_safety")
    if base.repository is not None or base.intent == "create_repository":
        found.add("repository_creation")
    if _RESEARCH_RE.search(cleaned) or (
        base.needs_current_info
        and re.search(
            r"\b(latest|current|today|news|weather|price|law|regulation|release|version|stock|exchange rate)\b",
            cleaned,
            re.I,
        )
    ):
        found.add("current_research")
    if (
        re.search(
            r"\b(list|show|explore|inspect|review|audit|look at|read|open|explain|search|grep|find)\b",
            cleaned,
            re.I,
        )
        and (
            bool(paths)
            or re.search(r"\b(code|codebase|repo|repository|project|files?|directory|folder|workspace)\b", cleaned, re.I)
        )
    ) or re.search(r"\bwhat files?\b", cleaned, re.I):
        found.add("workspace_inspection")
    if re.search(r"\b(git (?:status|branch|log|diff|history)|current branch|recent commits?)\b", cleaned, re.I):
        found.add("git_inspection")
    if has_data_path or re.search(
        r"\b(analy[sz]e|summarize|compare|clean|query|aggregate|chart|graph)\b.{0,48}"
        r"\b(data|dataset|csv|spreadsheet|expenses?|sales|metrics?|json)\b|"
        r"\b(csv|dataset|spreadsheet)\b",
        cleaned,
        re.I | re.DOTALL,
    ):
        found.add("data_analysis")
    if _TROUBLESHOOT_RE.search(cleaned) or base.intent == "troubleshooting":
        found.add("diagnosis_and_fix")
    if _DECISION_RE.search(cleaned) or base.intent == "decision":
        found.add("decision_and_tradeoffs")
    if re.search(r"\b(calculate|compute|evaluate|how much is|what is)\b", cleaned, re.I) and re.search(
        r"\d\s*(?:\+|-|\*|/|%|\*\*|\^|to the power of)", cleaned, re.I
    ):
        found.add("calculation")
    if re.search(r"\b(implement|fix|refactor|build|develop|add|create|update|change)\b", cleaned, re.I) and (
        _CODE_RE.search(cleaned)
        or has_file_path
        or re.search(r"\b(feature|bug|backend|frontend|endpoint|auth|login|component)\b", cleaned, re.I)
    ):
        found.add("code_change")
    if re.search(r"\b(create|write|edit|update|delete|remove|move|rename|make)\b", cleaned, re.I) and (
        has_file_path
        or re.search(r"\b(file|folder|directory|readme|docs?|documentation)\b", cleaned, re.I)
    ):
        found.add("file_change")
    if re.search(
        r"\b(run (?:all |the |its |unit |integration |eval )?tests?|pytest|npm test|test it|verify (?:it|the (?:fix|change|build))|lint|typecheck)\b",
        cleaned,
        re.I,
    ) and (_CODE_RE.search(cleaned) or paths or "repository_creation" in found or "code_change" in found):
        found.add("verification")
    if (
        _WRITING_RE.search(cleaned)
        or base.intent == "writing"
        or re.search(r"\b(summarize|summary|write[-\s]?up|prepare (?:a )?report|document the results?)\b", cleaned, re.I)
    ):
        found.add("writing_deliverable")
    if _LEARNING_RE.search(cleaned) or base.intent == "learning":
        found.add("learning")
    if base.intent.startswith("real_world_") or _life_domain(cleaned) or re.search(
        r"\b(plan|roadmap|checklist|schedule|routine|strategy|itinerary)\b", cleaned, re.I
    ):
        found.add("practical_planning")

    intent_defaults = {
        "research": "current_research",
        "build_software": "code_change",
        "troubleshooting": "diagnosis_and_fix",
        "decision": "decision_and_tradeoffs",
        "direct_answer": "direct_answer",
    }
    if base.intent in intent_defaults:
        found.add(intent_defaults[base.intent])
    if not found:
        found.add("direct_answer")
    if "direct_answer" in found and len(found) > 1:
        found.remove("direct_answer")
    if "practical_planning" in found and (
        {"diagnosis_and_fix", "code_change", "repository_creation"} & found
    ):
        found.remove("practical_planning")
    if {"repository_creation", "code_change"} <= found and not re.search(
        r"\b(implement|fix|refactor|develop|add (?:a |an |the )?feature|build (?:a |an |the )?(?:app|website|api|feature))\b",
        cleaned,
        re.I,
    ):
        found.remove("code_change")
    _ = lower  # Kept explicit for future keyword refinements without API churn.
    return _ordered_workstreams(found)


def _suggested_tools_for_request(
    message: str,
    base: SolutionBrief,
    workstreams: Sequence[str],
    paths: Sequence[str],
) -> tuple[str, ...]:
    cleaned = _clean_message(message)
    lower = cleaned.lower()
    tools: list[str] = []

    def add(tool: str) -> None:
        if tool not in tools:
            tools.append(tool)

    workstream_set = set(workstreams)
    has_file = any(re.search(rf"\.(?:{_PATH_EXTENSIONS})$", path, re.I) for path in paths)
    if "workspace_inspection" in workstream_set:
        add("project_scan")
        if re.search(r"\b(tree|structure|layout|folder|directory)\b", cleaned, re.I):
            add("directory_tree")
        if has_file:
            add("read_files")
            add("read_file")
            add("file_outline")
        if not has_file or re.search(r"\b(list|explore|directory|folder|files)\b", cleaned, re.I):
            add("find_files")
            add("list_directory")
        if re.search(r"\b(search|grep|find|where|defined|used)\b", cleaned, re.I):
            add("find_symbol")
            add("grep")
        if re.search(r"\b(architecture|how does|flow|implemented|responsible)\b", cleaned, re.I):
            add("code_search_semantic")
    if "git_inspection" in workstream_set:
        if re.search(r"\b(diff|changed?|changes|uncommitted|staged)\b", cleaned, re.I):
            add("git_diff")
        add("git_info")
    if "current_research" in workstream_set:
        add("web_search")
        add("web_fetch")
    if "data_analysis" in workstream_set:
        if has_file:
            add("read_file")
        if any(path.lower().endswith(".csv") for path in paths) or "csv" in lower:
            add("csv_query")
        if any(path.lower().endswith(".json") for path in paths) or "json" in lower:
            add("json_query")
        add("calculator")
    if "diagnosis_and_fix" in workstream_set and (_CODE_RE.search(cleaned) or paths):
        add("project_scan")
        add("code_diagnostics")
        add("find_symbol")
        add("grep")
        add("read_files")
        add("read_file")
    if "calculation" in workstream_set:
        add("calculator")
    if "repository_creation" in workstream_set:
        add("create_repository")
        add("project_scan")
        add("git_info")
    if "code_change" in workstream_set:
        add("project_scan")
        add("find_files")
        add("read_files")
        add("read_file")
        add("file_outline")
        if re.search(r"\b(create|add|new|build|implement)\b", cleaned, re.I):
            add("write_files")
            add("write_file")
        add("batch_edit_files")
        add("edit_file")
        add("code_diagnostics")
        add("project_checks")
    if "file_change" in workstream_set:
        mentions_folder = bool(re.search(r"\b(folder|directory|directories)\b", cleaned, re.I))
        if re.search(r"\b(move|rename|relocate)\b", cleaned, re.I):
            add("move_path")
        if re.search(r"\b(copy|duplicate|clone)\b", cleaned, re.I):
            add("copy_path")
        if re.search(r"\b(delete|remove)\b", cleaned, re.I):
            add("delete_directory" if mentions_folder else "delete_file")
        if mentions_folder and re.search(r"\b(create|make|add)\b", cleaned, re.I):
            add("create_directory")
        if re.search(r"\b(create|write|add)\b", cleaned, re.I):
            add("write_files")
            add("write_file")
        if re.search(r"\b(edit|update|change|modify)\b", cleaned, re.I):
            add("batch_edit_files")
            add("edit_file")
    if "verification" in workstream_set or "repository_creation" in workstream_set:
        add("project_checks")
        add("pytest_runner")
        add("code_diagnostics")

    for tool in base.suggested_tools:
        add(tool)
    return tuple(tools[:14])


def _detect_deliverables(message: str, workstreams: Sequence[str]) -> tuple[str, ...]:
    patterns: tuple[tuple[str, str], ...] = (
        (r"\brepositor(?:y|ies)\b|\brepo\b", "local Git-ready repository"),
        (r"\bsummar(?:y|ize|ise)\b", "summary"),
        (r"\breport\b", "report"),
        (r"\btable\b", "comparison/table output"),
        (r"\bchecklist\b", "checklist"),
        (r"\bcomparison|compare\b", "comparison"),
        (r"\brecommendation\b", "recommendation"),
        (r"\bitinerary\b", "itinerary"),
        (r"\bbudget\b", "budget plan"),
        (r"\bstudy plan\b", "study plan"),
        (r"\broadmap\b", "roadmap"),
        (r"\bemail\b", "ready-to-send email"),
        (r"\bcover letter\b", "cover letter"),
        (r"\b(?:resume|cv)\b", "resume/CV"),
        (r"\bessay\b", "essay"),
        (r"\bpresentation\b", "presentation outline"),
        (r"\btest results?\b", "test results"),
    )
    positioned: list[tuple[int, str]] = []
    for pattern, label in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            positioned.append((match.start(), label))
    deliverables = [label for _, label in sorted(positioned)]

    defaults = {
        "code_change": "working code change",
        "file_change": "updated file(s)",
        "data_analysis": "analysis with traceable key numbers",
        "writing_deliverable": "ready-to-use draft",
        "learning": "explanation with example and practice",
        "decision_and_tradeoffs": "recommendation",
        "practical_planning": "step-by-step practical plan",
        "diagnosis_and_fix": "verified fix or diagnosis",
    }
    for workstream in workstreams:
        default_label = defaults.get(workstream)
        if default_label and default_label not in deliverables:
            deliverables.append(default_label)
    return _dedupe(deliverables, limit=5)


_PHASE_TEXT: dict[str, str] = {
    "immediate_safety": "Stabilize the immediate safety risk and direct the user to urgent local help before any detailed answer.",
    "workspace_inspection": "Inspect the relevant workspace files before making claims about their contents or structure.",
    "git_inspection": "Check the actual Git branch/status/history needed for the request.",
    "current_research": "Gather current evidence from reputable, preferably primary, sources and record dates/links.",
    "data_analysis": "Validate the source data, define the calculation method, and compute only from observed rows/values.",
    "diagnosis_and_fix": "Reproduce or characterize the symptom, isolate the likely cause, then apply the smallest safe fix.",
    "decision_and_tradeoffs": "Compare realistic options against the user's hard constraints and make a clear recommendation.",
    "calculation": "Calculate with a tool or show the arithmetic explicitly so the result can be checked.",
    "repository_creation": "Create the local repository scaffold with the approved repository tool; do not simulate file creation in prose.",
    "code_change": "Implement the smallest complete code change that satisfies the requested behaviour.",
    "file_change": "Make only the requested file or directory change through the approved file tools.",
    "verification": "Run targeted verification first, broaden it when shared behaviour changed, and report the actual result.",
    "writing_deliverable": "Produce the requested draft using only supplied facts or clearly marked placeholders.",
    "learning": "Explain from the user's level, give an example, then include a small practice/check step.",
    "practical_planning": "Turn the goal into ordered actions with first step, constraints, risks, and a fallback.",
    "direct_answer": "Answer directly and proportionately; do not add an unnecessary project plan to a simple question.",
}

_ACCEPTANCE_TEXT: dict[str, str] = {
    "immediate_safety": "Immediate danger, emergency contact, and what to avoid are addressed first.",
    "workspace_inspection": "Every file/content claim is grounded in an inspected path or tool observation.",
    "git_inspection": "Branch/status claims come from actual Git output.",
    "current_research": "Volatile claims cite dated sources and distinguish confirmed facts from estimates.",
    "data_analysis": "Totals and conclusions are traceable to the source data; gaps and assumptions are named.",
    "diagnosis_and_fix": "The original symptom or failing case is retested after the fix.",
    "decision_and_tradeoffs": "The recommendation respects hard constraints and says when another option would be better.",
    "calculation": "The final number matches the shown/calculated arithmetic and units.",
    "repository_creation": "The actual repository path, scaffold files, Git state, and starter-test result are reported.",
    "code_change": "Changed files are listed and targeted tests pass, or the exact failing test/output is disclosed.",
    "file_change": "Only the intended path changed and the resulting path/operation is reported from tool evidence.",
    "verification": "The verification command/tool and its real pass/fail outcome are included.",
    "writing_deliverable": "The draft is ready to use, matches audience/tone/length, and invents no personal facts.",
    "learning": "The user receives an understandable example and a way to check their own understanding.",
    "practical_planning": "The plan has a concrete first action, sequence, constraints, and fallback.",
    "direct_answer": "The answer addresses the exact question without unsupported claims.",
}


def _derive_readiness(
    message: str,
    base: SolutionBrief,
    workstreams: Sequence[str],
    paths: Sequence[str],
    *,
    has_history: bool,
) -> tuple[str, tuple[str, ...]]:
    cleaned = _clean_message(message)
    if base.urgent or base.intent == "urgent_safety":
        return "safety_first", ()
    if not cleaned:
        return "clarify_first", ("What would you like help with?",)
    if _GREETING_RE.match(cleaned):
        return "ready", ()

    destructive = re.search(
        r"\b(delete|remove|erase|wipe|drop|deploy|publish|send|pay|transfer)\b",
        cleaned,
        re.I,
    )
    if destructive:
        vague_target = re.search(
            r"\b(?:delete|remove|erase|wipe|drop|deploy|publish|send|pay|transfer)\s+(?:it|this|that|the file|a file|file)?\s*$",
            cleaned,
            re.I,
        )
        if vague_target and not paths and not has_history:
            return (
                "clarify_first",
                (
                    "Which exact target should this act on?",
                    "Should anything be backed up or kept before proceeding?",
                ),
            )
        return "confirmation_required", ()

    if _is_follow_up(cleaned):
        if has_history:
            return "ready_with_context", ()
        return (
            "clarify_first",
            (
                "What should I continue or change?",
                "What result do you want at the end?",
            ),
        )

    words = _WORD_RE.findall(cleaned.lower())
    generic_build = re.search(
        r"^\s*(?:please\s+)?(?:build|make|create|develop)\s+(?:an?\s+)?(?:app|website|tool|something)\s*[.!?]*$",
        cleaned,
        re.I,
    )
    generic_write = re.search(
        r"^\s*(?:please\s+)?(?:write|draft)\s+(?:something|it|this)\s*[.!?]*$",
        cleaned,
        re.I,
    )
    generic_help = len(words) <= 3 and bool(
        re.search(r"^\s*(?:help(?: me)?|which is best|best option|fix it|improve this)\s*[.!?]*$", cleaned, re.I)
    )
    if generic_build:
        return (
            "clarify_first",
            (
                "What should the app/tool help its users do?",
                "Which platform or technology should it use?",
                "What are the must-have features for the first version?",
            ),
        )
    if generic_write:
        return (
            "clarify_first",
            (
                "What should the text be about?",
                "Who is the audience?",
                "What tone and approximate length do you want?",
            ),
        )
    if generic_help:
        return (
            "clarify_first",
            (
                "What topic or task should I help with?",
                "What outcome do you want?",
                "Are there any budget, deadline, or format constraints?",
            ),
        )

    if base.sensitive_domain in {"medical", "legal", "financial", "safety"}:
        return "proceed_with_caution", ()
    if base.missing_context and base.intent in {
        "create_repository",
        "build_software",
        "decision",
        "writing",
        "learning",
    } or base.intent.startswith("real_world_"):
        return "proceed_with_assumptions", ()
    _ = workstreams
    return "ready", ()


def _operation_level(workstreams: Sequence[str]) -> str:
    items = set(workstreams)
    mutation = bool(items & {"repository_creation", "code_change", "file_change"})
    read_only = bool(
        items & {"workspace_inspection", "git_inspection", "data_analysis", "verification", "calculation"}
    )
    external = "current_research" in items
    if mutation and (read_only or external):
        return "mixed_workspace_and_research"
    if mutation:
        return "workspace_mutation"
    if read_only and external:
        return "read_only_and_external_research"
    if read_only:
        return "workspace_read_only_or_calculation"
    if external:
        return "external_research"
    return "answer_only"


def _enrich_solution_brief(
    base: SolutionBrief,
    message: str,
    history: Sequence[str],
) -> SolutionBrief:
    cleaned = _clean_message(message)
    normalized_history = _normalize_history(history, current=cleaned)
    paths = list(_extract_referenced_paths(cleaned))
    follow_up = _is_follow_up(cleaned)
    inherited_path = False
    if follow_up and normalized_history:
        for path in _extract_referenced_paths(normalized_history[-1]):
            if path not in paths:
                paths.append(path)
                inherited_path = True

    workstreams = set(_detect_workstreams(cleaned, base, tuple(paths)))
    if follow_up and normalized_history:
        previous = normalized_history[-1]
        previous_base = _analyze_primary_solution_request(previous)
        previous_paths = _extract_referenced_paths(previous)
        workstreams.update(_detect_workstreams(previous, previous_base, previous_paths))
    ordered_workstreams = _ordered_workstreams(workstreams)

    constraints, constraints_from_context = _merge_constraints(cleaned, normalized_history)
    suggested_tools = _suggested_tools_for_request(
        cleaned,
        base,
        ordered_workstreams,
        tuple(paths),
    )
    deliverables = _detect_deliverables(cleaned, ordered_workstreams)
    phases = tuple(_PHASE_TEXT[name] for name in ordered_workstreams if name in _PHASE_TEXT)
    acceptance = tuple(
        _ACCEPTANCE_TEXT[name] for name in ordered_workstreams if name in _ACCEPTANCE_TEXT
    )
    readiness, questions = _derive_readiness(
        cleaned,
        base,
        ordered_workstreams,
        tuple(paths),
        has_history=bool(normalized_history),
    )

    satisfied_terms: list[str] = []
    constraint_keys = {_constraint_key(value) for value in constraints}
    if "budget/amount" in constraint_keys:
        satisfied_terms.extend(["budget"])
    if "deadline/time" in constraint_keys or "date" in constraint_keys:
        satisfied_terms.extend(["deadline", "exam date", "travel dates"])
    if "location" in constraint_keys or "route" in constraint_keys:
        satisfied_terms.extend(["location", "city", "starting city"])
    missing_context = tuple(
        item
        for item in base.missing_context
        if not any(term in item.lower() for term in satisfied_terms)
    )

    sections = list(base.answer_sections)
    if len(ordered_workstreams) >= 2:
        for section in ("Work completed", "Verification", "Blockers or next input needed"):
            if section not in sections:
                sections.append(section)

    return replace(
        base,
        needs_current_info=base.needs_current_info or "current_research" in workstreams,
        suggested_tools=suggested_tools,
        missing_context=missing_context,
        answer_sections=tuple(sections),
        workstreams=ordered_workstreams,
        operation_level=_operation_level(ordered_workstreams),
        readiness=readiness,
        constraints=constraints,
        deliverables=deliverables,
        referenced_paths=tuple(paths[:8]),
        execution_phases=phases[:7],
        acceptance_criteria=acceptance[:6],
        clarifying_questions=questions,
        context_used=bool(
            base.context_used
            or constraints_from_context
            or inherited_path
            or (follow_up and normalized_history)
        ),
    )


def analyze_solution_request(
    message: str,
    history: Sequence[str] | str | None = None,
) -> SolutionBrief:
    """Classify a request into a conversation-aware execution brief.

    The original single-intent classifier remains the dominant route, but the
    public result now retains all workstreams, explicit constraints,
    deliverables, readiness, ordered phases, and acceptance criteria. Short
    follow-ups inherit the previous human turn's operating mode instead of
    being misread as a brand-new direct answer.
    """

    cleaned = _clean_message(message)
    normalized_history = _normalize_history(history, current=cleaned)
    base = _analyze_primary_solution_request(cleaned)

    if normalized_history and _is_follow_up(cleaned) and base.intent == "direct_answer":
        prior = _analyze_primary_solution_request(normalized_history[-1])
        if prior.intent != "direct_answer":
            base = replace(
                prior,
                goal=base.goal,
                needs_current_info=base.needs_current_info or prior.needs_current_info,
                sensitive_domain=base.sensitive_domain or prior.sensitive_domain,
                urgent=base.urgent or prior.urgent,
            )

    if normalized_history:
        prior_message = normalized_history[-1]

        # "I want a repository for X" -> "Create it" should become the same
        # repository action, not a generic direct answer.
        if (
            base.repository is None
            and _is_follow_up(cleaned)
            and re.search(r"\b(create|make|build|generate|scaffold|start)\b", cleaned, re.I)
            and _REPO_NOUN_RE.search(prior_message)
        ):
            synthetic = detect_repository_request(f"Create {prior_message}")
            if synthetic is not None:
                repository_base = _analyze_primary_solution_request(
                    f"Create a repository called {synthetic.name}"
                )
                base = replace(
                    repository_base,
                    goal=base.goal,
                    needs_current_info=base.needs_current_info,
                    sensitive_domain=base.sensitive_domain,
                    urgent=base.urgent,
                    repository=synthetic,
                    context_used=True,
                )

        # "Create a repo for that" should inherit the subject, not call the
        # project literally "that".
        if base.repository is not None and base.repository.name in {
            "that",
            "it",
            "this",
            "nexus-project",
        }:
            prior_repository = detect_repository_request(prior_message)
            if prior_repository is not None:
                inherited_name = prior_repository.name
            else:
                subject = re.sub(
                    r"^\s*(?:plan|design|build|create|make|i want|i need)\s+(?:a\s+|an\s+|the\s+)?",
                    "",
                    prior_message,
                    flags=re.IGNORECASE,
                )
                subject = re.sub(
                    r"\b(?:react|python|fastapi|node|static|vite|typescript|javascript)\b",
                    "",
                    subject,
                    flags=re.IGNORECASE,
                )
                inherited_name = slugify_project_name(subject)
            inherited_template = (
                base.repository.template
                if base.repository.template != "python-fastapi"
                else _repository_template(prior_message)
            )
            base = replace(
                base,
                repository=RepositoryRequest(
                    name=inherited_name,
                    template=inherited_template,
                    description=_goal_text(prior_message, limit=280),
                ),
                context_used=True,
            )

    return _enrich_solution_brief(base, cleaned, normalized_history)


def _is_safe_workspace_path(path: str) -> bool:
    """Only route explicit relative workspace paths; tools still enforce policy."""

    value = (path or "").strip().replace("\\", "/")
    if value == ".":
        return True
    if not value or value.startswith(("/", "~")) or "://" in value:
        return False
    parts = [part for part in value.split("/") if part not in {"", "."}]
    if not parts or ".." in parts:
        return False
    basename = parts[-1].lower()
    if basename.startswith(".env") or basename in {
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        "shadow",
        "passwd",
    }:
        return False
    if basename.endswith((".pem", ".key", ".p12", ".pfx", ".keystore")):
        return False
    return True


def _extract_calculation(message: str) -> str | None:
    cleaned = _clean_message(message).rstrip("?.! ")
    percent = re.search(
        r"\b(?:what is|calculate|compute)?\s*(\d+(?:\.\d+)?)\s*%\s+of\s+(\d[\d,]*(?:\.\d+)?)\b",
        cleaned,
        re.I,
    )
    if percent:
        return f"({percent.group(2).replace(',', '')} * {percent.group(1)} / 100)"

    power = re.search(
        r"\b(\d+(?:\.\d+)?)\s+(?:to the power of|raised to(?: the power of)?)\s+(\d+(?:\.\d+)?)\b",
        cleaned,
        re.I,
    )
    if power:
        return f"{power.group(1)}**{power.group(2)}"

    candidate = None
    explicit = re.search(r"\b(?:calculate|compute|evaluate|solve)\s+(.+)$", cleaned, re.I)
    question = re.search(r"\bwhat is\s+(.+)$", cleaned, re.I)
    if explicit:
        candidate = explicit.group(1)
    elif question and re.search(r"\d\s*(?:\+|-|\*|/|%|\^|\*\*)", question.group(1)):
        candidate = question.group(1)
    elif re.fullmatch(r"[\d\s+\-*/().,%^]+", cleaned) and re.search(r"[+\-*/]", cleaned):
        candidate = cleaned
    if not candidate:
        return None

    candidate = candidate.strip().rstrip("?.! ")
    candidate = re.sub(r"^(?:the\s+)?(?:value\s+of\s+)?", "", candidate, flags=re.I)
    candidate = candidate.replace(",", "").replace("^", "**")
    candidate = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", "*", candidate, flags=re.I)
    if not re.fullmatch(r"[0-9+\-*/().%\s]+", candidate):
        return None
    if not re.search(r"[+\-*/]", candidate):
        return None
    if candidate.count("(") != candidate.count(")"):
        return None
    return _clean_message(candidate)


def _directory_from_paths(paths: Sequence[str]) -> str | None:
    for path in paths:
        if _is_safe_workspace_path(path) and not re.search(
            rf"\.(?:{_PATH_EXTENSIONS})$", path, re.I
        ):
            return path
    return None


def _file_from_paths(paths: Sequence[str]) -> str | None:
    for path in paths:
        if _is_safe_workspace_path(path) and re.search(
            rf"\.(?:{_PATH_EXTENSIONS})$", path, re.I
        ):
            return path
    return None


def detect_read_only_tool_call(
    message: str,
    history: Sequence[str] | str | None = None,
) -> DeterministicToolCall | None:
    """Detect one explicit, low-risk tool call for deterministic routing.

    This intentionally does *not* infer writes, deletes, code edits, external
    browsing, or compound mutations. Those remain model/ReAct and approval
    decisions. It covers the everyday Claude-style asks that should work even
    in no-key simulation: calculate, inspect a folder/file, search code, check
    Git, run requested tests, hash supplied text, or report date/system info.
    """

    cleaned = _clean_message(message)
    brief = analyze_solution_request(cleaned, history=history)
    if brief.readiness in {"clarify_first", "safety_first"} or brief.urgent:
        return None

    expression = _extract_calculation(cleaned)
    if expression:
        return DeterministicToolCall(
            tool_id="calculator",
            parameters=(("expression", expression),),
            reason="explicit arithmetic request",
        )

    if re.search(r"\b(what(?:'s| is) (?:the )?(?:current )?(?:date|time)|current date and time)\b", cleaned, re.I):
        return DeterministicToolCall(
            tool_id="current_datetime",
            reason="explicit current date/time request",
        )

    if re.search(r"\b(system info|machine info|python version|cpu count|operating system)\b", cleaned, re.I):
        return DeterministicToolCall(
            tool_id="system_info",
            reason="explicit system-information request",
        )

    # Compound mutations should stay with the live ReAct planner. Returning a
    # first read here could make simulation stop after inspection and imply a
    # larger task was completed.
    if brief.operation_level in {"workspace_mutation", "mixed_workspace_and_research"}:
        return None

    paths = brief.referenced_paths
    directory = _directory_from_paths(paths)
    file_path = _file_from_paths(paths)
    safe_files = [
        path
        for path in paths
        if _is_safe_workspace_path(path)
        and re.search(rf"\.(?:{_PATH_EXTENSIONS})$", path, re.I)
    ]

    def explicit_directory(default: str = ".") -> str:
        if directory and _is_safe_workspace_path(directory):
            return directory
        bare = re.search(
            r"\b(?:in|under|inside)\s+(src|tests|docs|web|frontend|projects|scripts|data)\b",
            cleaned,
            re.I,
        )
        if bare:
            return bare.group(1).lower()
        known = re.search(
            r"\b(src|tests|docs|web|frontend|projects|scripts|data)\b(?!\s*/)",
            cleaned,
            re.I,
        )
        return known.group(1).lower() if known else default

    if re.search(
        r"\b(changelog|release notes?|draft (?:a )?changelog|summarize (?:the )?(?:recent )?commits?|commit summary)\b",
        cleaned,
        re.I,
    ):
        parameters: tuple[tuple[str, object], ...] = (
            ("repo_path", directory or "."),
            ("max_commits", 50),
        )
        from_match = re.search(r"\b(?:since|from)\s+`?([A-Za-z0-9._/@{}~^:-]+)`?", cleaned, re.I)
        if from_match:
            candidate = from_match.group(1).strip("`.,)")
            if candidate.lower() not in {"last", "latest", "previous", "recent", "tag", "release", "the"} and (
                any(char.isdigit() or char in "._-/" for char in candidate) or candidate.startswith("HEAD")
            ):
                parameters += (("from_ref", candidate),)
        return DeterministicToolCall(
            tool_id="changelog_draft",
            parameters=parameters,
            reason="explicit changelog or release-notes request",
        )

    if re.search(
        r"\b(release readiness|ready (?:to|for) (?:release|ship|deploy|launch|production)|"
        r"can (?:i|we) (?:ship|release|deploy)|pre[- ]release (?:check|audit|review)|"
        r"release (?:gate|audit)|deploy readiness|production ready)\b",
        cleaned,
        re.I,
    ):
        include_checks = bool(
            re.search(
                r"\b(run|include|with)\b.{0,30}\b(checks?|tests?|pytest|lint|build)\b|\bfull (?:check|audit|release)\b",
                cleaned,
                re.I,
            )
        )
        return DeterministicToolCall(
            tool_id="release_readiness",
            parameters=(
                ("path", explicit_directory(".")),
                ("include_checks", include_checks),
            ),
            reason="explicit release-readiness request",
        )

    if re.search(
        r"\b(secret scan|scan .{0,40}secrets?|find (?:leaked|committed|hardcoded) (?:secrets?|api keys?|credentials?)|"
        r"hardcoded (?:secrets?|api keys?|credentials?)|leaked (?:secrets?|api keys?|credentials?)|credential leak)\b",
        cleaned,
        re.I,
    ):
        return DeterministicToolCall(
            tool_id="secret_scan",
            parameters=(
                ("path", explicit_directory(".")),
                (
                    "include_tests",
                    not bool(re.search(r"\b(exclude|ignore|skip) tests?\b|\bwithout tests?\b", cleaned, re.I)),
                ),
            ),
            reason="explicit secret-scan request",
        )

    if re.search(r"\bproject scan\b", cleaned, re.I) or (
        re.search(r"\b(scan|map|overview|analy[sz]e|audit|understand|summarize)\b", cleaned, re.I)
        and re.search(r"\b(project|repo|repository|codebase|workspace)\b", cleaned, re.I)
    ):
        return DeterministicToolCall(
            tool_id="project_scan",
            parameters=(("path", explicit_directory(".")),),
            reason="explicit whole-project scan request",
        )

    if re.search(
        r"\b(code diagnostics?|syntax (?:check|errors?)|check .{0,24}syntax|"
        r"find (?:syntax errors?|todos?|fixmes?)|scan for (?:syntax|todos?|fixmes?))\b",
        cleaned,
        re.I,
    ):
        target = file_path or explicit_directory(".")
        return DeterministicToolCall(
            tool_id="code_diagnostics",
            parameters=(
                ("path", target),
                ("include_todos", bool(re.search(r"\b(todo|fixme)\b", cleaned, re.I))),
            ),
            reason="explicit code-diagnostics request",
        )

    if re.search(
        r"\b(project checks?|all checks?|run (?:the )?checks?|npm (?:run )?(?:lint|test|build)|"
        r"lint (?:and|&) build|verify (?:the )?project)\b",
        cleaned,
        re.I,
    ):
        checks: list[str] = []
        lower = cleaned.lower()
        if "compile" in lower or "syntax" in lower:
            checks.append("python_compile")
        if "pytest" in lower or "python test" in lower:
            checks.append("pytest")
        if "lint" in lower:
            checks.append("npm_lint")
        if "build" in lower:
            checks.append("npm_build")
        if "npm test" in lower:
            checks.append("npm_test")
        parameters = (("path", explicit_directory(".")),)
        if checks:
            parameters += (("checks", list(dict.fromkeys(checks))),)
        return DeterministicToolCall(
            tool_id="project_checks",
            parameters=parameters,
            reason="explicit project-check request",
        )

    if re.search(
        r"\b(git diff|show (?:me )?(?:the )?(?:diff|changes?)|what changed|uncommitted changes?|staged changes?)\b",
        cleaned,
        re.I,
    ):
        parameters = (
            ("repo_path", directory or "."),
            ("staged", bool(re.search(r"\bstaged\b", cleaned, re.I))),
        )
        if file_path:
            parameters += (("path", file_path),)
        return DeterministicToolCall(
            tool_id="git_diff",
            parameters=parameters,
            reason="explicit Git diff request",
        )

    if re.search(r"\b(git (?:status|branch|log|diff|history)|current branch|recent commits?)\b", cleaned, re.I):
        repo_path = directory or "."
        return DeterministicToolCall(
            tool_id="git_info",
            parameters=(("repo_path", repo_path),),
            reason="explicit Git inspection request",
        )

    if re.search(
        r"\b(run (?:all |the |unit |integration |eval )?tests?|pytest|test suite)\b",
        cleaned,
        re.I,
    ):
        if file_path and file_path.endswith(".py"):
            target = file_path
        elif directory and directory.startswith("tests"):
            target = directory
        elif "unit" in cleaned.lower():
            target = "tests/unit"
        elif "eval" in cleaned.lower():
            target = "tests/eval"
        else:
            target = "tests/"
        return DeterministicToolCall(
            tool_id="pytest_runner",
            parameters=(("target", target), ("options", "-q --tb=short")),
            reason="explicit test-run request",
        )

    if re.search(r"\b(directory tree|folder tree|tree view|project tree)\b", cleaned, re.I) or (
        re.search(r"\b(show|print|display)\b", cleaned, re.I)
        and re.search(r"\btree\b", cleaned, re.I)
        and re.search(r"\b(folder|directory|project|workspace)\b", cleaned, re.I)
    ):
        return DeterministicToolCall(
            tool_id="directory_tree",
            parameters=(("path", explicit_directory(".")), ("max_depth", 3)),
            reason="explicit directory-tree request",
        )

    symbol_match = re.search(
        r"\b(?:where is|find (?:the )?(?:definition|definitions|references?|symbol)(?: of)?|"
        r"definition of|references? (?:to|for))\s+`?([A-Za-z_$][A-Za-z0-9_$]*)`?"
        r"(?:\s+is\s+(?:defined|used))?\b",
        cleaned,
        re.I,
    )
    if symbol_match and re.search(r"\b(defined|used|definition|reference|symbol)\b", cleaned, re.I):
        return DeterministicToolCall(
            tool_id="find_symbol",
            parameters=(
                ("symbol", symbol_match.group(1)),
                ("path", explicit_directory("src")),
            ),
            reason="explicit definition/reference lookup request",
        )

    if re.search(r"\bfind\b", cleaned, re.I) and re.search(r"\bfiles?\b", cleaned, re.I):
        glob_match = re.search(r"`?(\*\.[A-Za-z0-9]{1,12})`?", cleaned)
        language_match = re.search(
            r"\b(python|javascript|typescript|tsx|markdown|json|yaml|toml|html|css)\s+files?\b",
            cleaned,
            re.I,
        )
        named_match = re.search(
            r"\bfiles?\s+(?:named|containing|with)\s+`?([A-Za-z0-9_.-]{2,80})`?",
            cleaned,
            re.I,
        )
        language_patterns = {
            "python": "*.py",
            "javascript": "*.js",
            "typescript": "*.ts",
            "tsx": "*.tsx",
            "markdown": "*.md",
            "json": "*.json",
            "yaml": "*.yaml",
            "toml": "*.toml",
            "html": "*.html",
            "css": "*.css",
        }
        pattern = None
        if glob_match:
            pattern = glob_match.group(1)
        elif language_match:
            pattern = language_patterns[language_match.group(1).lower()]
        parameters = (("path", explicit_directory(".")),)
        if pattern:
            parameters += (("pattern", pattern),)
        elif named_match:
            parameters += (("name_contains", named_match.group(1)),)
        else:
            parameters += (("pattern", "*"),)
        return DeterministicToolCall(
            tool_id="find_files",
            parameters=parameters,
            reason="explicit recursive file-discovery request",
        )

    if re.search(r"\b(list|show|explore)\b", cleaned, re.I) and re.search(
        r"\b(files?|folder|directory|workspace|project|repo|repository)\b", cleaned, re.I
    ):
        target_dir = directory
        if target_dir is None:
            bare_dir = re.search(
                r"\b(?:in|under|inside)\s+(src|tests|docs|web|frontend|projects|scripts|data)\b",
                cleaned,
                re.I,
            )
            if bare_dir:
                target_dir = bare_dir.group(1).lower()
        if target_dir is None and re.search(
            r"\b(workspace|project|repo|repository|current directory|root)\b", cleaned, re.I
        ):
            target_dir = "."
        if target_dir and _is_safe_workspace_path(target_dir):
            return DeterministicToolCall(
                tool_id="list_directory",
                parameters=(("path", target_dir),),
                reason="explicit directory listing request",
            )

    if re.search(r"\b(search|grep|find)\b", cleaned, re.I) and re.search(
        r"\b(code|codebase|files?|defined|used|where)\b", cleaned, re.I
    ):
        quoted = re.search(r"['\"`]([^'\"`]{2,80})['\"`]", cleaned)
        plain = re.search(
            r"\b(?:search|grep)(?:\s+for)?\s+([A-Za-z_][A-Za-z0-9_.-]{1,79})\b",
            cleaned,
            re.I,
        )
        defined = re.search(
            r"\bfind\s+where\s+([A-Za-z_][A-Za-z0-9_.-]{1,79})\s+is\s+(?:defined|used)\b",
            cleaned,
            re.I,
        )
        pattern_match = quoted or defined or plain
        pattern = pattern_match.group(1) if pattern_match else None
        if pattern and not _extract_referenced_paths(pattern):
            search_root = directory or ("src" if re.search(r"\b(code|codebase|python)\b", cleaned, re.I) else ".")
            if search_root.startswith("docs"):
                include = "*.md"
            elif search_root.startswith("web"):
                include = "*.tsx"
            else:
                include = "*.py"
            return DeterministicToolCall(
                tool_id="grep",
                parameters=(
                    ("pattern", re.escape(pattern)),
                    ("path", search_root),
                    ("include", include),
                ),
                reason="explicit code-search request",
            )

    hash_match = re.search(
        r"\b(?:sha256|sha-256|md5|hash)\b.{0,24}['\"`]([^'\"`]{1,500})['\"`]",
        cleaned,
        re.I,
    )
    if hash_match:
        algorithm = "md5" if "md5" in cleaned.lower() else "sha256"
        return DeterministicToolCall(
            tool_id="hash_text",
            parameters=(("text", hash_match.group(1)), ("algorithm", algorithm)),
            reason="explicit text-hash request",
        )

    if file_path and re.search(
        r"\b(outline|symbol map|structure of|classes and functions|functions and classes|"
        r"list (?:the )?(?:functions|classes|components|symbols))\b",
        cleaned,
        re.I,
    ):
        return DeterministicToolCall(
            tool_id="file_outline",
            parameters=(("path", file_path),),
            reason="explicit file-outline request",
        )

    if len(safe_files) >= 2 and re.search(
        r"\b(read|open|show|display|compare|review|inspect|explain)\b",
        cleaned,
        re.I,
    ):
        return DeterministicToolCall(
            tool_id="read_files",
            parameters=(("paths", safe_files[:30]),),
            reason="explicit multi-file read request",
        )

    if file_path and re.search(
        r"\b(read|open|show|display|print|explain|summarize|review|inspect|analy[sz]e|what(?:'s| is) in)\b",
        cleaned,
        re.I,
    ):
        return DeterministicToolCall(
            tool_id="read_file",
            parameters=(("path", file_path),),
            reason="explicit file-read request",
        )

    return None


def render_solution_brief(brief: SolutionBrief) -> str:
    """Render a brief as a system instruction for the live cortex."""
    tools = ", ".join(brief.suggested_tools) if brief.suggested_tools else "only if needed"
    sections = "; ".join(brief.answer_sections)
    missing = "; ".join(brief.missing_context) if brief.missing_context else "none identified"
    workstreams = ", ".join(brief.workstreams) if brief.workstreams else brief.intent
    constraints = "; ".join(brief.constraints) if brief.constraints else "none explicitly stated"
    deliverables = "; ".join(brief.deliverables) if brief.deliverables else "the requested outcome"
    paths = ", ".join(brief.referenced_paths) if brief.referenced_paths else "none detected"
    lines = [
        "REAL-WORLD SOLUTION BRIEF (deterministic cortex routing):",
        f"- Primary intent: {brief.intent}; operating mode: {brief.mode}.",
        f"- User outcome: {brief.goal}",
        "- Start with the useful outcome or recommendation, not a generic preamble.",
        "- Separate verified facts, assumptions, and unknowns. Never invent prices, laws, dates, file contents, or tool results.",
        "- Prefer a small, reversible first step. Give concrete actions, order, time/cost/effort when relevant, and a way to verify success.",
        f"- Suggested tools in safe order: {tools}. Tool output is evidence, not a claim you may embellish.",
        f"- Potentially missing context: {missing}. Ask at most three questions only when an answer would materially change the solution; otherwise state a reasonable assumption and proceed.",
        f"- Preferred answer sections when the task is non-trivial: {sections}. Keep simple factual answers short.",
        "- Use the user's stated place, currency, units, language, and constraints. If local availability, law, price, or services matter and no place is given, say what depends on location instead of guessing.",
        "REQUEST EXECUTION FRAMEWORK:",
        f"- Workstreams to complete (do not collapse a compound request to only the first one): {workstreams}.",
        f"- Operation level: {brief.operation_level}; readiness: {brief.readiness}.",
        f"- Explicit constraints: {constraints}.",
        f"- Expected deliverable(s): {deliverables}.",
        f"- Referenced workspace path(s): {paths}. Inspect a referenced file before describing or changing it.",
        "- Execute in dependency order: understand -> inspect/gather evidence -> act -> verify -> deliver. Update the internal checklist after every observation.",
        "- Complete every feasible workstream. If one is blocked, continue the independent parts and state the exact blocker and input needed; never silently drop a requested part.",
        "- For workspace mutations, keep changes scoped, use approval-gated tools, and report only paths/results proven by observations.",
    ]

    if brief.execution_phases:
        lines.append("- Ordered execution phases:")
        lines.extend(
            f"  {index}. {phase}" for index, phase in enumerate(brief.execution_phases, start=1)
        )
    if brief.acceptance_criteria:
        lines.append("- Done means:")
        lines.extend(f"  * {criterion}" for criterion in brief.acceptance_criteria)
    if brief.context_used:
        lines.append(
            "- Conversation context is relevant: resolve pronouns and elliptical follow-ups from earlier human turns. The latest instruction overrides older constraints when they conflict."
        )
    if brief.readiness == "clarify_first":
        questions = "; ".join(brief.clarifying_questions) or "the material missing detail"
        lines.append(
            f"- READINESS GATE: do not execute or guess yet. Ask only these material question(s), then stop: {questions}"
        )
    elif brief.readiness == "confirmation_required":
        lines.append(
            "- READINESS GATE: this is consequential or destructive. Confirm the exact target/scope or use the tool approval flow before acting; identify backup/rollback where relevant."
        )
    elif brief.readiness == "proceed_with_assumptions":
        lines.append(
            "- READINESS: proceed now with sensible, clearly stated assumptions instead of stalling for non-critical details."
        )
    elif brief.readiness == "proceed_with_caution":
        lines.append(
            "- READINESS: proceed carefully, qualify uncertainty, verify high-impact claims, and state when a qualified professional/official source is required."
        )

    if brief.needs_current_info:
        lines.append(
            "- This may depend on current/volatile information: use web_search/web_fetch, prefer primary/official sources, cite source names or URLs, and state the date checked."
        )
    if brief.repository is not None:
        repo = brief.repository
        lines.extend(
            [
                f"- Repository request detected: create a local Git-ready repository named '{repo.name}' with template '{repo.template}'.",
                "- Use create_repository for the scaffold instead of manually writing a long series of starter files. If approval is required, say exactly that and do not claim creation.",
                "- After creation, report the actual path/files/Git status from the tool observation, run or recommend the template test command, and give optional GitHub remote/push commands. Never claim a GitHub repository was created or pushed unless a tool observation proves it.",
            ]
        )
    if brief.sensitive_domain:
        lines.append(
            f"- Sensitive domain: {brief.sensitive_domain}. Be careful, explain limits, avoid definitive professional advice, and include escalation/professional-help criteria."
        )
    if brief.urgent:
        lines.append(
            "- URGENCY: Put immediate safety actions first. Tell the user to contact local emergency services now when there is danger, severe symptoms, fire/gas, poisoning, or self-harm risk."
        )
    return "\n".join(lines)


def build_solution_brief(
    message: str,
    history: Sequence[str] | str | None = None,
) -> str:
    """Convenience wrapper used by the cortex context builder."""
    return render_solution_brief(analyze_solution_request(message, history=history))


def _specific_troubleshooting_steps(lower: str) -> tuple[str, ...] | None:
    if any(token in lower for token in ("spark", "burning smell", "electric shock", "wiring", "switchboard")):
        return (
            "If there are sparks, smoke, a burning smell, buzzing, or heat from a socket/switchboard, keep people away and avoid touching it with wet hands; switch off the relevant breaker only if you can do so safely.",
            "Unplug the affected appliance from a safe, dry position and do not open panels or attempt internal wiring repairs.",
            "Note which circuit/appliance triggers the problem and whether it trips immediately or only under load.",
            "Call a licensed electrician rather than repeatedly resetting the breaker; repeated trips usually mean a fault, not a nuisance.",
            "Resume use only after the faulty circuit/appliance is tested and the original symptom no longer occurs.",
        )
    if any(token in lower for token in ("pipe leak", "water leak", "tap leaking", "plumbing", "drain blocked", "blocked drain")):
        return (
            "For an active leak, close the nearest water valve (or main supply), keep electrical items away from the water, and contain it with a bucket/towels.",
            "Dry the area and identify whether water comes from a supply pipe, tap joint, appliance hose, trap, or drain; take a clear photo/video before dismantling anything.",
            "Tighten only accessible fittings gently and check washers/hoses; do not over-tighten plastic fittings or use sealant as a substitute for a failed part.",
            "Turn water on briefly while watching the joint; if the leak continues, close the valve again.",
            "Call a plumber for hidden pipes, low pressure after repair, sewage smell/backflow, ceiling stains, or any leak near wiring.",
        )
    if any(token in lower for token in ("fridge", "refrigerator", "freezer")):
        return (
            "Keep the doors closed to protect food. If you have a thermometer, check the fridge is near 3–4°C and freezer near −18°C; move highly perishable food to a cool box/neighbour’s fridge if it is warming up.",
            "Confirm the plug/socket has power and the temperature controls were not accidentally changed; give a recently moved or newly loaded fridge several hours before judging it.",
            "Check that the door seals fully, items are not blocking internal vents, and warm air can circulate around the outside. Clean only accessible dusty condenser areas after unplugging and following the manual.",
            "Listen for the evaporator/condenser fan and compressor: silence, repeated clicking, very hot compressor, heavy frost, or one compartment cold while the other is warm points to different faults—note exactly which pattern you see.",
            "If temperature does not recover after the basic checks, avoid opening sealed refrigerant parts and call a refrigerator technician with the brand/model, compartment temperatures, sounds, and frost pattern.",
        )
    if "washing machine" in lower or "washer" in lower:
        return (
            "If water is leaking or the machine smells electrical, stop the cycle, turn off the water tap, and unplug it before inspecting anything.",
            "Note the exact stage/error code: fill, wash, drain, spin, door-lock, vibration, or leak. Check the door/lid is fully closed and the load is not one heavy item balled on one side.",
            "Inspect accessible inlet/drain hoses for kinks and clean the drain-pump filter only after preparing towels/a shallow tray for residual water.",
            "Run a short rinse/drain test with a small balanced load and watch where the symptom returns; do not keep forcing a burning smell, sparking, or major leak.",
            "Call a technician for motor, drum, pressure-switch, control-board, or internal hose faults, and share the model/error code and stage where it fails.",
        )
    if any(token in lower for token in ("air conditioner", " ac ", "split ac", "window ac")) or lower.startswith("ac "):
        return (
            "Confirm mode is Cool (not Fan/Dry), set temperature a few degrees below room temperature, and check remote batteries and the indoor filter.",
            "Clean a washable indoor filter as the manual allows, keep doors/windows closed, and ensure the outdoor unit is not blocked.",
            "Notice whether air is flowing but warm, airflow is weak, ice forms, water drips indoors, or the outdoor fan/compressor never starts—each pattern narrows the fault.",
            "Do not open refrigerant lines or electrical panels. If ice forms, switch cooling off and let it thaw rather than scraping it.",
            "Book an AC technician if cooling does not return after filter/mode checks; share model, error code, airflow, icing, and outdoor-unit behaviour.",
        )
    if any(token in lower for token in ("car won't start", "car not starting", "bike won't start", "vehicle won't start", "engine won't start")):
        return (
            "Put the vehicle in Park/Neutral with the parking brake on. Note whether dashboard lights come on, you hear a click/crank, or the engine turns but does not fire.",
            "Check fuel level, obvious loose/corroded battery terminals, and whether lights dim sharply during cranking; do not keep cranking for long stretches.",
            "Try the spare key/fob battery if the immobilizer light behaves unusually, and follow the manual before any jump-start attempt—wrong connections can damage electronics.",
            "If there is a fuel smell, smoke, overheating, or battery damage/swelling, do not jump-start it.",
            "Use roadside assistance/a mechanic and report the sound, dashboard lights, recent fuel/battery work, and any warning lamps.",
        )
    if any(token in lower for token in ("wifi", "wi-fi", "router", "internet", "broadband")):
        return (
            "Test whether the failure affects one device or every device, and note router/ONT light colours before changing settings.",
            "Restart in order: turn off router/ONT for 30 seconds, power the ONT/modem first, wait for stable lights, then power the router.",
            "Test near the router and, if possible, with a cable or mobile hotspot to separate Wi-Fi signal problems from the internet line itself.",
            "Check for a provider outage/account issue through the official app/helpline; avoid factory reset until you have saved broadband/PPPoE details.",
            "If wired internet also fails after the ordered restart, contact the provider with light status, outage start time, and tests already done.",
        )
    if any(token in lower for token in ("laptop", "computer", "phone", "mobile", "printer", "pc ", "screen", "app crash")):
        return (
            "Capture the exact error, what you were doing, and whether it began after an update, drop, spill, new accessory, or storage filling up.",
            "Restart once, remove non-essential accessories, and test with a known-good charger/cable/account or document where relevant.",
            "Check available storage, pending updates, date/time, and permissions; for a printer, verify paper/ink, queue status, and whether its own test page prints.",
            "Back up important data before resets, OS repair, or battery/storage replacement; change one setting at a time and retest.",
            "Stop and seek service for swelling/burning smell, liquid damage, repeated shutdowns, clicking storage, or data you cannot afford to lose.",
        )
    return None


def _food_business_steps(lower: str) -> tuple[str, ...]:
    india_context = any(
        token in lower
        for token in ("india", "patna", "bihar", "delhi", "mumbai", "kolkata", "chennai", "bengaluru", "bangalore", "hyderabad", "pune")
    )
    license_step = (
        "Before signing a lease or buying major equipment, verify the exact current permissions from official sources: in India check FSSAI registration/licence category plus local trade, fire, water, pollution, and premises requirements for the specific address."
        if india_context
        else "Before signing a lease or buying major equipment, verify food-business registration, premises, fire, water/waste, and delivery-platform rules from official local sources."
    )
    return (
        "Choose one customer and a tight starting menu built around one clear occasion (office lunch, family dinner, snacks, healthy meals); interview and take trial orders from at least 10 target customers in the delivery radius.",
        "Cost every dish properly: ingredients, packaging, gas/electricity, wastage, staff time, rent allocation, delivery cost, and aggregator commission. Remove dishes that cannot make a contribution after those costs.",
        license_step,
        "Start lean with 6–10 standardized dishes, written portion/recipe cards, two suppliers for critical ingredients, and a rented/shared compliant kitchen if that is cheaper than a full setup.",
        "Soft-launch for 7–14 days and track orders, repeat rate, prep time, wastage, ratings/complaints, and profit per order daily; buy larger equipment only after a dish and channel repeat profitably.",
    )


def _fallback_steps(brief: SolutionBrief, message: str = "") -> tuple[str, ...]:
    intent = brief.intent
    if intent == "troubleshooting":
        specific = _specific_troubleshooting_steps(message.lower())
        if specific is not None:
            return specific
        return (
            "Write down the exact symptom, error text/code, and when it happens; do not change several things at once.",
            "Check the basics first: power/input, connections, supplies/settings, and anything changed immediately before the problem.",
            "Try the safest reversible test (restart, known-good part/setting, or a minimal example) and note whether the symptom changes.",
            "Isolate one variable at a time until the failing part is identified; before a reset or repair, protect people, food, water/electrical safety, and important data as relevant.",
            "Apply the smallest fix for that cause, then repeat the original failing action to verify it is actually solved.",
        )
    if intent == "create_repository" and brief.repository is not None:
        return (
            f"Create '{brief.repository.name}' from the '{brief.repository.template}' template with README, license, .gitignore, source, and a starter test.",
            "Initialize Git on the main branch and make an initial commit only inside the new project folder.",
            "Run the starter test/health check and fix the scaffold before adding features.",
            "Add one small vertical slice of the real product, commit it, then connect a GitHub remote when you are ready to publish.",
        )
    if intent == "build_software":
        return (
            "Define the smallest useful version: user, main screen/action, data in, and result out.",
            "Inspect the existing project or choose the simplest stack that fits; avoid adding services you do not need yet.",
            "Build one end-to-end slice, then add validation, error states, and persistence.",
            "Run targeted tests and a manual happy-path check; record run commands in the README.",
        )
    if intent == "decision":
        return (
            "List the realistic options and remove any that fail a hard constraint (budget, deadline, safety, availability).",
            "Score the remaining options on the three criteria that matter most to you; do not let minor features outweigh the main outcome.",
            "Check total cost of ownership (time, maintenance, fees, learning curve), not only the purchase price.",
            "Choose the option with the best outcome under your constraints, set a review date, and define what evidence would make you switch.",
        )
    if intent == "research":
        return (
            "Define the exact question and date range so old information is not mixed with current rules or prices.",
            "Prefer official/primary sources first, then reputable secondary reporting; capture publication dates.",
            "Cross-check any important number or claim in at least two independent sources.",
            "Separate what is confirmed from estimates and opinions before making a decision.",
        )
    if intent == "learning" or intent == "real_world_study":
        return (
            "Take a quick baseline test or list what you already know; split the syllabus into weak, medium, and strong topics.",
            "Study in focused blocks: learn one concept, close the notes, recall it aloud/written, then solve examples.",
            "Use spaced revision after 1 day, 3 days, and 7 days; keep an error notebook for repeated mistakes.",
            "Finish each week with a timed mixed test and adjust the next week based on errors, not hours alone.",
        )
    if intent == "real_world_business":
        if any(
            token in message.lower()
            for token in ("cloud kitchen", "restaurant", "cafe", "bakery", "tiffin", "food business", "food startup")
        ):
            return _food_business_steps(message.lower())
        return (
            "Pick one specific customer and one painful problem; write the offer in one sentence before buying inventory or building a full product.",
            "Talk to 10 target customers and ask what they currently do, what it costs them, and whether they would pay for a trial.",
            "Create a minimum offer you can deliver this week; price from costs, delivery time, fees, and a realistic margin.",
            "Pre-sell or take small paid trials, deliver manually if needed, collect proof/results, then automate only the repeated parts.",
            "Track leads, conversions, delivery cost, and repeat/referral rate weekly; improve one bottleneck at a time.",
        )
    if intent == "real_world_money":
        return (
            "List monthly income, fixed expenses, debts with interest/minimum payments, and current cash available.",
            "Protect essentials and minimum payments first; build a starter emergency buffer before optional investing.",
            "Direct extra money to the highest-interest debt while keeping payments current; automate transfers on payday.",
            "Set one measurable 30-day target and review weekly. Verify tax/product rules from official sources before acting.",
        )
    if intent == "real_world_career":
        return (
            "Choose 3–5 target roles and extract the repeated skills, tools, and proof employers ask for.",
            "Close the largest proof gap with one portfolio project or measurable work sample tied to those roles.",
            "Rewrite the CV around outcomes and keywords from real postings; keep one master version and tailor copies.",
            "Apply in focused batches, prepare stories for common interviews, and track replies to improve the pitch.",
        )
    if intent == "real_world_travel":
        return (
            "Fix dates, starting city, budget ceiling, and must-see priorities before booking non-refundable items.",
            "Group places by area to reduce transit time; leave buffer on arrival and departure days.",
            "Verify official transport, entry/document, weather, and closure information close to the travel date.",
            "Keep digital and offline copies of IDs, bookings, emergency contacts, and payment backups.",
        )
    if intent == "writing":
        return (
            "State the audience and the one action or feeling the text should produce.",
            "Lead with the key point, add only the necessary context, and end with a clear next step or deadline.",
            "Replace vague claims with specific facts, dates, and outcomes; read it aloud once to catch awkward tone.",
        )
    return (
        "Define the finished result in one sentence and the constraints that cannot be violated (budget, deadline, safety, quality).",
        "Gather the missing facts that would change the decision; do not spend time optimizing details that do not affect the outcome.",
        "Do the smallest useful first step today, check the result, then commit to the larger plan.",
        "Write a short checklist with owner, deadline, cost/time, and a fallback if the first approach fails.",
    )


def build_practical_fallback(
    message: str,
    model_label: str | None = None,
    history: Sequence[str] | str | None = None,
) -> str:
    """Build a useful deterministic answer for offline/simulation mode.

    This is deliberately honest: it provides a practical framework and next
    actions, but does not pretend to know volatile facts, execute mutations,
    or replace a live model's reasoning.
    """
    brief = analyze_solution_request(message, history=history)
    goal = brief.goal.rstrip(".")

    if brief.readiness == "clarify_first" and brief.intent != "urgent_safety":
        questions = "\n".join(
            f"{index}. {question}"
            for index, question in enumerate(brief.clarifying_questions, start=1)
        )
        return (
            "## Quick clarification needed\n"
            "I can help with this, but one material detail is missing and guessing could send the work in the wrong direction.\n\n"
            f"{questions}\n\n"
            "Reply with those details and I’ll turn it into a concrete result. I have not changed any files or taken external action."
        )

    compound = len(brief.workstreams) >= 3 and brief.intent != "create_repository"
    effective_message = message
    if brief.context_used and history:
        prior_turns = _normalize_history(history, current=message)
        if prior_turns:
            # A short follow-up ("make it cheaper") should retain the prior
            # topic when choosing domain-specific fallback steps.
            effective_message = f"{prior_turns[-1]} {message}"
    steps = (
        brief.execution_phases
        if compound and brief.execution_phases
        else _fallback_steps(brief, effective_message)
    )
    missing = (
        "\n".join(f"- {item}" for item in brief.missing_context)
        if brief.missing_context
        else "- No critical missing detail identified."
    )
    numbered_steps = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))

    if brief.intent == "urgent_safety":
        return (
            "## Do this now\n"
            "If anyone is in immediate danger, has severe symptoms, or there is fire/gas/poisoning/self-harm risk, "
            "call your local emergency number now and move to a safe place. Do not wait for an AI response.\n\n"
            f"For your situation — **{goal}** — keep the person safe, avoid giving food/drink/medicine unless emergency "
            "professionals advise it, and share the exact location, symptoms/event, and time it started with responders.\n\n"
            "Once emergency help is on the way, tell me what happened and what responders advised; I can help you organize next steps."
        )

    if brief.intent == "create_repository" and brief.repository is not None:
        repo = brief.repository
        return (
            f"I can create **{repo.name}** as a local, Git-ready **{repo.template}** repository.\n\n"
            "## Build plan\n"
            f"{numbered_steps}\n\n"
            "## What the scaffold includes\n"
            "- README with run/test commands\n"
            "- Source starter and a small verification test\n"
            "- MIT license, .gitignore, and optional GitHub Actions CI\n"
            "- Git initialization and an initial commit (inside the new folder only)\n\n"
            "Use the chat in **Code** mode after approving workspace tools, or open **Projects → Repository builder**. "
            "I will only claim it was created after the repository tool returns the actual path and file list."
        )

    title = "Practical solution plan"
    if compound:
        title = "Multi-step execution plan"
    elif brief.intent == "troubleshooting":
        title = "Troubleshooting plan"
    elif brief.intent == "decision":
        title = "Decision plan"
    elif brief.intent == "research":
        title = "Evidence-first research plan"
    elif brief.intent == "learning":
        title = "Learning plan"

    safety = ""
    if brief.sensitive_domain in {"medical", "legal", "financial"}:
        safety = (
            "\n\n> This is general information, not professional "
            f"{brief.sensitive_domain} advice. Verify high-impact decisions with a qualified professional or official source."
        )
    current_note = ""
    if brief.needs_current_info:
        current_note = (
            "\n\n**Current-information note:** prices, laws, dates, and availability change. Verify them on official "
            "sources before spending money or filing anything; do not treat an offline estimate as current fact."
        )

    verification = (
        "\n".join(f"- {item}" for item in brief.acceptance_criteria)
        if brief.acceptance_criteria
        else (
            "- The original problem or goal is tested again, not assumed fixed.\n"
            "- Cost, deadline, and any safety/legal constraints are written down.\n"
            "- You have one fallback if the first approach does not work."
        )
    )
    compound_note = ""
    if compound:
        workstream_list = ", ".join(name.replace("_", " ") for name in brief.workstreams)
        compound_note = (
            f"I’m treating this as one connected task with these workstreams: **{workstream_list}**. "
            "In offline planning mode I have not changed files or run external actions; the live/tool path should execute the phases below and report evidence for each one.\n\n"
        )

    model_note = f" ({model_label})" if model_label else ""
    return (
        f"## {title}\n"
        f"For **{goal}**, use this order so you solve the real constraint first instead of collecting random tips{model_note}.\n\n"
        f"{compound_note}"
        f"## Best first move\n{steps[0]}\n\n"
        f"## Step-by-step\n{numbered_steps}\n\n"
        "## Details that would make this tighter\n"
        f"{missing}\n\n"
        "## Verify you are done\n"
        f"{verification}"
        f"{current_note}{safety}"
    )
