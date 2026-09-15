"""Recover a known synthetic price coefficient with the category OLS adapter.

This validates estimator arithmetic under an explicitly specified data-generating
process. It cannot validate causal identification on observational retail data.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from pricepoint_models import FEATURE_NAMES, CategoryElasticityModel


def validate(*, seed: int = 42, true_coefficient: float = -1.5) -> dict[str, Any]:
    """Generate known exogenous price variation and report recovery without a split."""
    generator = np.random.default_rng(seed)
    start = date(2020, 1, 6)
    rows: list[dict[str, Any]] = []
    for category in range(4):
        for product in range(32):
            product_effect = product / 32
            history: list[float] = []
            for week_index in range(104):
                week = start + timedelta(weeks=week_index)
                price_noise, outcome_noise = generator.normal(0.0, 0.18, 2)
                # Product-level price differences are confounded; the assigned
                # within-product perturbation supplies identifiable variation.
                log_price = 0.8 + product_effect + float(price_noise)
                price = math.exp(log_price)
                sine = math.sin(2 * math.pi * week_index / 52)
                cosine = math.cos(2 * math.pi * week_index / 52)
                observed_proxy = ((week_index + product) % 13) / 13
                log_units = (
                    5
                    + 3 * product_effect
                    + true_coefficient * log_price
                    + 0.25 * sine
                    - 0.08 * cosine
                    + 0.003 * week_index
                    - 0.2 * observed_proxy
                    + float(outcome_noise)
                )
                units = math.expm1(log_units)
                available = history[: max(0, week_index - 1)]
                recent = available[-4:]
                rows.append(
                    {
                        "product_id": f"c{category}p{product:02}",
                        "category": f"synthetic_{category}",
                        "week": week,
                        "as_of": week - timedelta(days=7),
                        "units": units,
                        "price": price,
                        "relative_price": math.exp(float(price_noise)),
                        "log_price": log_price,
                        "lag1": available[-1] if available else 0.0,
                        "lag2": available[-2] if len(available) >= 2 else 0.0,
                        "lag4": available[-4] if len(available) >= 4 else 0.0,
                        "lag52": available[-52] if len(available) >= 52 else 0.0,
                        "mean4": float(np.mean(recent)) if recent else 0.0,
                        "std4": float(np.std(recent)) if recent else 0.0,
                        "weeks_since_change": 0.0,
                        "last_change": 0.0,
                        "category_mean": 0.0,
                        "week_sin": sine,
                        "week_cos": cosine,
                        "holiday_distance": 0.0,
                        "age_weeks": float(week_index),
                        "zero_fraction": observed_proxy,
                        "trend": float(week_index),
                    }
                )
                history.append(units)
    frame = pl.DataFrame(rows).with_columns(pl.col(FEATURE_NAMES).cast(pl.Float64))
    fitted = CategoryElasticityModel().fit(frame)
    estimates = [
        {
            **estimate,
            "true_coefficient": true_coefficient,
            "contains_true_coefficient": estimate["after_low"]
            <= true_coefficient
            <= estimate["after_high"],
        }
        for estimate in fitted.report
    ]
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "rows": frame.height,
        "products": 128,
        "weeks": 104,
        "true_coefficient": true_coefficient,
        "confidence_level": 0.95,
        "categories_recovered": sum(
            estimate["contains_true_coefficient"] for estimate in estimates
        ),
        "categories": len(estimates),
        "estimates": estimates,
        "methodology": (
            "Known log1p-demand process with product effects, seasonality, trend, a simulated "
            "availability covariate in the zero_fraction slot, and independent Gaussian price "
            "and outcome perturbations. All rows fit the recovery experiment; no data split or "
            "predictive-performance claim is made. The remaining features are adapter inputs "
            "unused by C1. Product-cluster covariance supplies the confidence intervals."
        ),
        "limitation": (
            "Recovery under known exogenous within-product price variation checks estimator "
            "arithmetic. Real retail prices are observational and need not satisfy that assumption."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/synthetic_validation.json"))
    args = parser.parse_args()
    result = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "estimates"}, indent=2))


if __name__ == "__main__":
    main()
