"""Frontend-design and polyglot coding-intelligence tests."""

from __future__ import annotations

import pytest

from nexus.domain.value_objects.coding_excellence import (
    analyze_coding_request,
    assess_coding_answer,
    build_coding_contract,
    coding_capability_catalog,
    detect_coding_languages,
    normalize_coding_focus,
)
from nexus.domain.value_objects.execution_quality import (
    assess_response_quality,
    build_execution_contract,
    build_execution_profile,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Make Nexus good at C.C++.Rust,Python,PHP,html5,XML and ruby", ("c", "cpp", "rust", "python", "php", "html5", "xml", "ruby")),
        ("Write a memory-safe parser in C17", ("c",)),
        ("Refactor this C++20 service", ("cpp",)),
        ("Build a Rust CLI with Cargo", ("rust",)),
        ("Create a PHP 8 form handler", ("php",)),
        ("Validate this XML against an XSD", ("xml",)),
        ("Write Ruby with RSpec", ("ruby",)),
    ],
)
def test_detects_requested_languages_without_swallowing_c_plus_plus(message, expected):
    detected = detect_coding_languages(message)

    for language in expected:
        assert language in detected
    if message.startswith("Refactor this C++"):
        assert detected == ("cpp",)


def test_language_detection_uses_file_extensions_but_not_ambiguous_headers():
    detected = detect_coding_languages(
        "Review these files",
        paths=["src/main.rs", "web/index.html", "include/api.h", "lib/tool.rb"],
    )

    assert detected == ("rust", "html5", "ruby")


def test_normalize_coding_focus_aliases():
    assert normalize_coding_focus("C++") == "cpp"
    assert normalize_coding_focus("front-end") == "frontend"
    assert normalize_coding_focus("HTML") == "html5"
    assert normalize_coding_focus("unknown") == "auto"


def test_frontend_dashboard_profile_has_design_system_goals_and_checks():
    profile = analyze_coding_request(
        "Build a clean responsive React analytics dashboard with filters and accessible forms",
        mode="coding",
        workstreams=("code_change",),
    )

    assert profile.is_coding
    assert profile.frontend_kind == "dashboard"
    assert "frontend_quality" in profile.verification_checks
    assert "npm_build" in profile.verification_checks
    assert any("320px" in goal for goal in profile.design_goals)
    assert any("loading" in goal for goal in profile.design_goals)
    assert any("responsive tables" in goal for goal in profile.design_goals)


def test_polyglot_profile_carries_modern_standards_and_verification():
    profile = analyze_coding_request(
        "Create a Rust service that reads XML and a Ruby test helper",
        workstreams=("code_change", "verification"),
    )
    contract = build_coding_contract(profile)

    assert profile.languages == ("rust", "xml", "ruby")
    assert "cargo_clippy" in profile.verification_checks
    assert "xml_validate" in profile.verification_checks
    assert "ruby_test" in profile.verification_checks
    assert "Rust 2021" in contract
    assert "XML 1.0" in contract
    assert len(contract) <= 620


def test_execution_profile_and_contract_include_coding_specialization():
    profile = build_execution_profile(
        "Build a clean HTML5 landing page with accessible signup form and verify it",
        mode="frontend",
    )
    contract = build_execution_contract(profile)
    data = profile.as_dict()

    assert profile.coding_profile is not None
    assert profile.coding_profile.frontend_kind in {"form", "landing"}
    assert profile.effective_effort in {"deep", "max"}
    assert data["coding_languages"] == ["html5"]
    assert data["coding"]["is_frontend"] is True
    assert "CODING EXCELLENCE" in contract
    assert "frontend_quality" in contract
    assert len(contract) <= 1400


def test_code_assessment_rejects_unsafe_language_patterns():
    cases = {
        "c": "```c\n#include <string.h>\nvoid f(char *d, char *s){ strcpy(d, s); }\n```",
        "cpp": "```cpp\nstruct Node {};\nNode* node = new Node();\n```",
        "rust": "```rust\npub fn read() -> String { std::fs::read_to_string(\"x\").unwrap() }\n```",
        "python": "```python\nvalue = eval(user_input)\n```",
        "php": "```php\n<?php echo $_GET['name'];\n```",
        "ruby": "```ruby\neval(user_input)\n```",
        "xml": "```xml\n<?xml version=\"1.0\"?><!DOCTYPE x [<!ENTITY xxe SYSTEM \"file:///etc/passwd\">]><x>&xxe;</x>\n```",
    }

    for language, answer in cases.items():
        profile = analyze_coding_request(f"Write {language} code", focus=language)
        findings, _checks = assess_coding_answer(profile, answer)
        assert findings, language
        assert any(finding.severity in {"critical", "major"} for finding in findings), language


def test_code_assessment_accepts_clean_semantic_html5():
    profile = analyze_coding_request("Create a clean HTML5 signup form", focus="frontend")
    answer = """```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign up</title>
</head>
<body>
  <main>
    <h1>Create account</h1>
    <form action="/signup" method="post">
      <label for="email">Email</label>
      <input id="email" name="email" type="email" autocomplete="email" required>
      <img src="/logo.svg" alt="Nexus logo">
      <button type="submit">Create account</button>
    </form>
  </main>
</body>
</html>
```"""

    findings, checks = assess_coding_answer(profile, answer)

    assert findings == ()
    assert "frontend_semantics_accessibility" in checks


def test_code_assessment_flags_inaccessible_html_and_malformed_xml():
    frontend = analyze_coding_request("Create an HTML5 page", focus="frontend")
    findings, _ = assess_coding_answer(
        frontend,
        "```html\n<html><body><div onclick=\"go()\">Go</div><img src=\"x.png\"><input placeholder=\"Email\"></body></html>\n```",
    )
    codes = {finding.code for finding in findings}
    assert "frontend_document_structure" in codes
    assert "frontend_image_alt" in codes
    assert "frontend_control_label" in codes
    assert "frontend_inline_handlers" in codes

    xml_profile = analyze_coding_request("Return XML", focus="xml")
    xml_findings, _ = assess_coding_answer(
        xml_profile,
        "```xml\n<root><child></root>\n```",
    )
    assert {finding.code for finding in xml_findings} == {"xml_not_well_formed"}


def test_execution_quality_gate_repairs_wrong_language_and_unsafe_code():
    profile = build_execution_profile("Write Rust code to read a file safely")
    report = assess_response_quality(
        profile,
        "Here is Rust code:\n\n```rust\npub fn read() -> String { std::fs::read_to_string(\"x\").unwrap() }\n```",
    )

    assert not report.passed
    assert "rust_unwrap_in_library_code" in {issue.code for issue in report.issues}

    wrong_profile = build_execution_profile("Write Python code to reverse a string")
    wrong_report = assess_response_quality(
        wrong_profile,
        "Here is the Python code:\n\n```javascript\nconst reverse = (value) => [...value].reverse().join('');\n```",
    )
    assert "code_language_mismatch" in {issue.code for issue in wrong_report.issues}


def test_coding_capability_catalog_covers_requested_stack():
    catalog = coding_capability_catalog()
    language_ids = {item["id"] for item in catalog["languages"]}

    assert {"c", "cpp", "rust", "python", "php", "html5", "xml", "ruby"} <= language_ids
    assert "frontend" in catalog["focuses"]
    assert "design_system" in catalog["frontend_kinds"]
