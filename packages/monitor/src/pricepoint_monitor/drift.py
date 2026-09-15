"""Distribution drift and realized error, with finite-data validation."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pricepoint_core.metrics import wape
from scipy.stats import ks_2samp


def _values(values: ArrayLike) -> NDArray[np.float64]:
    result = np.asarray(values, dtype=float).ravel()
    if result.size == 0 or not np.isfinite(result).all():
        raise ValueError("Drift inputs must be finite and nonempty")
    return result


def psi(reference: ArrayLike, current: ArrayLike, bins: int = 10) -> float:
    """Training-quantile PSI with open tails and Jeffreys smoothing."""
    r, c = _values(reference), _values(current)
    if bins < 2:
        raise ValueError("At least two bins are required")
    edges = np.unique(np.quantile(r, np.linspace(0, 1, bins + 1)))
    if edges.size == 1:
        value = float(edges[0])
        delta = max(abs(value) * 1e-8, 1e-8)
        edges = np.array([value - delta, value + delta])
    edges = np.concatenate(([-np.inf], edges, [np.inf]))
    rh = np.histogram(r, bins=edges)[0].astype(float) + 0.5
    ch = np.histogram(c, bins=edges)[0].astype(float) + 0.5
    rp, cp = rh / rh.sum(), ch / ch.sum()
    return float(np.sum((cp - rp) * np.log(cp / rp)))


def ks(reference: ArrayLike, current: ArrayLike) -> float:
    return float(ks_2samp(_values(reference), _values(current)).statistic)


def rolling_wape(actual: ArrayLike, predicted: ArrayLike) -> float:
    return wape(actual, predicted)
