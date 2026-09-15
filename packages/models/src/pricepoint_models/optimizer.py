"""Constrained search over exact integer pennies inside the fitted support."""

from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Literal

import numpy as np
import polars as pl

from pricepoint_models.estimators import CalibratedModel, DemandModel


def with_candidate_prices(feature_row: pl.DataFrame, prices: list[float]) -> pl.DataFrame:
    """Change the intervention features while preserving all historical features."""
    if feature_row.height != 1:
        raise ValueError("Exactly one historical feature row is required")
    original_price = float(feature_row["price"][0])
    relative = float(feature_row["relative_price"][0])
    if original_price <= 0 or relative <= 0 or any(price <= 0 for price in prices):
        raise ValueError("Candidate and historical prices must be positive")
    trailing_median = original_price / relative
    return pl.concat([feature_row] * len(prices)).with_columns(
        pl.Series("price", prices, dtype=pl.Float64),
        pl.Series(
            "relative_price", [price / trailing_median for price in prices], dtype=pl.Float64
        ),
        pl.Series("log_price", [math.log(price) for price in prices], dtype=pl.Float64),
    )


def optimize(
    model: DemandModel,
    feature_row: pl.DataFrame,
    *,
    current_price: float,
    cost_floor: float,
    min_markdown: float,
    max_markdown: float,
    inventory: float,
    support: tuple[float, float] | list[float],
    objective: Literal["revenue", "margin"] = "revenue",
) -> dict[str, Any]:
    """Return the maximizing feasible price, with inventory-capped sales and bands."""
    values = [current_price, cost_floor, min_markdown, max_markdown, inventory, *support]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Business constraints must be finite")
    if current_price <= 0 or cost_floor < 0 or inventory < 0:
        raise ValueError("Price must be positive; cost and inventory must be nonnegative")
    if not 0 <= min_markdown <= max_markdown <= 1:
        raise ValueError("Markdown bounds must satisfy 0 <= minimum <= maximum <= 1")
    if len(support) != 2 or not 0 < support[0] <= support[1]:
        raise ValueError("Historical support must be a positive ordered pair")
    if objective not in ("revenue", "margin"):
        raise ValueError("Objective must be revenue or margin")
    current = Decimal(str(current_price))
    minimum = max(
        Decimal(str(cost_floor)),
        Decimal(str(support[0])),
        current * (1 - Decimal(str(max_markdown))),
    )
    maximum = min(Decimal(str(support[1])), current * (1 - Decimal(str(min_markdown))))
    low_penny = max(1, int((minimum * 100).to_integral_value(rounding=ROUND_CEILING)))
    high_penny = int((maximum * 100).to_integral_value(rounding=ROUND_FLOOR))
    if low_penny > high_penny:
        raise ValueError(
            "No penny price satisfies the cost, markdown, and fitted-support constraints"
        )
    best: dict[str, Any] | None = None
    best_value = -math.inf
    # Chunking bounds memory while preserving an exhaustive penny grid.
    for start in range(low_penny, high_penny + 1, 4096):
        prices = [penny / 100 for penny in range(start, min(high_penny + 1, start + 4096))]
        candidates = with_candidate_prices(feature_row, prices)
        if isinstance(model, CalibratedModel):
            units, lower, upper = model.predict_interval(candidates)
        else:
            raise ValueError("Markdown decisions require a calibrated interval model")
        units = np.minimum(units, inventory)
        lower = np.minimum(lower, inventory)
        upper = np.minimum(upper, inventory)
        price_array = np.asarray(prices)
        revenues = units * price_array
        margins = units * (price_array - cost_floor)
        scores = revenues if objective == "revenue" else margins
        index = int(np.argmax(scores))
        if float(scores[index]) > best_value:
            best_value = float(scores[index])
            price = prices[index]
            historical_low_penny = int(
                (Decimal(str(support[0])) * 100).to_integral_value(rounding=ROUND_CEILING)
            )
            historical_high_penny = int(
                (Decimal(str(support[1])) * 100).to_integral_value(rounding=ROUND_FLOOR)
            )
            at_support_boundary = round(price * 100) in (
                historical_low_penny,
                historical_high_penny,
            )
            best = {
                "recommended_price": price,
                "expected_units": float(units[index]),
                "expected_revenue": float(revenues[index]),
                "expected_margin": float(margins[index]),
                "interval": [float(lower[index]), float(upper[index])],
                "extrapolation_warning": at_support_boundary,
                "warning_reason": (
                    "Optimum touches fitted historical support; "
                    "demand beyond that boundary is unsupported"
                )
                if at_support_boundary
                else None,
                "markdown": 1 - price / current_price,
                "objective": objective,
                "inventory": inventory,
                "grid_candidates": high_penny - low_penny + 1,
                "model_version": model.version,
            }
    if best is None:
        raise RuntimeError("Feasible grid produced no finite demand prediction")
    return best
