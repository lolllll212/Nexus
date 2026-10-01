"""Mathematical utilities plugin for NEXUS.

Exposes tools for descriptive statistics and number-theoretic factorization.
Conforms to the NEXUS plugin contract:
    TOOLS: list[Tool]
    HANDLERS: dict[str, Callable]
"""

from __future__ import annotations

from typing import Any, Dict, List

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema

TOOLS: List[Tool] = [
    Tool(
        id="math_statistics",
        name="math_statistics",
        description="Calculate descriptive statistics (count, mean, median, min, max, variance) for a list of numbers.",
        input_schema=JSONSchema(
            type="object",
            properties={
                "numbers": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of numeric values",
                }
            },
            required=["numbers"],
        ),
        output_schema=JSONSchema(
            type="object",
            properties={
                "count": {"type": "integer"},
                "mean": {"type": "number"},
                "median": {"type": "number"},
                "min": {"type": "number"},
                "max": {"type": "number"},
                "variance": {"type": "number"},
            },
        ),
        status=ToolStatus.READY,
    ),
    Tool(
        id="prime_factors",
        name="prime_factors",
        description="Compute the prime factorization of a positive integer.",
        input_schema=JSONSchema(
            type="object",
            properties={
                "n": {
                    "type": "integer",
                    "description": "Integer to factorize (must be >= 2)",
                }
            },
            required=["n"],
        ),
        output_schema=JSONSchema(
            type="object",
            properties={
                "factors": {
                    "type": "array",
                    "items": {"type": "integer"},
                }
            },
        ),
        status=ToolStatus.READY,
    ),
]


async def _math_statistics(params: Dict[str, Any]) -> Dict[str, Any]:
    numbers = params.get("numbers", [])
    if not numbers:
        return {"error": "numbers list must not be empty"}

    n = len(numbers)
    mean_val = sum(numbers) / n
    sorted_nums = sorted(numbers)
    if n % 2 == 1:
        median_val = float(sorted_nums[n // 2])
    else:
        median_val = float((sorted_nums[n // 2 - 1] + sorted_nums[n // 2]) / 2.0)

    variance_val = sum((x - mean_val) ** 2 for x in numbers) / n if n > 1 else 0.0

    return {
        "count": n,
        "mean": round(mean_val, 4),
        "median": round(median_val, 4),
        "min": float(min(numbers)),
        "max": float(max(numbers)),
        "variance": round(variance_val, 4),
    }


async def _prime_factors(params: Dict[str, Any]) -> Dict[str, Any]:
    n = params.get("n")
    if not isinstance(n, int) or n < 2:
        return {"error": "n must be an integer >= 2"}

    factors: List[int] = []
    d = 2
    temp = n
    while d * d <= temp:
        while temp % d == 0:
            factors.append(d)
            temp //= d
        d += 1
    if temp > 1:
        factors.append(temp)

    return {"factors": factors}


HANDLERS: Dict[str, Any] = {
    "math_statistics": _math_statistics,
    "prime_factors": _prime_factors,
}
