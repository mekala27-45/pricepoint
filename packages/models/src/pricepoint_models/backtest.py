"""Expanding-window evaluation with frozen temporal calibration and test sets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import duckdb
import numpy as np
import polars as pl

from pricepoint_models.estimators import (
    BaselineModel,
    CalibratedModel,
    CategoryElasticityModel,
    DemandModel,
    LightGBMDemandModel,
    targets,
)


@dataclass(frozen=True)
class TemporalSplit:
    fold: int
    fit_end: date
    calibration_week: date
    gap_week: date
    decision_as_of: date
    test_week: date

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold": self.fold,
            "fit_end": self.fit_end.isoformat(),
            "calibration_week": self.calibration_week.isoformat(),
            "gap_week": self.gap_week.isoformat(),
            "decision_as_of": self.decision_as_of.isoformat(),
            "test_week": self.test_week.isoformat(),
        }


def rolling_origin_splits(
    weeks: list[date],
    *,
    folds: int = 8,
    min_train_weeks: int = 26,
) -> list[TemporalSplit]:
    """Reserve the latest folds as one-week tests; never shuffle observations.

    For test week T, decisions are at T-7 days. Calibration labels cover T-14,
    leaving T-7 as the decision gap. Base fitting stops at T-28, so calibration
    itself has the same decision gap and cannot train on its own labels.
    """
    ordered = sorted(set(weeks))
    if folds < 1 or min_train_weeks < 2:
        raise ValueError("At least one fold and two initial training weeks are required")
    if len(ordered) < min_train_weeks + folds + 3:
        raise ValueError("Insufficient weekly history for fitting, calibration, gaps, and tests")
    if any(
        right - left != timedelta(days=7) for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("Backtest requires a contiguous weekly calendar")
    return [
        TemporalSplit(
            index + 1,
            week - timedelta(days=28),
            week - timedelta(days=14),
            week - timedelta(days=7),
            week - timedelta(days=7),
            week,
        )
        for index, week in enumerate(ordered[-folds:])
    ]


def wape(actual: np.ndarray[Any, Any], predicted: np.ndarray[Any, Any]) -> float | None:
    """Absolute error over absolute demand; all-zero windows are undefined."""
    denominator = float(np.abs(actual).sum())
    if denominator == 0:
        return None
    return float(np.abs(actual - predicted).sum() / denominator)


def training_scales(training: pl.DataFrame) -> dict[str, float]:
    """Compute each product's one-step naive MAE from training labels only."""
    scales: dict[str, float] = {}
    for (product,), rows in training.sort("week").partition_by("product_id", as_dict=True).items():
        values = targets(rows)
        if len(values) > 1:
            scale = float(np.abs(np.diff(values)).mean())
            if scale > 1e-12:
                scales[str(product)] = scale
    return scales


def mase(
    frame: pl.DataFrame, predicted: np.ndarray[Any, Any], scales: dict[str, float]
) -> tuple[float | None, int]:
    """Average product-scaled errors, reporting excluded zero-scale products."""
    errors: list[float] = []
    excluded = 0
    for product, actual, prediction in zip(
        frame["product_id"].to_list(), targets(frame), predicted, strict=True
    ):
        scale = scales.get(str(product))
        if scale is None:
            excluded += 1
        else:
            errors.append(abs(float(actual) - float(prediction)) / scale)
    return (float(np.mean(errors)) if errors else None), excluded


def _universe(
    training: pl.DataFrame,
    min_sales_weeks: int,
    min_distinct_prices: int,
    max_products: int | None,
) -> tuple[list[str], dict[str, int]]:
    counts = training.group_by("product_id").agg(
        (pl.col("units") > 0).sum().alias("sales_weeks"),
        pl.col("price").filter(pl.col("units") > 0).n_unique().alias("prices"),
        pl.col("units").sum().alias("total_units"),
    )
    enough_history = pl.col("sales_weeks") >= min_sales_weeks
    enough_prices = pl.col("prices") >= min_distinct_prices
    eligible = counts.filter(enough_history & enough_prices).sort(
        ["total_units", "product_id"], descending=[True, False]
    )
    selected = eligible if max_products is None else eligible.head(max_products)
    return [str(product) for product in selected["product_id"].to_list()], {
        "observed_products": counts.height,
        "excluded_insufficient_sales_weeks": counts.filter(~enough_history).height,
        "excluded_insufficient_prices_after_history_filter": counts.filter(
            enough_history & ~enough_prices
        ).height,
        "eligible_products": eligible.height,
        "selected_products": selected.height,
        "excluded_compute_cap": eligible.height - selected.height,
    }


def analytical_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DuckDB computes fold means and sample SD; the stored fold table is authoritative."""
    frame = pl.DataFrame(rows)
    with duckdb.connect(":memory:") as connection:
        connection.register("fold_metrics", frame.to_arrow())
        table = connection.execute("""
            SELECT model, avg(wape) AS wape_mean, stddev_samp(wape) AS wape_std,
                   count(wape) AS wape_n, avg(mase) AS mase_mean,
                   stddev_samp(mase) AS mase_std, count(mase) AS mase_n
            FROM fold_metrics GROUP BY model ORDER BY model
        """).fetchall()
    return [
        {
            "model": row[0],
            "wape": {"mean": row[1], "std": row[2], "n": row[3]},
            "mase": {"mean": row[4], "std": row[5], "n": row[6]},
        }
        for row in table
    ]


@dataclass
class BacktestResult:
    artifacts: dict[str, Any]
    model: CalibratedModel
    incumbent: CalibratedModel
    support: dict[str, list[float]]
    train_frame: pl.DataFrame
    calibration_frame: pl.DataFrame
    test_frame: pl.DataFrame


def run_backtest(
    features: pl.DataFrame,
    *,
    folds: int = 8,
    min_train_weeks: int = 26,
    min_sales_weeks: int = 20,
    min_distinct_prices: int = 3,
    max_products: int | None = None,
    nominal: float = 0.9,
    n_estimators: int = 100,
) -> BacktestResult:
    """Fit all six models in each expanding fold and evaluate untouched future labels."""
    if (
        min_sales_weeks < 1
        or min_distinct_prices < 2
        or (max_products is not None and max_products < 1)
    ):
        raise ValueError("Universe thresholds must be positive and require at least two prices")
    if features.select(pl.struct("product_id", "week").n_unique()).item() != features.height:
        raise ValueError("Gold features must contain exactly one row per product and week")
    if features.filter(pl.col("as_of") != pl.col("week") - pl.duration(days=7)).height:
        raise ValueError("Each target week must have a decision cutoff exactly one week earlier")
    weeks = features["week"].unique().sort().to_list()
    splits = rolling_origin_splits(weeks, folds=folds, min_train_weeks=min_train_weeks)
    metric_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    interval_rows: list[dict[str, Any]] = []
    final_models: dict[str, DemandModel] = {}
    final_candidate: CalibratedModel | None = None
    final_elasticity: list[dict[str, Any]] = []
    final_train = pl.DataFrame()
    final_calibration = pl.DataFrame()
    final_test = pl.DataFrame()
    for split in splits:
        available_train = features.filter(pl.col("week") <= split.fit_end)
        universe, universe_report = _universe(
            available_train, min_sales_weeks, min_distinct_prices, max_products
        )
        if not universe:
            raise ValueError(
                f"No products meet training-only universe thresholds in fold {split.fold}"
            )
        allowed = pl.col("product_id").is_in(universe)
        train = available_train.filter(allowed).sort("product_id", "week")
        calibration = features.filter(allowed & (pl.col("week") == split.calibration_week)).sort(
            "product_id"
        )
        test = features.filter(allowed & (pl.col("week") == split.test_week)).sort("product_id")
        if calibration.height == 0 or test.height == 0:
            raise ValueError("Every fold needs nonempty calibration and test observations")
        scales = training_scales(train)
        models: list[DemandModel] = [
            BaselineModel("B0"),
            BaselineModel("B1"),
            BaselineModel("B2"),
            BaselineModel("B3"),
            CategoryElasticityModel(),
            LightGBMDemandModel(n_estimators=n_estimators, nominal=nominal),
        ]
        actual = targets(test)
        split_rows.append(
            {
                **split.to_dict(),
                "fit_start": str(train["week"].min()),
                "fit_rows": train.height,
                "calibration_rows": calibration.height,
                "test_rows": test.height,
                "universe": universe_report,
            }
        )
        for estimator in models:
            estimator.fit(train)
            prediction = estimator.predict(test)
            mase_value, excluded = mase(test, prediction, scales)
            metric_rows.append(
                {
                    "fold": split.fold,
                    "test_week": split.test_week.isoformat(),
                    "model": estimator.name,
                    "wape": wape(actual, prediction),
                    "mase": mase_value,
                    "mase_excluded_rows": excluded,
                    "rows": test.height,
                }
            )
            low: np.ndarray[Any, Any] | None = None
            high: np.ndarray[Any, Any] | None = None
            if isinstance(estimator, LightGBMDemandModel):
                calibrated = CalibratedModel.calibrate(estimator, calibration, nominal)
                _, low, high = calibrated.predict_interval(test)
                qlow, qhigh = estimator.predict_quantiles(test)
                interval_rows.append(
                    {
                        "fold": split.fold,
                        "test_week": split.test_week.isoformat(),
                        "nominal": nominal,
                        "conformal_coverage": float(np.mean((actual >= low) & (actual <= high))),
                        "quantile_coverage": float(np.mean((actual >= qlow) & (actual <= qhigh))),
                        "conformal_mean_width": float(np.mean(high - low)),
                        "quantile_mean_width": float(np.mean(qhigh - qlow)),
                        "calibration_radius": calibrated.radius,
                        "calibration_rows": calibration.height,
                        "test_rows": test.height,
                        "calibration_week": split.calibration_week.isoformat(),
                        "coverage_split": "held_out_test",
                    }
                )
                final_candidate = calibrated
            for index, row in enumerate(
                test.select("product_id", "category").iter_rows(named=True)
            ):
                prediction_rows.append(
                    {
                        "fold": split.fold,
                        "week": split.test_week.isoformat(),
                        "model": estimator.name,
                        "product_id": str(row["product_id"]),
                        "category": str(row["category"]),
                        "actual": float(actual[index]),
                        "predicted": float(prediction[index]),
                        "low": float(low[index]) if low is not None else None,
                        "high": float(high[index]) if high is not None else None,
                    }
                )
            if isinstance(estimator, CategoryElasticityModel):
                final_elasticity = estimator.report
            final_models[estimator.name] = estimator
        final_train, final_calibration, final_test = train, calibration, test
    if final_candidate is None:
        raise RuntimeError("Backtest produced no calibrated demand model")
    summary = analytical_summary(metric_rows)
    baseline_rows = [row for row in summary if row["model"].startswith("B")]
    best_baseline = min(
        baseline_rows,
        key=lambda row: (
            float(row["wape"]["mean"]) if row["wape"]["mean"] is not None else float("inf")
        ),
    )["model"]
    incumbent = CalibratedModel.calibrate(final_models[best_baseline], final_calibration, nominal)
    support = {
        str(row["product_id"]): [float(row["minimum"]), float(row["maximum"])]
        for row in final_train.group_by("product_id")
        .agg(pl.col("price").min().alias("minimum"), pl.col("price").max().alias("maximum"))
        .iter_rows(named=True)
    }
    predictions = pl.DataFrame(
        prediction_rows, schema_overrides={"low": pl.Float64, "high": pl.Float64}
    )
    category_metrics: list[dict[str, Any]] = []
    for (model_name, category), subset in predictions.partition_by(
        "model", "category", as_dict=True
    ).items():
        category_metrics.append(
            {
                "model": str(model_name),
                "category": str(category),
                "rows": subset.height,
                "wape": wape(subset["actual"].to_numpy(), subset["predicted"].to_numpy()),
            }
        )
    coverage_count = sum(row["test_rows"] for row in interval_rows)
    conformal_coverage = (
        sum(row["conformal_coverage"] * row["test_rows"] for row in interval_rows) / coverage_count
    )
    quantile_coverage = (
        sum(row["quantile_coverage"] * row["test_rows"] for row in interval_rows) / coverage_count
    )
    artifacts: dict[str, Any] = {
        "methodology": {
            "folds": folds,
            "horizon_weeks": 1,
            "decision_gap_weeks": 1,
            "expanding_window": True,
            "shuffled": False,
            "calibration": (
                "Separate historical week before the decision gap; test labels are never "
                "used to calibrate their own intervals"
            ),
            "mase_scale": (
                "Product-level one-step naive MAE estimated from base-fit training labels only; "
                "zero-scale observations excluded and counted"
            ),
            "min_sales_weeks": min_sales_weeks,
            "min_distinct_prices": min_distinct_prices,
            "universe_selection": "Repeated inside each fold from base-fit rows only",
            "max_products": max_products,
            "lightgbm_parameters": {
                "objective": "tweedie",
                "tweedie_variance_power": 1.5,
                "n_estimators": n_estimators,
                "num_leaves": 15,
                "learning_rate": 0.05,
                "min_child_samples": 30,
                "reg_lambda": 2,
                "seed": 42,
                "threads": 1,
            },
            "tuning": "No search: one fixed preregistered configuration, identical across folds",
            "interval_limitation": (
                "Temporal and cross-product dependence violate exact exchangeability; "
                "held-out empirical coverage is the promotion criterion"
            ),
        },
        "folds": metric_rows,
        "summary": summary,
        "split_metadata": split_rows,
        "category_metrics": sorted(
            category_metrics, key=lambda row: (row["model"], row["category"])
        ),
        "coverage": {
            "nominal": nominal,
            "conformal": conformal_coverage,
            "quantile": quantile_coverage,
            "test_rows": coverage_count,
            "coverage_split": "held_out_test",
            "folds": interval_rows,
        },
        "elasticity": final_elasticity,
        "predictions": prediction_rows,
        "incumbent_model": best_baseline,
        "support": support,
    }
    return BacktestResult(
        artifacts, final_candidate, incumbent, support, final_train, final_calibration, final_test
    )
