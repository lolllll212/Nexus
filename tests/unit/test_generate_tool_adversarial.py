"""Adversarial prompt-injection + code-validation tests for GenerateToolUseCase.

Guards:
- _validate_request: rejects tool names outside [a-z][a-z0-9_]{0,63} and
  descriptions >500 chars.
- _validate_code: requires a top-level def solve(...), rejects subprocess/socket/
  ctypes/eval/exec/compile/__import__ imports and dangerous Names.
- _build_prompt_safe: wraps user content in --- DELIMITER --- blocks so the model
  cannot be tricked into executing injected instructions.
"""

from __future__ import annotations

import pytest

from nexus.application.tools.generate_tool import (
    _validate_code,
    _validate_request,
    _build_prompt_safe,
    ToolSpecRequest,
    ToolGenerationError,
)


class TestValidateRequest:
    def test_name_too_short(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_request("", "desc")

    def test_name_too_long(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_request("a" * 65, "desc")

    def test_name_bad_chars(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_request("BadName", "desc")
        _validate_request("tool_1", "desc")  # okay

    def test_name_lowercase_ok(self) -> None:
        _validate_request("my_tool_v2", "desc")  # passes

    def test_description_too_long(self) -> None:
        with pytest.raises(ToolGenerationError):
            long_desc = "x" * 501  # type: ignore
            _validate_request("tool", long_desc)  # type: ignore

    def test_description_ok(self) -> None:
        _validate_request("tool", "short description")  # passes


class TestValidateCode:
    def test_valid_solve(self) -> None:
        _validate_code("def solve(input_data: dict) -> dict:\n    return {'answer': 42}")

    def test_no_solve(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("def foo():\n    pass")

    def test_syntax_error(self) -> None:
        # Missing colon or blatantly invalid syntax should raise
        with pytest.raises(ToolGenerationError):
            _validate_code("def solve  (input_data: dict)\n    return {}\n")

    def test_dangerous_import_subprocess(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("import subprocess\n")

    def test_dangerous_import_socket(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("import socket\n")

    def test_dangerous_eval_exec(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("x = eval('1+1')\n")

    def test_dangerous_compile(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("compile('1+1', '<string>', 'eval')\n")

    def test_dangerous_import_ctypes(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("import ctypes\n")

    def test_dangerous_name_eval(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("x = eval\n")

    def test_dangerous_name_exec(self) -> None:
        with pytest.raises(ToolGenerationError):
            _validate_code("x = exec\n")

    def test_allowed_constructs(self) -> None:
        # math, string ops, dict returns should be fine
        _validate_code("""def solve(x: int) -> int:
    return x + 1""")


class TestBuildPromptSafe:
    def test_basic_prompt(self) -> None:
        req = ToolSpecRequest(
            name="sort",
            description="sort a list",
            problem_statement="sort a list of numbers",
        )
        prompt = _build_prompt_safe(req)
        assert "--- PROBLEM ---" in prompt
        assert "--- NAME ---" in prompt
        assert "--- DESCRIPTION ---" in prompt
        assert "--- OUTPUT ---" in prompt
        assert "sort a list of numbers" in prompt

    def test_prompt_includes_requirements(self) -> None:
        req = ToolSpecRequest(
            name="calc",
            description="calculate",
            problem_statement="add two numbers",
            requirements=["math"],
        )
        prompt = _build_prompt_safe(req)
        assert "--- REQUIRED PACKAGES ---" in prompt
        assert "math" in prompt

    def test_prompt_includes_examples(self) -> None:
        req = ToolSpecRequest(
            name="fmt",
            description="format",
            problem_statement="format text",
            input_examples=[{"text": "hi"}],
        )
        prompt = _build_prompt_safe(req)
        # str() of a list of dicts uses single quotes in Python repr
        assert "{'text': 'hi'}" in prompt

    def test_prompt_includes_expected_outputs(self) -> None:
        req = ToolSpecRequest(
            name="hello",
            description="greet",
            problem_statement="say hello",
            expected_outputs=[{"result": "hello!"}],
        )
        prompt = _build_prompt_safe(req)
        # str() of a list of dicts uses single quotes in Python repr
        assert "{'result': 'hello!'}" in prompt
