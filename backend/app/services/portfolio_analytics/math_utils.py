"""
Reusable math primitives shared across the analytics modules.
All functions are pure with no side-effects.
"""
from __future__ import annotations

import statistics as _stats


def mean(arr: list[float]) -> float:
    """Arithmetic mean, returns 0.0 for empty input."""
    return sum(arr) / len(arr) if arr else 0.0


def std(arr: list[float]) -> float:
    """Sample standard deviation, returns 0.0 when fewer than 2 elements."""
    return _stats.stdev(arr) if len(arr) >= 2 else 0.0


def pct_change(a: float | None, b: float | None) -> float | None:
    """Return (a/b − 1) × 100, or None when either value is missing/zero."""
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 4)
