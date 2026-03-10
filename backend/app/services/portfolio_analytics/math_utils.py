"""
Reusable math primitives shared across the analytics modules.
All functions are pure with no side-effects.

Uses NumPy for numerical stability and performance.
"""
from __future__ import annotations

import numpy as np


def mean(arr: list[float]) -> float:
    """Arithmetic mean, returns 0.0 for empty input."""
    if not arr:
        return 0.0
    return float(np.mean(np.asarray(arr, dtype=np.float64)))


def std(arr: list[float]) -> float:
    """Sample standard deviation (ddof=1), returns 0.0 when fewer than 2 elements."""
    if len(arr) < 2:
        return 0.0
    return float(np.std(np.asarray(arr, dtype=np.float64), ddof=1))


def pct_change(a: float | None, b: float | None) -> float | None:
    """Return (a/b − 1) × 100, or None when either value is missing/zero."""
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 4)
