# NEXUS Plugin System Contract

NEXUS plugins allow dynamic, decoupled extension of the conscious cortex's tool registry.

Plugins are pure Python packages or modules dropped into the configured plugins directory (`plugins/` by default).

---

## 1. Directory Structure

Each plugin lives either as a directory containing an `__init__.py` or as a standalone `.py` module:

```
plugins/
├── README.md
├── sample_text_tools/
│   └── __init__.py          # TOOLS: list[Tool], HANDLERS: dict[str, Callable]
└── math_tools/
    └── __init__.py          # TOOLS: list[Tool], HANDLERS: dict[str, Callable]
```

---

## 2. Plugin Contract

Every plugin module must export two top-level variables:

### `TOOLS: list[Tool]`
A list of `nexus.domain.entities.tool.Tool` instances declaring the tool identity and contracts:
- `id`: unique identifier string (e.g. `"math_statistics"`)
- `name`: human-readable name for LLM invocation
- `description`: prompt documentation describing what the tool does
- `input_schema`: `JSONSchema` defining expected parameters
- `output_schema`: `JSONSchema` defining output shape
- `status`: `ToolStatus.READY`

### `HANDLERS: dict[str, Callable]`
A dictionary mapping `tool.id` to an `async` callable:
```python
async def handler(params: dict[str, Any]) -> dict[str, Any]:
    ...
```

---

## 3. Registration and Lifecycle

1. **Discovery**: `PluginLoader` scans `plugins/` for package directories or `.py` files.
2. **Import**: Each module is loaded dynamically with an isolated namespace (`nexus_plugin_<name>`).
3. **Registration**: For each tool in `TOOLS`, the tool metadata is registered with the `ToolRegistry` port.
4. **Execution**: The associated async handler is wired into the `ToolExecutor`. When the ReAct loop or Swarm invokes a tool, the registered handler is executed safely.

---

## 4. Installed Plugins

- **`sample_text_tools`**:
  - `word_count`: Counts words, lines, and characters in a text block.
  - `capitalize`: Capitalizes each word in a string.
- **`math_tools`**:
  - `math_statistics`: Calculates count, mean, median, min, max, and variance for a list of numbers.
  - `prime_factors`: Computes the prime factorization of an integer >= 2.
