"""
Plugin system for NEXUS — dynamic tool loading from external modules.

Each plugin is a Python module/package that exposes:
    TOOLS: List[Tool]          — tool definitions to register
    HANDLERS: Dict[str, Callable] — async handler functions keyed by tool id

Place plugin folders under the configured plugins directory (default: plugins/).
Each plugin folder must contain an __init__.py or a single .py file.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.ports.tool_registry import ToolRegistry


class PluginInfo:
    """Metadata about a loaded plugin."""

    def __init__(self, name: str, path: str, tools: List[str], error: Optional[str] = None) -> None:
        self.name = name
        self.path = path
        self.tools = tools
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "path": self.path, "tools": self.tools, "error": self.error}


class PluginLoader:
    """Discovers, loads, and registers plugins from a directory."""

    def __init__(self, plugins_dir: str | Path, registry: ToolRegistry) -> None:
        self._plugins_dir = Path(plugins_dir)
        self._registry = registry
        self._loaded: Dict[str, PluginInfo] = {}
        self._handlers: Dict[str, Callable] = {}

    @property
    def handlers(self) -> Dict[str, Callable]:
        return dict(self._handlers)

    def load_all(self) -> List[PluginInfo]:
        """Scan the plugins directory and load every valid plugin."""
        if not self._plugins_dir.exists():
            return []

        results = []
        for item in sorted(self._plugins_dir.iterdir()):
            if item.is_dir() and not item.name.startswith(("_", ".")):
                info = self._load_plugin_dir(item)
                results.append(info)
            elif item.suffix == ".py" and not item.name.startswith(("_", ".")):
                info = self._load_plugin_file(item)
                results.append(info)
        return results

    def load_plugin(self, name: str) -> Optional[PluginInfo]:
        """Load a single plugin by name (folder or .py file)."""
        dir_path = self._plugins_dir / name
        if dir_path.is_dir():
            return self._load_plugin_dir(dir_path)
        file_path = self._plugins_dir / f"{name}.py"
        if file_path.exists():
            return self._load_plugin_file(file_path)
        return None

    def _load_plugin_dir(self, path: Path) -> PluginInfo:
        module_name = f"nexus_plugin_{path.name}"
        init_file = path / "__init__.py"
        if init_file.exists():
            return self._load_module(module_name, init_file)
        # Try loading any .py file in the directory
        py_files = list(path.glob("*.py"))
        if py_files:
            return self._load_module(module_name, py_files[0])
        return PluginInfo(path.name, str(path), [], error="No __init__.py or .py files found")

    def _load_plugin_file(self, path: Path) -> PluginInfo:
        module_name = f"nexus_plugin_{path.stem}"
        return self._load_module(module_name, path)

    def _load_module(self, module_name: str, file_path: Path) -> PluginInfo:
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return PluginInfo(module_name, str(file_path), [], error="Could not create module spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            tools: List[Tool] = getattr(module, "TOOLS", [])
            handlers: Dict[str, Callable] = getattr(module, "HANDLERS", {})

            tool_ids = []
            for tool in tools:
                if tool.status == ToolStatus.READY:
                    tool.status = ToolStatus.READY
                self._handlers[tool.id] = handlers.get(tool.id, self._make_sandbox_handler(tool))
                tool_ids.append(tool.id)

            info = PluginInfo(file_path.parent.name, str(file_path), tool_ids)
            self._loaded[file_path.parent.name] = info
            return info
        except Exception as e:
            tb = traceback.format_exc()
            return PluginInfo(file_path.stem, str(file_path), [], error=f"{e}\n{tb}")

    def _make_sandbox_handler(self, tool: Tool) -> Callable:
        """Fallback handler that runs tool code in the sandbox."""

        async def _handler(params: Dict[str, Any]) -> Dict[str, Any]:
            if tool.code:
                from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox

                sandbox = SubprocessSandbox()
                return await sandbox.run(tool.code, inputs=params)
            return {"error": f"No handler and no code for tool {tool.id}"}

        return _handler

    def get_loaded(self) -> Dict[str, PluginInfo]:
        return dict(self._loaded)
