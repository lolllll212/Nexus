"""
NVIDIA NIM (NVIDIA Inference Microservices) LLMProvider adapter.

Integrates with NVIDIA NIM APIs (cloud-hosted at https://integrate.api.nvidia.com/v1
or self-hosted on-premises NIM microservice containers). Implements the
hexagonal LLMProvider and StreamingLLMProvider ports.
"""

from __future__ import annotations

import ast
import asyncio
import csv
import io
import json
import logging
import re
from collections.abc import AsyncGenerator, Sequence

from nexus.domain.exceptions import LLMUnavailableError
from nexus.domain.ports.llm_provider import StreamingLLMProvider
from nexus.domain.value_objects.schema import JSONSchema
from nexus.domain.value_objects.solution_brief import (
    analyze_solution_request,
    build_practical_fallback,
    detect_read_only_tool_call,
    detect_repository_request,
)

logger = logging.getLogger("nexus.nim")

DEFAULT_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NIM_MODEL = "meta/llama-3.3-70b-instruct"

# Capability keys mirror the Claude-style capability panel in the web chat:
# reasoning (extended thinking), tool_use, code, vision, long_context,
# research (multi-source synthesis), streaming.
SUPPORTED_NIM_MODELS = [
    {
        "id": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "name": "Nemotron 3.5 Lightning 30B (fast)",
        "provider": "NVIDIA NIM",
        "description": "Fastest verified reasoning model - sub-second first token. Default.",
        "tags": ["default", "reasoning", "fast"],
        "context_window": 131072,
        "speed": "fastest",
        "best_for": "Everyday chat, quick questions, voice conversations",
        "capabilities": ["reasoning", "tool_use", "code", "long_context", "streaming"],
    },
    {
        "id": "nvidia/nemotron-3-ultra-550b-a55b",
        "name": "Nemotron 3 Ultra 550B",
        "provider": "NVIDIA NIM",
        "description": "Largest verified reasoning model - deep multi-step reasoning.",
        "tags": ["flagship", "reasoning"],
        "context_window": 262144,
        "speed": "deep",
        "best_for": "Hard reasoning, architecture, long research syntheses",
        "capabilities": ["reasoning", "tool_use", "code", "long_context", "research", "streaming"],
    },
    {
        "id": "meta/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B Instruct",
        "provider": "Meta / NVIDIA NIM",
        "description": "Workhorse open model - the container's classic cortex default.",
        "tags": ["general", "balanced"],
        "context_window": 131072,
        "speed": "balanced",
        "best_for": "General reasoning, writing, tool-driven workflows",
        "capabilities": ["tool_use", "code", "long_context", "research", "streaming"],
    },
    {
        "id": "openai/gpt-oss-20b",
        "name": "GPT-OSS 20B",
        "provider": "OpenAI / NVIDIA NIM",
        "description": "Open-weight general model - balanced speed and quality.",
        "tags": ["general"],
        "context_window": 131072,
        "speed": "balanced",
        "best_for": "General chat and quick drafting",
        "capabilities": ["reasoning", "tool_use", "code", "streaming"],
    },
    {
        "id": "stepfun-ai/step-5-preview",
        "name": "Step 5 Preview",
        "provider": "StepFun / NVIDIA NIM",
        "description": "Fast general assistant model.",
        "tags": ["general", "fast"],
        "context_window": 65536,
        "speed": "fastest",
        "best_for": "Snappy answers and short tasks",
        "capabilities": ["tool_use", "code", "streaming"],
    },
    {
        "id": "z-ai/glm-5.3",
        "name": "GLM 5.3",
        "provider": "Z.ai / NVIDIA NIM",
        "description": "Strong general model - slower responses, deep answers.",
        "tags": ["general", "deep"],
        "context_window": 131072,
        "speed": "deep",
        "best_for": "Deep, thorough written answers",
        "capabilities": ["reasoning", "tool_use", "code", "long_context", "research", "streaming"],
    },
    {
        "id": "meta/llama-3.2-90b-vision-instruct",
        "name": "Llama 3.2 90B Vision",
        "provider": "Meta / NVIDIA NIM",
        "description": "Multimodal vision-language model for image understanding.",
        "tags": ["vision", "multimodal"],
        "context_window": 131072,
        "speed": "balanced",
        "best_for": "Image Q&A, screenshots, charts and diagrams",
        "capabilities": ["vision", "tool_use", "long_context", "streaming"],
    },
]


class NvidiaNimProvider(StreamingLLMProvider):
    """
    Implements LLMProvider + StreamingLLMProvider targeting NVIDIA NIM.
    Compatible with both NVIDIA cloud API (https://integrate.api.nvidia.com/v1)
    and locally hosted NIM microservice containers.
    """

    supports_native_tool_calls = True

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_NIM_MODEL,
        temperature: float = 0.5,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._model = model or DEFAULT_NIM_MODEL
        self._temperature = temperature
        self._base_url = (base_url or DEFAULT_NIM_BASE_URL).rstrip("/")
        self._default_max_tokens = default_max_tokens

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._base_url = value.rstrip("/")

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key and self._api_key != "local-no-key")

    def set_api_key(self, api_key: str) -> None:
        self._api_key = (api_key or "").strip()

    def _client(self):
        from openai import AsyncOpenAI

        key = self._api_key if self.has_api_key else "nvapi-dummy"
        return AsyncOpenAI(api_key=key, base_url=self._base_url)

    @staticmethod
    def _message_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return ""

    @classmethod
    def _last_human_message(cls, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            text = cls._message_text(message.get("content")).strip()
            if not text:
                continue
            if text.startswith(("[OBSERVATION", "<tool_output")):
                continue
            return text
        return ""

    @classmethod
    def _latest_tool_observation(
        cls, messages: list[dict[str, str]], tool_name: str
    ) -> str:
        for message in reversed(messages):
            text = cls._message_text(message.get("content"))
            if f'<tool_output name="{tool_name}">' in text or (
                text.startswith("[OBSERVATION") and f"FROM {tool_name}" in text
            ):
                return text
        return ""

    @staticmethod
    def _observation_field(observation: str, field: str) -> str:
        match = re.search(rf"['\"]{re.escape(field)}['\"]\s*:\s*['\"]([^'\"]+)['\"]", observation)
        return match.group(1) if match else ""

    @classmethod
    def _human_messages(cls, messages: list[dict[str, str]]) -> list[str]:
        humans: list[str] = []
        for message in messages:
            if message.get("role") != "user":
                continue
            text = cls._message_text(message.get("content")).strip()
            if not text or text.startswith(("[OBSERVATION", "<tool_output")):
                continue
            humans.append(text)
        return humans

    @classmethod
    def _latest_any_tool_observation(
        cls, messages: list[dict[str, str]]
    ) -> tuple[str, str] | None:
        for message in reversed(messages):
            text = cls._message_text(message.get("content"))
            named = re.search(r'<tool_output name="([^"]+)">', text)
            if named:
                return named.group(1), text
            framed = re.search(r"\[OBSERVATION[^\]]*FROM\s+([A-Za-z0-9_.-]+)\]", text)
            if framed:
                return framed.group(1), text
        return None

    @classmethod
    def _assistant_tool_call(
        cls, messages: list[dict[str, str]], tool_id: str | None = None
    ) -> dict | None:
        for message in reversed(messages):
            if message.get("role") != "assistant":
                continue
            text = cls._message_text(message.get("content"))
            if "TOOL_CALL:" not in text:
                continue
            raw = text.split("TOOL_CALL:", 1)[1].strip()
            try:
                payload = json.loads(raw)
            except Exception:
                if tool_id is None or tool_id in text:
                    return {"tool_id": tool_id or "unknown", "params": {}}
                continue
            if isinstance(payload, dict) and (tool_id is None or payload.get("tool_id") == tool_id):
                return payload
        return None

    @staticmethod
    def _literal_closers(text: str) -> str | None:
        """Return brackets needed to close a Python literal, or None if invalid."""

        pairs = {"{": "}", "[": "]", "(": ")"}
        stack: list[str] = []
        quote: str | None = None
        triple = False
        escaped = False
        index = 0
        while index < len(text):
            char = text[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif triple and text.startswith(quote * 3, index):
                    quote = None
                    triple = False
                    index += 2
                elif not triple and char == quote:
                    quote = None
                index += 1
                continue
            if char in {"'", '"'}:
                if text.startswith(char * 3, index):
                    quote = char
                    triple = True
                    index += 3
                    continue
                quote = char
                triple = False
            elif char in pairs:
                stack.append(char)
            elif char in pairs.values():
                if not stack or pairs[stack[-1]] != char:
                    return None
                stack.pop()
            index += 1
        if quote is not None:
            return None
        return "".join(pairs[opener] for opener in reversed(stack))

    @staticmethod
    def _repair_truncated_literal(raw: str) -> object | None:
        """Best-effort parse of a context-truncated Python dict/list repr.

        The ReAct loop caps observations at a fixed character count, which can
        cut a rich tool result (for example project_scan) in the middle of a
        nested list. Retrying at earlier commas and closing still-open
        brackets recovers the complete leading fields without inventing data.
        """

        if not raw or raw[0] not in "{[(":
            return None
        comma_positions = [index for index, char in enumerate(raw) if char == ","]
        candidates = [len(raw), *reversed(comma_positions[-200:])]
        for end in candidates:
            candidate = raw[:end].rstrip().rstrip(",")
            closers = NvidiaNimProvider._literal_closers(candidate)
            if closers is None:
                continue
            try:
                return ast.literal_eval(candidate + closers)
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_observation_payload(observation: str) -> object:
        match = re.search(
            r"<tool_output[^>]*>\s*(.*?)\s*</tool_output>",
            observation,
            flags=re.DOTALL,
        )
        raw = match.group(1) if match else observation
        was_truncated = "...[truncated]" in raw
        raw = raw.replace(" ...[truncated]", "").strip()
        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(raw)
            except Exception:
                continue
            return value
        if was_truncated:
            repaired = NvidiaNimProvider._repair_truncated_literal(raw)
            if isinstance(repaired, dict):
                return {**repaired, "_partial_observation": True}
            if repaired is not None:
                return repaired
        return raw

    @staticmethod
    def _clip_text(value: object, limit: int = 3000) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n…[truncated]"

    def _repository_result_answer(self, observation: str, fallback_name: str) -> str:
        if "approval_required" in observation:
            return (
                "I can create the repository, but workspace-repo permission is not approved yet. "
                "Open **Code → Tools** in this chat window, approve workspace tools, then ask me again. "
                "I have not created any files yet."
            )
        if "'error'" in observation or '"error"' in observation:
            error = self._observation_field(observation, "error") or "the repository builder returned an error"
            return (
                f"I could not create the repository yet: {error}. "
                "Check that the target folder is new or empty, then try again; I will not overwrite unknown project files."
            )

        path = self._observation_field(observation, "path") or fallback_name
        template = self._observation_field(observation, "template") or "python-fastapi"
        name = self._observation_field(observation, "name") or path.rstrip("/").split("/")[-1]
        committed = bool(re.search(r"['\"]committed['\"]\s*:\s*True", observation))
        git_line = (
            "Git is initialized with an initial commit."
            if committed
            else "Git status is included in the tool result; check the reported note before committing."
        )
        run_commands = {
            "frontend-design-system": "npm install && npm run typecheck && npm run build && npm run dev",
            "html5-clean-ui": "npm test && python -m http.server 4173",
            "c-cmake": "make test && cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure",
            "cpp-cmake": "make test && cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure",
            "rust-cli": "cargo fmt --all -- --check && cargo clippy --all-targets -- -D warnings && cargo test",
            "python-fastapi": "python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]' && pytest && uvicorn app.main:app --reload",
            "react-vite": "npm install && npm run typecheck && npm run dev",
            "node-api": "npm install && npm test && npm run dev",
            "python-cli": "python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]' && pytest",
            "php-web": "composer validate && composer test && php -S 127.0.0.1:8000 -t public",
            "ruby-cli": f"bundle install && bundle exec rake test && ruby -Ilib exe/{name} Nexus",
            "xml-toolkit": "python -m pytest -q && python src/xml_toolkit.py data/catalog.xml",
            "static-site": "python -m http.server 4173",
            "empty": "git status",
        }.get(template, "Follow the commands in README.md")
        check_hint = {
            "frontend-design-system": "frontend_quality, npm_typecheck, npm_build",
            "html5-clean-ui": "frontend_quality",
            "c-cmake": "c_syntax, make_test, cmake_build, ctest",
            "cpp-cmake": "cpp_syntax, make_test, cmake_build, ctest",
            "rust-cli": "cargo_fmt, cargo_check, cargo_clippy, cargo_test",
            "php-web": "php_lint, composer_test, frontend_quality",
            "ruby-cli": "ruby_syntax, ruby_test",
            "xml-toolkit": "xml_validate, python_compile, pytest",
        }.get(template, "the checks recommended in README.md")
        return (
            f"Created **{name}** at `{path}` using the **{template}** template. {git_line}\n\n"
            f"**Run it**\n```bash\ncd {path}\n{run_commands}\n```\n\n"
            f"Recommended Nexus verification: {check_hint}.\n\n"
            "**Publish to GitHub when ready**\n"
            "```bash\ngit remote add origin https://github.com/<your-username>/"
            f"{name}.git\ngit push -u origin main\n```\n\n"
            "Tell me the first feature you want, and I can help implement it inside this new repository."
        )

    @staticmethod
    def _csv_summary(content: str) -> str:
        try:
            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames:
                return ""
            rows = list(reader)
        except Exception:
            return ""
        if not rows:
            return "The CSV has headers but no data rows in the observed output."

        lines = [
            f"I read the CSV structure: **{len(rows)} rows** and columns **{', '.join(reader.fieldnames)}**.",
            "",
            "| Column | Numeric total | Average |",
            "|---|---:|---:|",
        ]
        numeric_found = False
        for column in reader.fieldnames:
            numbers: list[float] = []
            for row in rows:
                value = str(row.get(column, "")).strip().replace(",", "").replace("₹", "")
                try:
                    numbers.append(float(value))
                except ValueError:
                    continue
            if len(numbers) < max(1, len(rows) // 2):
                continue
            numeric_found = True
            total = sum(numbers)
            average = total / len(numbers)
            lines.append(f"| {column} | {total:,.2f} | {average:,.2f} |")
        if not numeric_found:
            lines = lines[:2] + ["No mostly numeric columns were visible, so I have not invented totals."]
        lines.append("")
        lines.append("These figures are calculated only from the rows visible in the tool observation.")
        return "\n".join(lines)

    def _read_file_result_answer(self, payload: dict, path: str, user_message: str) -> str:
        content = str(payload.get("content") or "")
        if not content:
            return f"I read `{path}`, but the file appears empty in the tool result."

        lower_path = path.lower()
        if lower_path.endswith(".csv"):
            summary = self._csv_summary(content)
            if summary:
                return summary

        wants_explanation = bool(
            re.search(r"\b(explain|summarize|review|analy[sz]e|what does)\b", user_message, re.I)
        )
        structure: list[str] = []
        if lower_path.endswith(".md"):
            headings = re.findall(r"^#{1,3}\s+(.+)$", content, flags=re.MULTILINE)
            if headings:
                structure = [f"- {heading.strip()}" for heading in headings[:12]]
        elif lower_path.endswith(".py"):
            definitions = re.findall(r"^(?:class|def|async def)\s+([A-Za-z_]\w*)", content, flags=re.M)
            if definitions:
                structure = [f"- `{name}`" for name in definitions[:15]]

        extension = lower_path.rsplit(".", 1)[-1] if "." in lower_path else ""
        language = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "tsx",
            "json": "json",
            "md": "markdown",
            "csv": "csv",
            "html": "html",
            "css": "css",
        }.get(extension, "text")
        excerpt = self._clip_text(content, 3000)
        if wants_explanation and structure:
            return (
                f"I read `{path}`. Its visible structure is:\n\n"
                + "\n".join(structure)
                + f"\n\nHere is the relevant beginning so the explanation stays grounded in the actual file:\n\n```{language}\n{excerpt}\n```"
            )
        return f"Here is `{path}`:\n\n```{language}\n{excerpt}\n```"

    def _deterministic_tool_result_answer(
        self,
        tool_id: str,
        observation: str,
        user_message: str,
        history: Sequence[str] = (),
    ) -> str:
        payload = self._parse_observation_payload(observation)
        call = detect_read_only_tool_call(user_message, history=history)
        params = call.params() if call and call.tool_id == tool_id else {}

        structured_error_tools = {"json_query", "web_search", "web_fetch", "http_request"}
        if isinstance(payload, dict) and payload.get("error") and tool_id not in structured_error_tools:
            error = self._clip_text(payload.get("error"), 500)
            return (
                f"I tried `{tool_id}`, but it could not complete: {error}. "
                "No files were changed. Check the exact path/target and try again."
            )
        if isinstance(payload, str) and ("failed:" in payload.lower() or "approval_required" in payload):
            return (
                f"I tried `{tool_id}`, but it could not complete: {self._clip_text(payload, 500)}. "
                "No files were changed."
            )
        if not isinstance(payload, dict):
            return f"`{tool_id}` returned:\n\n{self._clip_text(payload, 3000)}"

        if tool_id == "calculator":
            expression = payload.get("expression") or params.get("expression") or "the expression"
            result = payload.get("result")
            if re.search(r"\bjson\b", user_message, re.IGNORECASE):
                if isinstance(result, float) and result.is_integer():
                    result = int(result)
                body: dict[str, object] = {}
                if '"expression"' in user_message or "'expression'" in user_message:
                    body["expression"] = expression
                body["result"] = result
                return json.dumps(body)
            return f"`{expression}` = **{result}**"

        if tool_id == "current_datetime":
            timezone = payload.get("timezone") or "UTC"
            return (
                f"The current date/time in **{timezone}** is **{payload.get('datetime')}** "
                f"(ISO: `{payload.get('iso')}`)."
            )

        if tool_id == "hash_text":
            return f"The hash is:\n\n`{payload.get('hash')}`"

        if tool_id == "system_info":
            info = payload.get("info") if isinstance(payload.get("info"), dict) else payload
            rows = "\n".join(f"- **{key}:** {value}" for key, value in info.items())
            return f"System information:\n\n{rows}"

        if tool_id == "list_directory":
            entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
            path = str(payload.get("path") or params.get("path") or ".")
            if not entries:
                return f"`{path}` is empty according to the directory tool."
            rendered = []
            for entry in entries[:50]:
                if isinstance(entry, dict):
                    name = entry.get("name", "?")
                    marker = "/" if entry.get("type") == "dir" else ""
                    size = f" ({entry.get('size')} bytes)" if entry.get("type") == "file" else ""
                    rendered.append(f"- `{name}{marker}`{size}")
                else:
                    rendered.append(f"- `{entry}`")
            total = payload.get("total_entries", len(entries))
            extra = f"\n\nShowing {len(rendered)} of {total} entries." if int(total or 0) > len(rendered) else ""
            return f"Contents of `{path}` ({total} entries):\n\n" + "\n".join(rendered) + extra

        if tool_id == "read_file":
            answer = self._read_file_result_answer(
                payload,
                str(payload.get("path") or params.get("path") or "the requested file"),
                user_message,
            )
            if payload.get("truncated"):
                line_range = payload.get("line_range") if isinstance(payload.get("line_range"), list) else []
                range_text = f" Lines shown: {line_range[0]}–{line_range[1]}." if len(line_range) == 2 else ""
                answer += f"\n\nNote: this is a bounded excerpt of a larger file.{range_text}"
            return answer

        if tool_id == "grep":
            matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
            if not matches:
                return f"I searched `{params.get('path', '.')}` and found no matches for that pattern."
            lines = []
            for match in matches[:20]:
                if isinstance(match, dict):
                    lines.append(
                        f"- `{match.get('file')}:{match.get('line')}` — {self._clip_text(match.get('text'), 220)}"
                    )
                else:
                    lines.append(f"- {self._clip_text(match, 220)}")
            extra = f"\n\n…and {len(matches) - 20} more matches." if len(matches) > 20 else ""
            return f"Found **{len(matches)}** matching location(s):\n\n" + "\n".join(lines) + extra

        if tool_id == "git_info":
            changed = payload.get("changed_files") if isinstance(payload.get("changed_files"), list) else []
            if payload.get("is_clean"):
                status_text = "clean (no uncommitted changes shown)"
            else:
                status_text = (
                    f"{payload.get('changed_count', len(changed))} changed file(s): "
                    f"{payload.get('staged_count', 0)} staged, "
                    f"{payload.get('unstaged_count', 0)} unstaged, "
                    f"{payload.get('untracked_count', 0)} untracked"
                )
            changed_text = ""
            if changed:
                changed_text = "\n" + "\n".join(f"  - `{item}`" for item in changed[:20])
            upstream = f"\n- **Upstream:** `{payload.get('upstream')}`" if payload.get("upstream") else ""
            return (
                f"Git status for `{payload.get('path', params.get('repo_path', '.'))}`:\n\n"
                f"- **Branch:** `{payload.get('branch', 'unknown')}`{upstream}\n"
                f"- **Last commit:** {payload.get('last_commit', 'unknown')}\n"
                f"- **Working tree:** {status_text}{changed_text}"
            )

        if tool_id == "project_scan":
            partial = bool(payload.get("_partial_observation"))
            missing = "not visible in the truncated tool excerpt" if partial else "none detected"
            languages = payload.get("languages") if isinstance(payload.get("languages"), list) else []
            language_text = ", ".join(
                f"{item.get('language')} ({item.get('files')} files)"
                for item in languages[:6]
                if isinstance(item, dict)
            ) or missing
            manifests = payload.get("manifests") if isinstance(payload.get("manifests"), list) else []
            manifest_text = ", ".join(
                f"`{item.get('path')}`" for item in manifests[:10] if isinstance(item, dict)
            ) or missing
            frameworks = ", ".join(str(item) for item in payload.get("frameworks", [])[:10]) or (
                missing if partial else "none confidently detected"
            )
            entrypoints = payload.get("entrypoints") if isinstance(payload.get("entrypoints"), list) else []
            entrypoint_text = ", ".join(f"`{item}`" for item in entrypoints[:10]) or (
                missing if partial else "none obvious"
            )
            commands = payload.get("suggested_commands") if isinstance(payload.get("suggested_commands"), list) else []
            command_text = "\n".join(f"- `{command}`" for command in commands[:8]) or (
                f"- {missing}" if partial else "- No standard command detected"
            )
            recommended_checks = (
                payload.get("recommended_checks") if isinstance(payload.get("recommended_checks"), list) else []
            )
            checks_text = ", ".join(f"`{item}`" for item in recommended_checks[:10]) or missing
            frontend = payload.get("frontend") if isinstance(payload.get("frontend"), dict) else {}
            frontend_text = (
                "detected ("
                + ", ".join(
                    part
                    for part in [
                        ", ".join(str(item) for item in frontend.get("frameworks", [])[:5]),
                        f"{frontend.get('html_files', 0)} HTML",
                        f"{frontend.get('css_files', 0)} CSS",
                        f"{frontend.get('component_files', 0)} components",
                    ]
                    if part
                )
                + ")"
                if frontend.get("detected")
                else missing
                if partial and not frontend
                else "not detected"
            )
            git = payload.get("git") if isinstance(payload.get("git"), dict) else {}
            git_text = (
                f"branch `{git.get('branch') or 'detached/unknown'}`, "
                f"{git.get('changed_files', 0)} changed file(s)"
                if git.get("is_repo")
                else missing
                if partial and not git
                else "not a Git repository at this path"
            )
            return (
                f"I scanned `{payload.get('path', params.get('path', '.'))}` in {payload.get('duration_ms', '?')} ms.\n\n"
                f"- **Files:** {payload.get('files', 0)} across {payload.get('directories', 0)} directories\n"
                f"- **Languages:** {language_text}\n"
                f"- **Manifests:** {manifest_text}\n"
                f"- **Frameworks:** {frameworks}\n"
                f"- **Entrypoints:** {entrypoint_text}\n"
                f"- **Tests:** {payload.get('test_files', 0)} test file(s)\n"
                f"- **Frontend:** {frontend_text}\n"
                f"- **Recommended checks:** {checks_text}\n"
                f"- **Git:** {git_text}\n\n"
                f"Suggested commands:\n{command_text}"
            )

        if tool_id == "find_files":
            files = payload.get("files") if isinstance(payload.get("files"), list) else []
            if not files:
                return f"I found no files matching `{payload.get('pattern', params.get('pattern', '*'))}` under `{payload.get('path', '.')}`."
            rendered = "\n".join(
                f"- `{item.get('path')}` ({item.get('bytes', 0)} bytes)"
                for item in files[:40]
                if isinstance(item, dict)
            )
            return f"Found **{payload.get('total_matches', len(files))}** matching file(s):\n\n{rendered}"

        if tool_id == "directory_tree":
            return (
                f"Directory tree for `{payload.get('path', params.get('path', '.'))}`:\n\n"
                f"```text\n{self._clip_text(payload.get('tree'), 6000)}\n```"
            )

        if tool_id == "read_files":
            files = payload.get("files") if isinstance(payload.get("files"), list) else []
            sections: list[str] = []
            for item in files[:10]:
                if not isinstance(item, dict):
                    continue
                if item.get("error"):
                    sections.append(f"### `{item.get('path')}`\n\nCould not read: {item.get('error')}")
                else:
                    sections.append(
                        f"### `{item.get('path')}` ({item.get('lines', '?')} lines)\n\n"
                        f"```text\n{self._clip_text(item.get('content'), 1800)}\n```"
                    )
            return "I read the requested file(s):\n\n" + "\n\n".join(sections)

        if tool_id == "file_outline":
            symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
            imports = payload.get("imports") if isinstance(payload.get("imports"), list) else []
            symbol_text = "\n".join(
                f"- `{item.get('qualified_name') or item.get('name')}` — {item.get('kind')} (line {item.get('line')})"
                for item in symbols[:60]
                if isinstance(item, dict)
            ) or "- No symbols detected"
            import_text = ", ".join(
                f"`{item.get('name')}`" for item in imports[:30] if isinstance(item, dict)
            ) or "none"
            return (
                f"Outline of `{payload.get('path', params.get('path'))}` "
                f"({payload.get('language')}, {payload.get('lines', '?')} lines):\n\n"
                f"{symbol_text}\n\nImports: {import_text}"
            )

        if tool_id == "find_symbol":
            definitions = payload.get("definitions") if isinstance(payload.get("definitions"), list) else []
            references = payload.get("references") if isinstance(payload.get("references"), list) else []

            def render(items: list[object]) -> str:
                return "\n".join(
                    f"- `{item.get('file')}:{item.get('line')}` — {self._clip_text(item.get('text'), 220)}"
                    for item in items[:30]
                    if isinstance(item, dict)
                ) or "- None found"

            return (
                f"Symbol `{payload.get('symbol', params.get('symbol'))}`:\n\n"
                f"**Definitions ({len(definitions)}):**\n{render(definitions)}\n\n"
                f"**References/imports ({len(references)}):**\n{render(references)}"
            )

        if tool_id == "code_diagnostics":
            diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
            languages = payload.get("languages") if isinstance(payload.get("languages"), list) else []
            language_text = ", ".join(
                f"{item.get('language')} ({item.get('files')})"
                for item in languages[:8]
                if isinstance(item, dict)
            )
            native = payload.get("native_checks") if isinstance(payload.get("native_checks"), list) else []
            skipped = (
                payload.get("native_checks_skipped")
                if isinstance(payload.get("native_checks_skipped"), list)
                else []
            )
            coverage_parts = []
            if language_text:
                coverage_parts.append(f"Languages: {language_text}")
            if native:
                coverage_parts.append("Native syntax: " + ", ".join(str(item) for item in native))
            if skipped:
                coverage_parts.append("Skipped: " + "; ".join(str(item) for item in skipped[:5]))
            coverage = ("\n\n" + "\n".join(f"- {part}" for part in coverage_parts)) if coverage_parts else ""
            if payload.get("clean") and not diagnostics:
                return (
                    f"No syntax or frontend/XML quality errors found in {payload.get('files_scanned', 0)} checked file(s) "
                    f"under `{payload.get('path', params.get('path', '.'))}`.{coverage}"
                )
            rendered = "\n".join(
                f"- `{item.get('file')}:{item.get('line')}` [{item.get('severity')}/{item.get('source')}] "
                f"{self._clip_text(item.get('message'), 300)}"
                for item in diagnostics[:40]
                if isinstance(item, dict)
            )
            return (
                f"Diagnostics: **{payload.get('errors', 0)} error(s)**, "
                f"{payload.get('warnings', 0)} warning(s), {payload.get('info', 0)} info item(s).{coverage}\n\n{rendered}"
            )

        if tool_id == "git_diff":
            changed = payload.get("changed_files") if isinstance(payload.get("changed_files"), list) else []
            if payload.get("clean"):
                return f"The Git working tree is clean on branch `{payload.get('branch') or 'unknown'}`."
            changed_text = "\n".join(
                f"- `{item.get('status')}` `{item.get('path')}`"
                for item in changed[:50]
                if isinstance(item, dict)
            )
            return (
                f"Git changes on branch `{payload.get('branch') or 'unknown'}`:\n\n{changed_text}\n\n"
                f"```diff\n{self._clip_text(payload.get('diff'), 5000)}\n```"
            )

        if tool_id == "project_checks":
            checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
            lines: list[str] = []
            for item in checks:
                if not isinstance(item, dict):
                    continue
                status = (
                    "passed"
                    if item.get("passed")
                    else "not run (toolchain missing)"
                    if item.get("tool_available") is False
                    else "failed"
                )
                output = item.get("output") or "\n".join(
                    part for part in [str(item.get("stdout") or ""), str(item.get("stderr") or "")] if part
                )
                lines.append(
                    f"- **{item.get('name')}**: {status}"
                    + (f"\n  - {self._clip_text(output, 600)}" if output else "")
                )
            overall = "All project checks passed." if payload.get("passed") else "One or more project checks failed."
            return f"{overall}\n\n" + "\n".join(lines)

        if tool_id == "pytest_runner":
            summary = payload.get("summary") or (
                f"{payload.get('passed', 0)} passed, {payload.get('failed', 0)} failed, "
                f"{payload.get('skipped', 0)} skipped"
            )
            failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
            result = f"Test run finished: **{summary}**."
            if failures:
                rendered_failures = "\n".join(
                    f"- {self._clip_text(failure, 500)}" for failure in failures[:5]
                )
                result += f"\n\nFailures:\n{rendered_failures}"
            elif payload.get("output"):
                result += f"\n\n```text\n{self._clip_text(payload.get('output'), 1800)}\n```"
            return result

        if tool_id == "web_search":
            query = payload.get("query") or params.get("query") or user_message
            results = payload.get("results") if isinstance(payload.get("results"), list) else []
            if payload.get("error"):
                return (
                    f"I searched for “{self._clip_text(query, 200)}”, but web search failed: "
                    f"{self._clip_text(payload.get('error'), 300)}. I have not invented replacement findings."
                )
            if not results:
                return (
                    f"I searched for “{self._clip_text(query, 200)}”, but the search provider returned no results. "
                    "Try a more specific query or fetch a known source URL directly."
                )
            lines: list[str] = []
            for index, item in enumerate(results[:10], start=1):
                if isinstance(item, dict):
                    title = self._clip_text(item.get("title") or "Untitled result", 180)
                    url = str(item.get("url") or "").strip()
                    snippet = self._clip_text(item.get("snippet"), 320)
                    heading = f"{index}. [{title}]({url})" if url else f"{index}. {title}"
                    lines.append(heading + (f"\n   {snippet}" if snippet else ""))
                else:
                    lines.append(f"{index}. {self._clip_text(item, 320)}")
            return f"Web results for “{self._clip_text(query, 200)}”:\n\n" + "\n".join(lines)

        if tool_id == "web_fetch":
            final_url = payload.get("final_url") or payload.get("url") or params.get("url") or ""
            status = payload.get("status", "?")
            if payload.get("error"):
                return (
                    f"I could not fetch `{final_url}` successfully: "
                    f"{self._clip_text(payload.get('error'), 400)}"
                )
            content = str(payload.get("content") or "").strip()
            if not content:
                return f"I fetched `{final_url}` (HTTP {status}), but it contained no readable text."
            title = self._clip_text(payload.get("title"), 200)
            intro = f"I fetched **{title}**" if title else "I fetched the page"
            links = payload.get("links") if isinstance(payload.get("links"), list) else []
            link_text = ""
            if links:
                rendered_links = "\n".join(
                    f"- [{self._clip_text(item.get('title') or item.get('url'), 120)}]({item.get('url')})"
                    for item in links[:5]
                    if isinstance(item, dict) and item.get("url")
                )
                if rendered_links:
                    link_text = f"\n\nUseful links on the page:\n{rendered_links}"
            note = " The page text was truncated to the tool limit." if payload.get("truncated") else ""
            return (
                f"{intro} from `{final_url}` (HTTP {status}).{note}\n\n"
                f"{self._clip_text(content, 3500)}{link_text}"
            )

        if tool_id == "http_request":
            status = payload.get("status", 0)
            target = payload.get("final_url") or payload.get("url") or params.get("url") or ""
            method = payload.get("method") or params.get("method") or "GET"
            if payload.get("error") and int(status or 0) == 0:
                return f"The {method} request to `{target}` failed: {self._clip_text(payload.get('error'), 400)}"
            if "json" in payload:
                body_text = json.dumps(payload.get("json"), indent=2, default=str)
                language = "json"
            else:
                body_text = str(payload.get("body") or "")
                language = "text"
            note = " The response body was truncated." if payload.get("truncated") else ""
            return (
                f"`{method} {target}` returned **HTTP {status}**.{note}\n\n"
                f"```{language}\n{self._clip_text(body_text, 3000)}\n```"
            )

        if tool_id == "code_search_semantic":
            results = payload.get("results") if isinstance(payload.get("results"), list) else []
            query = payload.get("query") or params.get("query") or ""
            if not results:
                return (
                    f"I found no code matches for “{self._clip_text(query, 200)}” after scanning "
                    f"{payload.get('files_scanned', 0)} file(s)."
                )
            lines = []
            for item in results[:10]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"- `{item.get('file')}:{item.get('line')}` "
                    f"(score {item.get('score')}) — {self._clip_text(item.get('snippet'), 260)}"
                )
            return (
                f"Semantic code search found **{payload.get('total_matches', len(results))}** match(es) "
                f"across {payload.get('files_scanned', '?')} file(s) using `{payload.get('mode', 'tfidf')}`:\n\n"
                + "\n".join(lines)
            )

        if tool_id == "dependency_audit":
            undeclared = payload.get("undeclared") if isinstance(payload.get("undeclared"), list) else []
            unused = payload.get("unused_declared") if isinstance(payload.get("unused_declared"), list) else []
            errors = payload.get("parse_errors") if isinstance(payload.get("parse_errors"), list) else []
            lines = [
                f"I audited {payload.get('files_scanned', 0)} Python file(s): "
                f"{len(payload.get('imported') or [])} external package(s) imported and "
                f"{len(payload.get('declared') or [])} declared."
            ]
            if undeclared:
                lines.append("\n**Undeclared imports:** " + ", ".join(f"`{item}`" for item in undeclared[:30]))
            else:
                lines.append("\nNo undeclared external imports were found.")
            if unused:
                lines.append("**Declared but not imported in the scanned tree:** " + ", ".join(f"`{item}`" for item in unused[:30]))
            if errors:
                lines.append("\n**Parse/read issues:**\n" + "\n".join(f"- {self._clip_text(item, 260)}" for item in errors[:10]))
            return "\n".join(lines)

        if tool_id == "secret_scan":
            findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
            if payload.get("clean") or not findings:
                return (
                    f"I scanned {payload.get('files_scanned', 0)} text file(s) under "
                    f"`{payload.get('path', params.get('path', '.'))}` and found no likely committed secrets. "
                    "Denylisted credential files were skipped by policy, so still keep real credentials out of the repo."
                )
            lines = [
                f"I found **{len(findings)}** likely secret finding(s) with **{payload.get('risk_level', 'unknown')}** risk "
                f"across {payload.get('files_with_findings', '?')} file(s). Values below are redacted:"
            ]
            for item in findings[:12]:
                if isinstance(item, dict):
                    lines.append(
                        f"- `{item.get('file')}:{item.get('line')}` — {item.get('kind')} "
                        f"({item.get('severity')}): `{self._clip_text(item.get('redacted_preview'), 90)}`"
                    )
            if len(findings) > 12:
                lines.append(f"\n…and {len(findings) - 12} more finding(s).")
            lines.append(
                "\nRemove these values from source, rotate any real credential, and load secrets from environment variables or a secret manager."
            )
            return "\n".join(lines)

        if tool_id == "release_readiness":
            blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
            warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
            actions = (
                payload.get("recommended_next_actions")
                if isinstance(payload.get("recommended_next_actions"), list)
                else []
            )
            diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
            secrets = payload.get("secrets") if isinstance(payload.get("secrets"), dict) else {}
            git = payload.get("git") if isinstance(payload.get("git"), dict) else {}
            dependencies = payload.get("dependencies") if isinstance(payload.get("dependencies"), dict) else {}
            lines = [
                str(payload.get("summary") or f"Release readiness: {payload.get('status', 'unknown')}; score {payload.get('score', '?')}/100.")
            ]
            if blockers:
                lines.append("\n**Blockers:**")
                for item in blockers[:10]:
                    if isinstance(item, dict):
                        message = self._clip_text(item.get("message"), 320).rstrip(".")
                        count = f" ({item.get('count')})" if item.get("count") else ""
                        lines.append(f"- {message}{count}.")
            else:
                lines.append("\n**Blockers:** none found by this gate.")
            if warnings:
                lines.append("\n**Warnings:**")
                for item in warnings[:10]:
                    if isinstance(item, dict):
                        message = self._clip_text(item.get("message"), 320).rstrip(".")
                        count = f" ({item.get('count')})" if item.get("count") else ""
                        lines.append(f"- {message}{count}.")
            evidence: list[str] = []
            if diagnostics:
                evidence.append(
                    f"diagnostics: {diagnostics.get('errors', 0)} error(s) across {diagnostics.get('files_scanned', 0)} scanned file(s)"
                )
            if secrets:
                evidence.append(f"secret scan risk: {secrets.get('risk_level', 'unknown')}")
            if git:
                if git.get("is_git_repository"):
                    evidence.append(
                        f"Git: branch `{git.get('branch', 'unknown')}`, {git.get('changed_count', 0)} uncommitted change(s)"
                    )
                else:
                    evidence.append("Git: not a repository")
            if dependencies:
                evidence.append(
                    f"dependencies: {len(dependencies.get('undeclared') or [])} undeclared package(s)"
                )
            if payload.get("checks_run"):
                evidence.append(f"project checks passed: {bool(payload.get('checks_passed'))}")
            else:
                evidence.append("project checks were not run in this readiness pass")
            if evidence:
                lines.append("\n**Evidence:** " + "; ".join(evidence) + ".")
            if actions:
                lines.append("\n**Next actions:**\n" + "\n".join(f"- {self._clip_text(action, 300)}" for action in actions[:6]))
            return "\n".join(lines)

        if tool_id == "changelog_draft":
            markdown = str(payload.get("markdown") or "").strip()
            if markdown:
                return self._clip_text(markdown, 6500)
            commits = payload.get("commits") if isinstance(payload.get("commits"), list) else []
            if commits:
                order = [
                    "Added",
                    "Fixed",
                    "Changed",
                    "Security",
                    "Performance",
                    "Documentation",
                    "Tests",
                    "Maintenance",
                    "Other",
                ]
                grouped: dict[str, list[dict]] = {}
                for item in commits:
                    if isinstance(item, dict):
                        grouped.setdefault(str(item.get("category") or "Other"), []).append(item)
                lines = [
                    "# Changelog draft",
                    "",
                    f"Range: `{payload.get('range', params.get('repo_path', '.'))}`",
                    f"Commits: {payload.get('commit_count', len(commits))}",
                    "",
                ]
                for section in order:
                    items = grouped.get(section) or []
                    if not items:
                        continue
                    lines.append(f"## {section}")
                    lines.append("")
                    for item in items[:30]:
                        prefix = "**Breaking:** " if item.get("breaking") else ""
                        label = item.get("display") or item.get("subject") or "commit"
                        lines.append(f"- {prefix}{label} (`{item.get('hash')}`)")
                    lines.append("")
                if payload.get("_partial_observation"):
                    lines.append("Note: this draft was reconstructed from the bounded tool observation; use the Tools panel for the full Markdown.")
                return self._clip_text("\n".join(lines).strip(), 6500)
            return (
                f"I drafted a changelog for `{payload.get('range', params.get('repo_path', '.'))}`, "
                f"but it contained {payload.get('commit_count', 0)} commit(s)."
            )

        if tool_id == "json_query":
            key_path = payload.get("key_path") or params.get("key_path") or ""
            if not payload.get("found", True):
                default_note = ""
                if payload.get("result") is not None:
                    default_note = f" The configured default is `{self._clip_text(json.dumps(payload.get('result'), default=str), 300)}`."
                return (
                    f"I could not find `{key_path}` in the JSON: "
                    f"{self._clip_text(payload.get('error'), 300)}.{default_note}"
                )
            result = payload.get("result")
            rendered = json.dumps(result, indent=2, default=str) if isinstance(result, dict | list) else str(result)
            return f"`{key_path}` is:\n\n```json\n{self._clip_text(rendered, 3000)}\n```"

        return "Tool result:\n\n```json\n" + self._clip_text(
            json.dumps(payload, indent=2, default=str), 3000
        ) + "\n```"

    def _simulated_response(self, messages: list[dict[str, str]]) -> str:
        """Realistic fallback when no NVIDIA API key is configured or offline."""
        human_messages = self._human_messages(messages)
        last_msg = human_messages[-1] if human_messages else self._last_human_message(messages)
        prior_messages = tuple(human_messages[:-1][-6:])
        lower = last_msg.lower()
        in_react = any(
            "FINAL ANSWER" in self._message_text(m.get("content")) for m in messages
        )

        repository = detect_repository_request(last_msg)
        if prior_messages:
            inherited = analyze_solution_request(last_msg, history=prior_messages)
            if inherited.repository is not None and (
                repository is None
                or inherited.context_used
                or inherited.readiness == "ready_with_context"
            ):
                if repository is not None or inherited.readiness == "ready_with_context":
                    repository = inherited.repository

        if in_react and repository is not None:
            observation = self._latest_tool_observation(messages, "create_repository")
            if observation:
                return "FINAL ANSWER: " + self._repository_result_answer(
                    observation, repository.name
                )
            if self._assistant_tool_call(messages, "create_repository") is None:
                payload = {"tool_id": "create_repository", "params": repository.tool_params()}
                return "TOOL_CALL: " + json.dumps(payload)

        if in_react:
            latest = self._latest_any_tool_observation(messages)
            if latest is not None:
                tool_id, observation = latest
                deterministic_tools = {
                    "calculator",
                    "changelog_draft",
                    "code_diagnostics",
                    "code_search_semantic",
                    "current_datetime",
                    "dependency_audit",
                    "directory_tree",
                    "file_outline",
                    "find_files",
                    "find_symbol",
                    "git_diff",
                    "git_info",
                    "grep",
                    "hash_text",
                    "http_request",
                    "json_query",
                    "list_directory",
                    "project_checks",
                    "project_scan",
                    "pytest_runner",
                    "read_file",
                    "read_files",
                    "release_readiness",
                    "secret_scan",
                    "system_info",
                    "web_fetch",
                    "web_search",
                }
                if tool_id in deterministic_tools:
                    return "FINAL ANSWER: " + self._deterministic_tool_result_answer(
                        tool_id,
                        observation,
                        last_msg,
                        history=prior_messages,
                    )

            deterministic_call = detect_read_only_tool_call(
                last_msg,
                history=prior_messages,
            )
            if deterministic_call is not None and self._assistant_tool_call(
                messages, deterministic_call.tool_id
            ) is None:
                payload = {
                    "tool_id": deterministic_call.tool_id,
                    "params": deterministic_call.params(),
                }
                return "TOOL_CALL: " + json.dumps(payload)

        answer = self._simulated_answer(last_msg, lower, history=prior_messages)
        # The cortex ReAct prompt demands a FINAL ANSWER envelope; honor it in
        # simulation too, otherwise the loop nudges until its iteration cap.
        if in_react:
            return f"FINAL ANSWER: {answer}"
        return answer

    def _simulated_answer(
        self,
        last_msg: str,
        lower: str,
        history: Sequence[str] = (),
    ) -> str:
        clean = " ".join((last_msg or "").strip().split())
        meta = next(
            (entry for entry in SUPPORTED_NIM_MODELS if entry.get("id") == self._model),
            {},
        )
        label = str(meta.get("name") or self._model)

        if not clean:
            return "I am ready. Ask for a practical plan, a fix, a decision, or say “create a repo for …”."

        secret_exfiltration = re.search(
            r"\b(?:read|show|print|dump|cat|reveal|expose|exfiltrate|steal|leak)\b.{0,48}"
            r"(?:\.env\b|credentials?\b|private keys?\b|id_rsa\b|id_ed25519\b|/etc/shadow\b|"
            r"api keys?\b|passwords?\b|secrets?\b|169\.254\.169\.254|instance credentials?)|"
            r"\b(?:show|reveal|give me)\b.{0,24}\b(?:secrets?|passwords?|api keys?)\b",
            clean,
            re.IGNORECASE | re.DOTALL,
        )
        if secret_exfiltration:
            return (
                "I can’t read or reveal credentials, private keys, passwords, or other secrets. "
                "I can still help you document required variable names with values redacted, rotate a compromised key, "
                "or troubleshoot configuration without printing the secret values."
            )

        greeting = re.match(
            r"^(hi|hii+|hello|hey|namaste|good (morning|afternoon|evening))\b",
            clean,
            re.IGNORECASE,
        )
        identity = any(
            phrase in lower
            for phrase in ("who are you", "what model", "which model", "your name")
        )
        if identity or (greeting and len(clean.split()) <= 8):
            return (
                f"Hello — I am NEXUS, currently using **{label}** (`{self._model}`) in offline simulation mode. "
                "I can build practical plans, troubleshoot step by step, work with approved workspace tools, and create local repositories, sir. "
                "For live model reasoning and current facts, configure an NVIDIA API key."
            )
        if re.search(r"\bstatus\s+report\b", lower):
            return (
                "J.A.R.V.I.S. at your service, sir. "
                f"NEXUS is responding through offline **{label}** (`{self._model}`) simulation because no live NVIDIA API key is available. "
                "This is a provider status report, not a verified infrastructure health check."
            )
        if any(token in lower for token in ("system status", "diagnostic", "are you online")):
            return (
                f"NEXUS is online with **{label}** selected; NVIDIA NIM is in simulated mode because no live API key is available. "
                "Chat history, tools, approvals, and the repository builder still use the real backend."
            )
        if "workshop" in lower and len(clean.split()) <= 14:
            return (
                "The AI Workshop is the primary nucleus of our system architecture. It bridges autonomous ReAct "
                "reasoning loops with tool execution, cognitive memory pipelines, and real-time sensory feedback."
            )
        if ("hub" in lower or "cluster" in lower) and len(clean.split()) <= 14:
            return (
                "Knowledge Graph Diagnostic: top hubs detected — Skill Suites, Local Businesses, AI Workshop, and Claude Code. "
                "The graph is indexed and ready for synthesis."
            )

        return build_practical_fallback(
            clean,
            model_label=f"offline {label} simulation",
            history=history,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        if not self.has_api_key:
            return self._simulated_response(messages)

        try:
            client = self._client()
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature if temperature is not None else self._temperature,
                "max_tokens": max_tokens or self._default_max_tokens,
            }
            if tools:
                kwargs["tools"] = tools
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("NVIDIA NIM completion error: %s. Falling back to simulated reply.", exc)
            return self._simulated_response(messages)

    async def complete_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.5,
        max_tokens: int | None = None,
    ) -> dict:
        if not self.has_api_key:
            # Simulated tool call if requested, or simulated text
            text = self._simulated_response(messages)
            return {"type": "text", "content": text}

        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._default_max_tokens,
            )
            msg = resp.choices[0].message
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                try:
                    arguments = json.loads(tc.function.arguments)
                except Exception:
                    arguments = {"raw": tc.function.arguments}
                return {
                    "type": "tool_call",
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": arguments,
                }
            return {"type": "text", "content": msg.content or ""}
        except Exception as exc:
            logger.warning("NVIDIA NIM complete_with_tools error: %s", exc)
            if not self.has_api_key or "401" in str(exc):
                return {"type": "text", "content": self._simulated_response(messages)}
            raise LLMUnavailableError(f"NVIDIA NIM tool call failed: {exc}") from exc

    async def extract_structured(
        self,
        content: str,
        schema: JSONSchema,
        instructions: str = "",
    ) -> dict:
        messages = [
            {
                "role": "system",
                "content": instructions + " Return ONLY valid JSON matching the requested schema.",
            },
            {"role": "user", "content": content},
        ]
        if not self.has_api_key:
            return {"status": "ok", "summary": self._simulated_response(messages)}

        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception as exc:
            logger.warning("NVIDIA NIM extract_structured fallback: %s", exc)
            return {"raw": content, "note": "parsed_fallback"}

    def get_supported_models(self) -> list[dict]:
        return SUPPORTED_NIM_MODELS

    def get_tier_model(self, tier: str) -> str:
        """Resolve model name for latency-tiered execution ('reflex', 'cortex', 'synthesis')."""
        tiers = {
            "reflex": "meta/llama-3.1-8b-instruct",
            "cortex": "meta/llama-3.3-70b-instruct",
            "synthesis": "nvidia/nemotron-4-340b-instruct",
        }
        return tiers.get(tier.lower(), self._model)

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from NVIDIA NIM or fallback to simulated stream."""
        if not self.has_api_key:
            simulated = self._simulated_response(messages)
            words = simulated.split(" ")
            for i, word in enumerate(words):
                prefix = "" if i == 0 else " "
                yield prefix + word
                await asyncio.sleep(0.015)
            return

        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._default_max_tokens,
                stream=True,
            )
            async for chunk in resp:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:
            logger.warning("NVIDIA NIM streaming error: %s. Falling back to simulated stream.", exc)
            simulated = self._simulated_response(messages)
            for word in simulated.split(" "):
                yield word + " "
                await asyncio.sleep(0.01)

    async def verify_connection(self) -> dict:
        """Check connection to NVIDIA NIM endpoint."""
        if not self.has_api_key:
            return {
                "connected": False,
                "status": "unconfigured",
                "message": "NVIDIA API key not set. Running in simulation mode.",
                "model": self._model,
                "base_url": self._base_url,
            }
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if res.status_code == 200:
                    return {
                        "connected": True,
                        "status": "connected",
                        "message": "Successfully connected to NVIDIA NIM endpoint.",
                        "model": self._model,
                        "base_url": self._base_url,
                    }
                return {
                    "connected": False,
                    "status": "error",
                    "code": res.status_code,
                    "message": f"NVIDIA NIM returned status {res.status_code}",
                    "model": self._model,
                    "base_url": self._base_url,
                }
        except Exception as exc:
            return {
                "connected": False,
                "status": "unreachable",
                "message": str(exc),
                "model": self._model,
                "base_url": self._base_url,
            }
