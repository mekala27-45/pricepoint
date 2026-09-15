"""Errors measured on demand, with explicit undefined cases."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pricepoint_core.schemas import MetricStat


def wape(actual: ArrayLike, predicted: ArrayLike) -> float:
    a, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if a.shape != p.shape or a.size == 0 or not np.isfinite(a).all() or not np.isfinite(p).all():
        raise ValueError("Expected aligned, finite, nonempty vectors")
    scale = float(np.abs(a).sum())
    if scale == 0:
        raise ValueError("WAPE is undefined with zero total actual demand")
    return float(np.abs(a - p).sum() / scale)


def metric_stat(values: list[float]) -> MetricStat:
    if not values or not np.isfinite(values).all():
        raise ValueError("Metrics must be finite and nonempty")
    return MetricStat(
        mean=float(np.mean(values)),
        std=float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        n=len(values),
    )
