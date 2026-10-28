"""Frontend-design and polyglot coding intelligence for Nexus.

This pure domain module gives the cortex a specialist brief for software
work.  It detects the requested language/frontend surface, selects modern
idioms and failure modes to avoid, names the verification checks that should
prove the result, and performs a few deterministic safety/quality checks on
code that is returned directly in chat.

It deliberately does not execute code or inspect the workspace.  Workspace
adapters provide diagnostics/build/test evidence; this module provides the
portable policy that tells the model what "excellent" means for the task.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

CODING_FOCUSES = (
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
)

# The first eight are the explicitly requested specialist languages.  The
# remaining entries support the frontend stack that normally surrounds HTML5.
SUPPORTED_CODING_LANGUAGES = (
    "c",
    "cpp",
    "rust",
    "python",
    "php",
    "html5",
    "xml",
    "ruby",
    "javascript",
    "typescript",
    "css",
)

_FOCUS_ALIASES = {
    "": "auto",
    "automatic": "auto",
    "code": "auto",
    "coding": "auto",
    "general": "auto",
    "front_end": "frontend",
    "front-end": "frontend",
    "ui": "frontend",
    "web_ui": "frontend",
    "web": "frontend",
    "c++": "cpp",
    "cplusplus": "cpp",
    "c_plus_plus": "cpp",
    "rs": "rust",
    "py": "python",
    "html": "html5",
    "rb": "ruby",
}


@dataclass(frozen=True)
class LanguagePlaybook:
    """Modern defaults and review rules for one language or markup format."""

    language_id: str
    label: str
    standard: str
    principles: tuple[str, ...]
    pitfalls: tuple[str, ...]
    verification_checks: tuple[str, ...]
    file_extensions: tuple[str, ...]
    fence_aliases: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.language_id,
            "label": self.label,
            "standard": self.standard,
            "principles": list(self.principles),
            "pitfalls": list(self.pitfalls),
            "verification_checks": list(self.verification_checks),
            "file_extensions": list(self.file_extensions),
            "fence_aliases": list(self.fence_aliases),
        }


LANGUAGE_PLAYBOOKS: dict[str, LanguagePlaybook] = {
    "c": LanguagePlaybook(
        language_id="c",
        label="C",
        standard="C17 by default (C11-compatible when required)",
        principles=(
            "make ownership, lifetimes, buffer sizes, and error returns explicit",
            "compile warning-clean with -Wall -Wextra -Wpedantic and test under ASan/UBSan",
            "prefer small functions, const-correct interfaces, and checked conversions",
        ),
        pitfalls=(
            "gets/strcpy/strcat/sprintf or unbounded scanf input",
            "undefined behaviour, signed overflow, use-after-free, and unchecked malloc",
            "hidden ownership transfer or macros with multiple-evaluation side effects",
        ),
        verification_checks=("c_syntax", "make_test", "cmake_build", "ctest"),
        file_extensions=(".c", ".h"),
        fence_aliases=("c",),
    ),
    "cpp": LanguagePlaybook(
        language_id="cpp",
        label="C++",
        standard="C++20 by default",
        principles=(
            "use RAII, value semantics, std::unique_ptr/shared_ptr, string_view/span, and const correctness",
            "prefer algorithms/ranges and strong types over raw loops and primitive obsession",
            "build warning-clean with sanitizers and keep headers self-contained",
        ),
        pitfalls=(
            "owning raw new/delete, dangling views, iterator invalidation, and slicing",
            "signed/unsigned surprises, data races, and exceptions escaping noexcept boundaries",
            "using namespace std in headers or premature template cleverness",
        ),
        verification_checks=("cpp_syntax", "make_test", "cmake_build", "ctest"),
        file_extensions=(".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"),
        fence_aliases=("cpp", "c++", "cc", "cxx"),
    ),
    "rust": LanguagePlaybook(
        language_id="rust",
        label="Rust",
        standard="Rust 2021 or newer with rustfmt and Clippy",
        principles=(
            "model errors with Result/Option and make illegal states unrepresentable",
            "borrow first, clone deliberately, and keep unsafe tiny with a written SAFETY proof",
            "write idiomatic iterator/error-propagation code and test public behaviour",
        ),
        pitfalls=(
            "unwrap/expect in library paths, hidden panics, and needless Rc<RefCell> workarounds",
            "fighting the borrow checker with leaked lifetimes or broad unsafe blocks",
            "blocking in async tasks or holding locks across await points",
        ),
        verification_checks=("cargo_fmt", "cargo_check", "cargo_clippy", "cargo_test"),
        file_extensions=(".rs",),
        fence_aliases=("rust", "rs"),
    ),
    "python": LanguagePlaybook(
        language_id="python",
        label="Python",
        standard="Python 3.11+ with type hints, Ruff, Mypy, and pytest",
        principles=(
            "prefer explicit data flow, small typed functions, and standard-library solutions first",
            "handle errors at boundaries and keep sync/async responsibilities separate",
            "test behaviour and edge cases rather than implementation trivia",
        ),
        pitfalls=(
            "eval/exec, pickle of untrusted data, shell=True with interpolated input",
            "mutable default arguments, bare except, and hidden global state",
            "N+1 I/O, unbounded reads, and timezone-naive datetimes",
        ),
        verification_checks=("python_compile", "python_lint", "python_typecheck", "pytest"),
        file_extensions=(".py", ".pyi"),
        fence_aliases=("python", "py"),
    ),
    "php": LanguagePlaybook(
        language_id="php",
        label="PHP",
        standard="PHP 8.2+ with strict_types and Composer autoloading",
        principles=(
            "use typed parameters/returns, readonly value objects, and framework-native validation",
            "use PDO prepared statements, password_hash/password_verify, and context-aware escaping",
            "validate and authorize at the edge; keep SQL, HTML, and business rules separate",
        ),
        pitfalls=(
            "echoing request data without htmlspecialchars or building SQL by concatenation",
            "weak md5/sha1 password hashing, loose comparisons, and suppressed errors",
            "trusting uploaded filenames/MIME types or exposing stack traces",
        ),
        verification_checks=("php_lint", "composer_test"),
        file_extensions=(".php", ".phtml"),
        fence_aliases=("php",),
    ),
    "html5": LanguagePlaybook(
        language_id="html5",
        label="HTML5",
        standard="HTML5 with semantic, accessible, responsive document structure",
        principles=(
            "use landmarks, real controls, labelled fields, meaningful headings, and alt text",
            "design mobile-first with fluid layout, visible focus, and reduced-motion support",
            "keep content usable before JavaScript and make loading/empty/error states explicit",
        ),
        pitfalls=(
            "div soup, clickable divs, missing labels/alt/viewport, and keyboard traps",
            "inline event handlers, placeholder-only labels, and target=_blank without rel",
            "fixed pixel layouts that overflow small screens",
        ),
        verification_checks=("frontend_quality", "npm_typecheck", "npm_build"),
        file_extensions=(".html", ".htm"),
        fence_aliases=("html", "html5"),
    ),
    "xml": LanguagePlaybook(
        language_id="xml",
        label="XML",
        standard="XML 1.0, UTF-8, explicit namespaces, schema-validated when a contract exists",
        principles=(
            "keep documents well-formed, namespace-aware, and escaped by construction",
            "disable DTD/external entities for untrusted input and bound document size/depth",
            "prefer elements for structured content and attributes for stable metadata",
        ),
        pitfalls=(
            "XXE, billion-laughs entity expansion, and DTD SYSTEM identifiers",
            "string-built XML without escaping or namespace-prefix string matching",
            "using CDATA to hide data that should be modelled or escaped",
        ),
        verification_checks=("xml_validate",),
        file_extensions=(".xml", ".xsd", ".xsl", ".xslt", ".svg"),
        fence_aliases=("xml", "xsd", "xslt", "svg"),
    ),
    "ruby": LanguagePlaybook(
        language_id="ruby",
        label="Ruby",
        standard="Ruby 3.x with frozen_string_literal, Bundler, and Minitest/RSpec",
        principles=(
            "write small objects with intention-revealing names and idiomatic Enumerable flow",
            "raise/rescue specific errors and keep metaprogramming rare and test-covered",
            "prefer keyword arguments for options and freeze shared constants",
        ),
        pitfalls=(
            "eval/Marshal.load on untrusted data or shell interpolation",
            "rescue Exception, monkey-patching core classes, and hidden mutable globals",
            "N+1 queries and Rails callbacks hiding essential business flow",
        ),
        verification_checks=("ruby_syntax", "ruby_test"),
        file_extensions=(".rb", ".rake", ".gemspec"),
        fence_aliases=("ruby", "rb"),
    ),
    "javascript": LanguagePlaybook(
        language_id="javascript",
        label="JavaScript",
        standard="Modern ES2022+ modules",
        principles=(
            "prefer const, pure helpers, explicit async error handling, and accessible DOM APIs",
            "avoid unnecessary dependencies and keep network/state boundaries testable",
            "use semantic events and progressive enhancement where practical",
        ),
        pitfalls=(
            "innerHTML with untrusted data, implicit globals, and floating promises",
            "layout thrash, huge bundles, and inaccessible custom controls",
            "trusting client-side validation as a security boundary",
        ),
        verification_checks=("npm_lint", "npm_test", "npm_build"),
        file_extensions=(".js", ".mjs", ".cjs", ".jsx"),
        fence_aliases=("javascript", "js", "jsx"),
    ),
    "typescript": LanguagePlaybook(
        language_id="typescript",
        label="TypeScript",
        standard="TypeScript strict mode",
        principles=(
            "model domain states with discriminated unions and validate unknown external data",
            "keep component props narrow, derive state where possible, and type async boundaries",
            "prefer readable composition over generic/framework cleverness",
        ),
        pitfalls=(
            "any/non-null assertions to silence real states and unsound type casts",
            "stale closures, effect spaghetti, and duplicated server/client state",
            "unlabelled controls and div-based interactive elements in JSX",
        ),
        verification_checks=("npm_typecheck", "npm_lint", "npm_test", "npm_build"),
        file_extensions=(".ts", ".tsx", ".mts", ".cts"),
        fence_aliases=("typescript", "ts", "tsx"),
    ),
    "css": LanguagePlaybook(
        language_id="css",
        label="CSS",
        standard="Modern CSS with custom properties, cascade layers where useful, Grid/Flexbox",
        principles=(
            "use design tokens, a 4/8px spacing rhythm, fluid type, and container-aware layout",
            "make focus, hover, disabled, loading, empty, and error states first-class",
            "respect prefers-reduced-motion and avoid expensive shadows/filters on large surfaces",
        ),
        pitfalls=(
            "magic pixel values, !important wars, global resets that remove focus outlines",
            "fixed heights that clip localized text and layouts that overflow at 320px",
            "color as the only status signal or contrast below WCAG AA",
        ),
        verification_checks=("frontend_quality", "npm_build"),
        file_extensions=(".css", ".scss"),
        fence_aliases=("css", "scss"),
    ),
}


_FRONTEND_COMMON_GOALS = (
    "clear visual hierarchy with one obvious primary action",
    "design tokens and a consistent 4/8px spacing rhythm",
    "mobile-first responsive layout that remains usable at 320px and wide desktop",
    "semantic HTML, keyboard-complete interaction, visible focus, and WCAG-conscious contrast",
    "explicit loading, empty, error, disabled, and success states",
    "reduced-motion support and performance-conscious assets/effects",
)

_FRONTEND_KIND_GOALS: dict[str, tuple[str, ...]] = {
    "dashboard": (
        "scannable data density, sticky context, filters, and responsive tables/cards",
        "skeletons instead of layout jump and text alternatives for charts",
    ),
    "form": (
        "visible labels, autocomplete, inline errors linked with aria-describedby, and preserved input",
        "one-column flow, clear progress, pending submit state, and confirmation",
    ),
    "landing": (
        "one primary CTA, concise benefit-led sections, responsive media, and honest proof only",
        "SEO/social metadata and fast first paint without heavy hero effects",
    ),
    "commerce": (
        "transparent price/total, accessible quantity/cart controls, and trust/error recovery states",
        "product imagery with useful alt text and no dark-pattern urgency",
    ),
    "design_system": (
        "tokenized color/type/spacing/radius/elevation with documented component states",
        "composable primitives, consistent naming, and examples for every variant",
    ),
    "content": (
        "readable measure/line-height, strong heading outline, and navigable long-form layout",
        "print-friendly content and descriptive link text",
    ),
    "game": (
        "stable frame loop, pause/reduced-motion controls, and non-color status cues",
        "canvas fallback text and keyboard/touch controls with visible state",
    ),
    "app_shell": (
        "predictable navigation, resilient route-level states, and no content shift",
        "component boundaries around data, presentation, and interaction state",
    ),
}


@dataclass(frozen=True)
class CodingProfile:
    """Specialist profile for one software/frontend request."""

    is_coding: bool = False
    focus: str = "auto"
    languages: tuple[str, ...] = ()
    frameworks: tuple[str, ...] = ()
    frontend_kind: str | None = None
    design_goals: tuple[str, ...] = ()
    principles: tuple[str, ...] = ()
    pitfalls: tuple[str, ...] = ()
    verification_checks: tuple[str, ...] = ()
    quality_checks: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    complexity_boost: float = 0.0

    @property
    def is_frontend(self) -> bool:
        return self.frontend_kind is not None

    @property
    def language_labels(self) -> tuple[str, ...]:
        return tuple(LANGUAGE_PLAYBOOKS[item].label for item in self.languages if item in LANGUAGE_PLAYBOOKS)

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_coding": self.is_coding,
            "focus": self.focus,
            "languages": list(self.languages),
            "language_labels": list(self.language_labels),
            "frameworks": list(self.frameworks),
            "frontend_kind": self.frontend_kind,
            "is_frontend": self.is_frontend,
            "design_goals": list(self.design_goals),
            "principles": list(self.principles),
            "pitfalls": list(self.pitfalls),
            "verification_checks": list(self.verification_checks),
            "quality_checks": list(self.quality_checks),
            "reasons": list(self.reasons),
            "complexity_boost": round(float(self.complexity_boost), 3),
            "supported_languages": list(SUPPORTED_CODING_LANGUAGES),
        }


@dataclass(frozen=True)
class CodingFinding:
    """One deterministic problem found in code returned directly in chat."""

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


def normalize_coding_focus(value: str | None) -> str:
    """Normalize an API/UI coding focus to a supported identifier."""

    normalized = str(value or "auto").strip().lower().replace("-", "_")
    if normalized in CODING_FOCUSES:
        return normalized
    return _FOCUS_ALIASES.get(normalized, "auto")


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def _language_from_extension(path: str) -> str | None:
    lower = str(path or "").lower()
    for language_id in SUPPORTED_CODING_LANGUAGES:
        if any(lower.endswith(ext) for ext in LANGUAGE_PLAYBOOKS[language_id].file_extensions):
            # .h is intentionally ambiguous; callers use message/framework
            # evidence to choose C or C++.  Returning C here would mislabel
            # many C++ headers, so leave a lone .h unresolved.
            if lower.endswith(".h") and language_id in {"c", "cpp"}:
                return None
            return language_id
    return None


def detect_coding_languages(
    message: str,
    *,
    paths: Sequence[str] = (),
) -> tuple[str, ...]:
    """Detect explicitly requested or file-implied coding languages."""

    text = str(message or "")
    lower = text.lower()
    found: list[str] = []

    def add(language_id: str) -> None:
        if language_id not in found:
            found.append(language_id)

    # C++ must be tested before C so the plus signs are never swallowed.
    if re.search(r"c\+\+|cplusplus|\bcpp\b|std::", lower):
        add("cpp")
    c_patterns = (
        r"\bC\s*(?:11|17|23)\b",
        r"\b(?:ANSI|ISO)\s+C\b",
        r"\bC language\b",
        r"\b(?:in|using|with|written in|program in|code in)\s+C(?:\b|[.,;:])",
        r"(?<![A-Za-z])C(?=\s*(?:\.|,|/|and\b))",
        r"\.c(?![A-Za-z])",
    )
    if any(re.search(pattern, text) for pattern in c_patterns):
        # Place C before C++ in the public ordering requested by users.
        if "cpp" in found:
            found.insert(found.index("cpp"), "c")
        else:
            add("c")

    patterns: tuple[tuple[str, str], ...] = (
        ("rust", r"\brust\b|\bcargo\b|\.rs\b"),
        ("python", r"\bpython\b|\bpytest\b|\.py\b"),
        ("php", r"\bphp\b|\bcomposer\b|\blaravel\b|\bsymfony\b|\.php\b"),
        ("html5", r"\bhtml(?:5)?\b|\.html?\b"),
        ("xml", r"\bxml\b|\bxslt?\b|\bxsd\b|\.xml\b|\.svg\b"),
        ("ruby", r"\bruby\b|\brails\b|\bgemfile\b|\brspec\b|\.rb\b"),
        ("javascript", r"\bjavascript\b|\.jsx?\b|\bnode\.js\b"),
        ("typescript", r"\btypescript\b|\.tsx?\b"),
        ("css", r"\bcss\b|\bscss\b|\.css\b|\.scss\b"),
    )
    for language_id, pattern in patterns:
        if re.search(pattern, lower):
            add(language_id)

    for path in paths:
        path_language = _language_from_extension(path)
        if path_language:
            add(path_language)

    order = {language_id: index for index, language_id in enumerate(SUPPORTED_CODING_LANGUAGES)}
    return tuple(sorted(found, key=lambda item: order[item]))


def _detect_frameworks(text: str) -> tuple[str, ...]:
    lower = str(text or "").lower()
    frameworks: list[str] = []
    patterns = {
        "React": r"\breact\b",
        "Vite": r"\bvite\b",
        "Next.js": r"\bnext\.?js\b",
        "Vue": r"\bvue(?:\.js)?\b",
        "Angular": r"\bangular\b",
        "Svelte": r"\bsvelte\b",
        "Tailwind CSS": r"\btailwind\b",
        "FastAPI": r"\bfastapi\b",
        "Django": r"\bdjango\b",
        "Flask": r"\bflask\b",
        "Laravel": r"\blaravel\b",
        "Symfony": r"\bsymfony\b",
        "Rails": r"\brails\b",
        "CMake": r"\bcmake\b",
        "Cargo": r"\bcargo\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, lower):
            frameworks.append(label)
    return tuple(frameworks)


def _frontend_kind(text: str) -> str | None:
    lower = str(text or "").lower()
    frontend_terms = (
        r"\b(?:frontend|front-end|user interface|clean ui|ui design|web design|website|web app|"
        r"landing page|dashboard|design system|component library|react|vite|html5?|css|"
        r"responsive (?:page|site|ui|layout)|checkout|sign[- ]?up form|login form)\b"
    )
    if not re.search(frontend_terms, lower):
        return None
    kind_patterns: tuple[tuple[str, str], ...] = (
        ("design_system", r"\b(?:design system|component library|ui kit)\b"),
        ("dashboard", r"\b(?:dashboard|admin|analytics|crm|saas|console)\b"),
        ("commerce", r"\b(?:e-?commerce|shop|store|cart|checkout|product page)\b"),
        ("form", r"\b(?:form|sign[- ]?up|login|register|wizard|onboarding)\b"),
        ("game", r"\b(?:game|canvas game|playable)\b"),
        ("content", r"\b(?:blog|docs|documentation|article|news|magazine)\b"),
        ("landing", r"\b(?:landing|marketing|portfolio|homepage|website|site)\b"),
        ("app_shell", r"\b(?:web app|app shell|application ui|spa)\b"),
    )
    for kind, pattern in kind_patterns:
        if re.search(pattern, lower):
            return kind
    return "generic_frontend"


def analyze_coding_request(
    message: str,
    *,
    mode: str = "general",
    focus: str | None = None,
    paths: Sequence[str] = (),
    workstreams: Sequence[str] = (),
    operation_level: str = "",
    repository_template: str | None = None,
) -> CodingProfile:
    """Build the specialist coding/design profile for one request."""

    text = " ".join(str(message or "").split())
    lower = text.lower()
    requested_focus = normalize_coding_focus(focus or mode)
    languages = list(detect_coding_languages(text, paths=paths))
    frameworks = list(_detect_frameworks(text))
    frontend_kind = _frontend_kind(text)
    reasons: list[str] = []

    if requested_focus == "frontend":
        frontend_kind = frontend_kind or "generic_frontend"
        reasons.append("user_selected_frontend_focus")
    elif requested_focus in LANGUAGE_PLAYBOOKS:
        if requested_focus not in languages:
            languages.append(requested_focus)
        languages = list(
            tuple(sorted(languages, key=lambda item: SUPPORTED_CODING_LANGUAGES.index(item)))
        )
        reasons.append(f"user_selected_{requested_focus}_focus")
        if requested_focus == "html5":
            frontend_kind = frontend_kind or "generic_frontend"

    template_frontend = repository_template in {
        "react-vite",
        "static-site",
        "frontend-design-system",
        "html5-clean-ui",
    }
    if template_frontend:
        frontend_kind = frontend_kind or (
            "design_system" if repository_template == "frontend-design-system" else "app_shell"
        )
        reasons.append("frontend_repository_template")

    coding_workstreams = {"code_change", "diagnosis_and_fix", "repository_creation", "verification"}
    generic_coding = bool(
        re.search(
            r"\b(?:code|coding|program|function|class|bug|debug|refactor|compile|compiler|"
            r"script|algorithm|api endpoint|repository|repo|test suite|unit test)\b",
            lower,
        )
    )
    is_coding = bool(
        requested_focus != "auto"
        or mode.strip().lower() == "coding"
        or languages
        or frontend_kind
        or set(workstreams) & coding_workstreams
        or (generic_coding and operation_level != "answer_only")
        or (generic_coding and re.search(r"\b(?:write|create|implement|fix|debug|refactor)\b", lower))
    )
    if not is_coding:
        return CodingProfile(focus=requested_focus)

    if frontend_kind:
        reasons.append(f"frontend_{frontend_kind}")
    if languages:
        reasons.append("languages_" + "_".join(languages[:4]))

    design_goals: tuple[str, ...] = ()
    if frontend_kind:
        design_goals = _ordered_unique(
            (*_FRONTEND_COMMON_GOALS, *_FRONTEND_KIND_GOALS.get(frontend_kind, ()))
        )[:8]

    principles: list[str] = []
    pitfalls: list[str] = []
    verification: list[str] = []
    for language_id in languages[:4]:
        playbook = LANGUAGE_PLAYBOOKS[language_id]
        principles.extend(playbook.principles[:2])
        pitfalls.extend(playbook.pitfalls[:2])
        verification.extend(playbook.verification_checks)
    if frontend_kind:
        verification.extend(("frontend_quality", "npm_typecheck", "npm_build"))
    if set(workstreams) & coding_workstreams or operation_level not in {"", "answer_only"}:
        verification.extend(("code_diagnostics", "project_checks"))

    quality_checks = ["language_match", "language_safety", "placeholder_free"]
    if frontend_kind:
        quality_checks.extend(
            ["frontend_semantics", "frontend_accessibility", "frontend_responsive_design"]
        )
    if "xml" in languages:
        quality_checks.append("xml_well_formed")
    if languages:
        quality_checks.append("language_idioms")

    boost = 0.04
    if frontend_kind:
        boost += 0.06
    if len(languages) > 1:
        boost += min(0.08, 0.02 * (len(languages) - 1))
    if repository_template:
        boost += 0.04

    return CodingProfile(
        is_coding=True,
        focus=requested_focus,
        languages=tuple(languages),
        frameworks=tuple(frameworks),
        frontend_kind=frontend_kind,
        design_goals=design_goals,
        principles=_ordered_unique(principles)[:8],
        pitfalls=_ordered_unique(pitfalls)[:8],
        verification_checks=_ordered_unique(verification)[:10],
        quality_checks=_ordered_unique(quality_checks),
        reasons=_ordered_unique(reasons),
        complexity_boost=round(boost, 3),
    )


def build_coding_contract(profile: CodingProfile, *, max_chars: int = 620) -> str:
    """Render a compact specialist addendum for the execution contract."""

    if not profile.is_coding:
        return ""

    segments: list[str] = []
    labels = ", ".join(profile.language_labels[:4])
    standards = "; ".join(
        LANGUAGE_PLAYBOOKS[item].standard for item in profile.languages[:2] if item in LANGUAGE_PLAYBOOKS
    )
    header = "CODING EXCELLENCE"
    if profile.frontend_kind:
        header += f" — frontend={profile.frontend_kind.replace('_', ' ')}"
    if labels:
        header += f"; languages={labels}"
    if standards:
        header += f"; standards={standards}"
    segments.append(header + ".")
    # Verification is a hard part of the contract, so reserve space for it
    # before the longer advisory design/build guidance.
    if profile.verification_checks:
        segments.append("Verify: " + ", ".join(profile.verification_checks[:5]) + ".")
    if profile.design_goals:
        segments.append("Design: " + "; ".join(profile.design_goals[:3]) + ".")
    if profile.principles:
        segments.append("Build: " + "; ".join(profile.principles[:2]) + ".")
    if profile.pitfalls:
        segments.append("Avoid: " + "; ".join(profile.pitfalls[:2]) + ".")

    rendered = ""
    for segment in segments:
        candidate = f"{rendered} {segment}".strip()
        if len(candidate) > max_chars:
            break
        rendered = candidate
    return rendered[:max_chars].rstrip()


@dataclass(frozen=True)
class _CodeBlock:
    raw_language: str
    language: str
    content: str


_FENCE_RE = re.compile(r"```([A-Za-z0-9_+.-]*)\s*\n(.*?)```", re.S)
_FENCE_ALIASES: dict[str, str] = {
    alias: language_id
    for language_id, playbook in LANGUAGE_PLAYBOOKS.items()
    for alias in playbook.fence_aliases
}
_FENCE_ALIASES.update({"c": "c", "html": "html5", "htm": "html5"})


def _extract_code_blocks(answer: str) -> list[_CodeBlock]:
    blocks: list[_CodeBlock] = []
    for raw, content in _FENCE_RE.findall(answer or ""):
        normalized_raw = raw.strip().lower()
        blocks.append(
            _CodeBlock(
                raw_language=normalized_raw,
                language=_FENCE_ALIASES.get(normalized_raw, normalized_raw),
                content=content.strip(),
            )
        )
    if blocks:
        return blocks
    stripped = str(answer or "").strip()
    if stripped.lower().startswith("<!doctype html") or stripped.lower().startswith("<html"):
        return [_CodeBlock("html", "html5", stripped)]
    if stripped.startswith("<?xml"):
        return [_CodeBlock("xml", "xml", stripped)]
    return []


def _html_findings(content: str, *, react: bool = False) -> list[CodingFinding]:
    findings: list[CodingFinding] = []
    lower = content.lower()

    if not react and "<html" in lower:
        missing: list[str] = []
        if "<!doctype html" not in lower:
            missing.append("doctype")
        if not re.search(r"<html\b[^>]*\blang\s*=", content, re.I):
            missing.append("html lang")
        if not re.search(r"<meta\b[^>]*charset\s*=", content, re.I):
            missing.append("charset")
        if not re.search(r"<meta\b[^>]*name\s*=\s*[\"']viewport[\"']", content, re.I):
            missing.append("responsive viewport")
        if "<title" not in lower:
            missing.append("title")
        if "<main" not in lower:
            missing.append("main landmark")
        if missing:
            findings.append(
                CodingFinding(
                    "frontend_document_structure",
                    "major",
                    "The HTML document is missing: " + ", ".join(missing) + ".",
                    "Return a complete semantic HTML5 document with doctype, lang, charset, viewport, title, and a main landmark.",
                )
            )

    images = re.findall(r"<img\b[^>]*>", content, re.I)
    if any(not re.search(r"\balt\s*=", image, re.I) for image in images):
        findings.append(
            CodingFinding(
                "frontend_image_alt",
                "major",
                "At least one image has no alt attribute.",
                "Give informative images useful alt text and decorative images alt=\"\".",
            )
        )

    label_targets = set(re.findall(r"<label\b[^>]*(?:for|htmlFor)\s*=\s*[\"']([^\"']+)[\"']", content, re.I))
    controls = re.findall(r"<(?:input|select|textarea)\b[^>]*>", content, re.I)
    unlabeled = False
    for control in controls:
        if re.search(r"type\s*=\s*[\"'](?:hidden|submit|button|reset)[\"']", control, re.I):
            continue
        if re.search(r"aria-(?:label|labelledby)\s*=", control, re.I):
            continue
        id_match = re.search(r"\bid\s*=\s*[\"']([^\"']+)[\"']", control, re.I)
        if not id_match or id_match.group(1) not in label_targets:
            unlabeled = True
            break
    if unlabeled:
        findings.append(
            CodingFinding(
                "frontend_control_label",
                "major",
                "At least one form control has no programmatically associated label.",
                "Associate every control with a visible label (for/htmlFor) or an appropriate ARIA label; placeholder text is not a label.",
            )
        )

    if re.search(r"\bon(?:click|change|submit|load|error)\s*=", content, re.I):
        findings.append(
            CodingFinding(
                "frontend_inline_handlers",
                "major",
                "Inline event-handler attributes make the UI harder to secure and maintain.",
                "Move behaviour into scripts/components with addEventListener or framework handlers and keep a CSP-friendly structure.",
            )
        )
    if re.search(r"<div\b[^>]*\bonClick\s*=", content):
        findings.append(
            CodingFinding(
                "frontend_non_semantic_control",
                "major",
                "A div is being used as an interactive control.",
                "Use a real button or link so keyboard, focus, and assistive-technology behaviour are correct.",
            )
        )
    blank_links = re.findall(r"<a\b[^>]*target\s*=\s*[\"']_blank[\"'][^>]*>", content, re.I)
    if any("noopener" not in link.lower() for link in blank_links):
        findings.append(
            CodingFinding(
                "frontend_blank_link_rel",
                "minor",
                "A target=_blank link does not include rel=\"noopener\".",
                "Add rel=\"noopener\" (and noreferrer when appropriate) to new-tab links.",
            )
        )
    return findings


def _language_findings(block: _CodeBlock) -> list[CodingFinding]:
    content = block.content
    language = block.language
    findings: list[CodingFinding] = []

    if language == "c" and re.search(
        r"\b(?:gets|strcpy|strcat|sprintf|vsprintf)\s*\(|\bscanf\s*\([^)]*%s",
        content,
    ):
        findings.append(
            CodingFinding(
                "unsafe_c_string_api",
                "critical",
                "The C code uses an unbounded string/input API.",
                "Replace gets/strcpy/strcat/sprintf/scanf %s with bounded APIs, explicit sizes, and checked return values.",
            )
        )
    if language == "cpp" and re.search(
        r"\b[A-Za-z_][\w:<>,\s]*\*\s*[A-Za-z_]\w*\s*=\s*new\b",
        content,
    ):
        findings.append(
            CodingFinding(
                "cpp_raw_owning_allocation",
                "major",
                "The C++ code appears to assign an owning allocation to a raw pointer.",
                "Use value semantics, containers, std::make_unique, or std::make_shared so ownership is exception-safe.",
            )
        )
    if language == "rust":
        if re.search(r"\bunsafe\s*\{", content) and "SAFETY:" not in content:
            findings.append(
                CodingFinding(
                    "rust_unsafe_without_proof",
                    "major",
                    "Rust unsafe code has no SAFETY explanation.",
                    "Shrink the unsafe block and document the invariants that make it sound, or use a safe API.",
                )
            )
        if re.search(r"\bpub\s+fn\b", content) and re.search(r"\.\s*unwrap\s*\(", content):
            findings.append(
                CodingFinding(
                    "rust_unwrap_in_library_code",
                    "major",
                    "Public Rust code uses unwrap, which can panic across an API boundary.",
                    "Return Result/Option or a domain error instead of unwrap in library code.",
                )
            )
    if language == "python" and re.search(
        r"\b(?:eval|exec)\s*\(|pickle\.loads\s*\(|shell\s*=\s*True",
        content,
    ):
        findings.append(
            CodingFinding(
                "unsafe_python_execution",
                "critical",
                "The Python code uses dynamic execution, unsafe deserialization, or a shell.",
                "Parse data explicitly, use JSON/AST-safe evaluation, and pass subprocess arguments as a list without shell=True.",
            )
        )
    if language == "php":
        unsafe_output = re.search(r"\b(?:echo|print)\b[^;]*(?:\$_GET|\$_POST|\$_REQUEST|\$_COOKIE)", content)
        unsafe_sql = re.search(
            r"(?:query|prepare|exec)\s*\([^)]*(?:\$_GET|\$_POST|\$_REQUEST|\.\s*\$|\{\$)",
            content,
            re.S,
        )
        if unsafe_output or unsafe_sql:
            findings.append(
                CodingFinding(
                    "unsafe_php_input_handling",
                    "critical",
                    "The PHP code appears to output or query with unescaped request data.",
                    "Validate input, escape output with htmlspecialchars, and use PDO prepared statements with bound parameters.",
                )
            )
        if re.search(r"\b(?:md5|sha1)\s*\([^)]*password", content, re.I):
            findings.append(
                CodingFinding(
                    "weak_php_password_hash",
                    "critical",
                    "The PHP code hashes a password with a fast general-purpose digest.",
                    "Use password_hash and password_verify with a current password algorithm.",
                )
            )
    if language == "ruby" and re.search(
        r"\b(?:eval|Marshal\.load)\s*\(?|\bsystem\s*\(?\s*[\"'][^\"']*#\{|`[^`]*#\{",
        content,
    ):
        findings.append(
            CodingFinding(
                "unsafe_ruby_execution",
                "critical",
                "The Ruby code uses eval, unsafe Marshal loading, or shell interpolation.",
                "Parse data explicitly and invoke commands with argument arrays instead of interpolated shell strings.",
            )
        )
    if language in {"javascript", "typescript"} and "dangerouslySetInnerHTML" in content:
        findings.append(
            CodingFinding(
                "frontend_dangerous_html",
                "major",
                "The frontend code injects raw HTML.",
                "Render structured data as elements or sanitize trusted HTML with a vetted sanitizer and explain the trust boundary.",
            )
        )
    return findings


def _xml_findings(block: _CodeBlock) -> list[CodingFinding]:
    content = block.content.strip()
    if not content.startswith("<"):
        return []
    if re.search(r"<!DOCTYPE[^>[\]]*(?:\[[\s\S]*?)?(?:ENTITY|SYSTEM)", content, re.I):
        return [
            CodingFinding(
                "xml_external_entity",
                "critical",
                "The XML declares entities or an external SYSTEM identifier.",
                "Remove DTD entities/external identifiers and parse untrusted XML with DTDs and external entities disabled.",
            )
        ]
    if "<!DOCTYPE" in content.upper() or len(content.encode("utf-8")) > 200_000:
        return []
    try:
        ET.fromstring(content)
    except ET.ParseError as exc:
        return [
            CodingFinding(
                "xml_not_well_formed",
                "major",
                f"The XML is not well-formed: {exc}.",
                "Fix the XML structure/escaping and validate it before returning the answer.",
            )
        ]
    return []


def assess_coding_answer(
    profile: CodingProfile,
    answer: str,
) -> tuple[tuple[CodingFinding, ...], tuple[str, ...]]:
    """Assess code embedded in a draft answer.

    Workspace summaries are not punished for omitting source code: when no
    code is present, existing execution/verification checks are authoritative.
    """

    if not profile.is_coding:
        return (), ()
    blocks = _extract_code_blocks(answer)
    if not blocks:
        return (), ()

    findings: list[CodingFinding] = []
    checks: list[str] = []

    def add_check(name: str) -> None:
        if name not in checks:
            checks.append(name)

    if profile.languages:
        labeled = {block.language for block in blocks if block.language}
        if labeled and not (labeled & set(profile.languages)):
            findings.append(
                CodingFinding(
                    "code_language_mismatch",
                    "major",
                    "The returned code block language does not match the requested language(s): "
                    + ", ".join(profile.language_labels)
                    + ".",
                    "Return the implementation in the requested language and label the fenced code block correctly.",
                )
            )
        else:
            add_check("code_language_match")

    saw_frontend_code = False
    saw_xml = False
    for block in blocks:
        findings.extend(_language_findings(block))
        if block.language == "xml" or (profile.languages == ("xml",) and block.content.lstrip().startswith("<")):
            saw_xml = True
            findings.extend(_xml_findings(block))
        if block.language == "html5":
            saw_frontend_code = True
            findings.extend(_html_findings(block.content))
        elif block.raw_language in {"jsx", "tsx"} or "className=" in block.content:
            saw_frontend_code = True
            findings.extend(_html_findings(block.content, react=True))
        if block.language == "css" and profile.is_frontend:
            saw_frontend_code = True
            if len(block.content) > 500 and not re.search(
                r"@media|clamp\(|minmax\(|auto-fit|auto-fill|\b\d+(?:\.\d+)?(?:vw|%)\b",
                block.content,
            ):
                findings.append(
                    CodingFinding(
                        "frontend_responsive_strategy",
                        "major",
                        "The stylesheet has no visible responsive or fluid-layout strategy.",
                        "Use mobile-first fluid layout, flexible Grid/Flexbox, clamp/minmax, and breakpoints where the design needs them.",
                    )
                )
            if ":focus-visible" not in block.content:
                findings.append(
                    CodingFinding(
                        "frontend_focus_style",
                        "minor",
                        "The stylesheet does not define a visible :focus-visible state.",
                        "Add a clear focus-visible treatment that is not removed by resets.",
                    )
                )

    codes = {finding.code for finding in findings}
    if not any(code.startswith(("unsafe_", "weak_")) or code in {"cpp_raw_owning_allocation"} for code in codes):
        add_check("code_language_safety")
    if saw_frontend_code and not any(code.startswith("frontend_") for code in codes):
        add_check("frontend_semantics_accessibility")
    if saw_xml and "xml_not_well_formed" not in codes and "xml_external_entity" not in codes:
        add_check("xml_well_formed")

    deduped: list[CodingFinding] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.code not in seen:
            seen.add(finding.code)
            deduped.append(finding)
    return tuple(deduped), tuple(checks)


def coding_capability_catalog() -> dict[str, Any]:
    """API-safe catalog of the built-in coding/frontend specializations."""

    return {
        "focuses": list(CODING_FOCUSES),
        "languages": [
            LANGUAGE_PLAYBOOKS[language_id].as_dict()
            for language_id in SUPPORTED_CODING_LANGUAGES
        ],
        "frontend_kinds": [
            "generic_frontend",
            "app_shell",
            "dashboard",
            "form",
            "landing",
            "commerce",
            "content",
            "game",
            "design_system",
        ],
        "design_goals": list(_FRONTEND_COMMON_GOALS),
    }


__all__ = [
    "CODING_FOCUSES",
    "LANGUAGE_PLAYBOOKS",
    "SUPPORTED_CODING_LANGUAGES",
    "CodingFinding",
    "CodingProfile",
    "LanguagePlaybook",
    "analyze_coding_request",
    "assess_coding_answer",
    "build_coding_contract",
    "coding_capability_catalog",
    "detect_coding_languages",
    "normalize_coding_focus",
]
