"""Behavioral checks for temporal evaluation, model fitting, and honest intervals."""

from __future__ import annotations

import ast
import json
import math
import pickle
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from pricepoint_models import (
    FEATURE_NAMES,
    BaselineModel,
    CalibratedModel,
    CategoryElasticityModel,
    LightGBMDemandModel,
    load_model,
    rolling_origin_splits,
    run_backtest,
)
from pricepoint_models.backtest import analytical_summary, mase, training_scales, wape
from pricepoint_models.estimators import conformal_radius, matrix, targets


def demand_features(products: int = 24, weeks: int = 45) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    start = date(2020, 1, 6)
    for product in range(products):
        observed: list[float] = []
        for week_index in range(weeks):
            week = start + timedelta(weeks=week_index)
            price = 1.4 + 0.17 * ((week_index + product) % 5) + product * 0.04
            sine = math.sin(2 * math.pi * week_index / 52)
            cosine = math.cos(2 * math.pi * week_index / 52)
            units = (
                math.exp(
                    4 + product * 0.08 - 1.6 * math.log(price) + 0.15 * sine + 0.004 * week_index
                )
                - 1
            )
            historical = observed[: max(0, week_index - 1)]
            recent = historical[-4:]
            row: dict[str, Any] = {
                "product_id": f"p{product:02}",
                "category": f"group{product % 2}",
                "week": week,
                "as_of": week - timedelta(days=7),
                "units": units,
                "price": price,
                "relative_price": price / 1.8,
                "log_price": math.log(price),
                "lag1": historical[-1] if historical else 0.0,
                "lag2": historical[-2] if len(historical) > 1 else 0.0,
                "lag4": historical[-4] if len(historical) > 3 else 0.0,
                "lag52": historical[-52] if len(historical) > 51 else 0.0,
                "mean4": float(np.mean(recent)) if recent else 0.0,
                "std4": float(np.std(recent)) if recent else 0.0,
                "weeks_since_change": 1.0,
                "last_change": 0.17,
                "category_mean": 30.0,
                "week_sin": sine,
                "week_cos": cosine,
                "holiday_distance": 10.0,
                "age_weeks": float(week_index),
                "zero_fraction": 0.0,
                "trend": float(week_index),
            }
            rows.append(row)
            observed.append(units)
    return pl.DataFrame(rows).with_columns(pl.col(FEATURE_NAMES).cast(pl.Float64))


@pytest.fixture(scope="module")
def features() -> pl.DataFrame:
    return demand_features()


@pytest.mark.parametrize("kind,column", [("B0", "lag1"), ("B1", "lag52"), ("B2", "mean4")])
def test_baselines_are_the_stated_forecasts(features: pl.DataFrame, kind: Any, column: str) -> None:
    model = BaselineModel(kind).fit(features)
    np.testing.assert_array_equal(model.predict(features), features[column].to_numpy())


def test_estimators_require_finite_data_and_fitting(features: pl.DataFrame) -> None:
    with pytest.raises(ValueError, match="fitted"):
        BaselineModel().predict(features)
    with pytest.raises(ValueError, match="fitted"):
        LightGBMDemandModel().predict(features)
    with pytest.raises(ValueError, match="not fitted"):
        LightGBMDemandModel().predict_quantiles(features)
    with pytest.raises(ValueError, match="Missing"):
        matrix(features.drop("price"))
    with pytest.raises(ValueError, match="finite"):
        matrix(features.with_columns(pl.lit(float("nan")).alias("price")))
    with pytest.raises(ValueError, match="nonnegative"):
        targets(features.with_columns(pl.lit(-1.0).alias("units")))
    with pytest.raises(ValueError, match="positive"):
        LightGBMDemandModel().fit(features.with_columns(pl.lit(0.0).alias("units")))
    with pytest.raises(ValueError, match="Nominal"):
        LightGBMDemandModel(nominal=1.0)


def test_controlled_elasticity_recovers_known_parameter(features: pl.DataFrame) -> None:
    model = CategoryElasticityModel().fit(features)
    assert len(model.report) == 2
    for estimate in model.report:
        assert estimate["status"] == "estimated"
        assert estimate["after"] == pytest.approx(-1.6, abs=1e-9)
        assert estimate["after_low"] - 1e-8 <= -1.6 <= estimate["after_high"] + 1e-8
        assert estimate["covariance"] == "product_cluster"
    np.testing.assert_allclose(model.predict(features), features["units"].to_numpy(), rtol=1e-8)
    unknown = features.head(1).with_columns(pl.lit("unknown").alias("category"))
    np.testing.assert_array_equal(model.predict(unknown), model.fallback.predict(unknown))


def test_elasticity_handles_unidentifiable_categories(features: pl.DataFrame) -> None:
    flat_price = features.with_columns(pl.lit(0.0).alias("log_price"))
    model = CategoryElasticityModel().fit(flat_price)
    assert all(row["status"] == "insufficient_variation" for row in model.report)
    fixed_product_price = features.with_columns(
        pl.col("log_price").first().over("product_id").alias("log_price")
    )
    model.fit(fixed_product_price)
    assert all(row["status"] == "no_within_product_price_variation" for row in model.report)
    single = features.filter(pl.col("product_id") == "p00")
    assert CategoryElasticityModel().fit(single).report[0]["covariance"] == "HC3"


def test_lightgbm_deterministic_quantiles_and_roundtrip(
    features: pl.DataFrame, tmp_path: Path
) -> None:
    first = LightGBMDemandModel(n_estimators=5).fit(features)
    second = LightGBMDemandModel(n_estimators=5).fit(features)
    np.testing.assert_array_equal(first.predict(features), second.predict(features))
    lower, upper = first.predict_quantiles(features)
    assert np.all(lower >= 0) and np.all(upper >= lower)
    calibrated = CalibratedModel.calibrate(first, features.tail(12))
    path = tmp_path / "model.pkl"
    calibrated.dump(path)
    loaded = load_model(path)
    np.testing.assert_array_equal(loaded.predict(features), calibrated.predict(features))
    assert isinstance(loaded, CalibratedModel)
    low, high = loaded.predict_quantiles(features)
    np.testing.assert_array_equal(low, lower)
    np.testing.assert_array_equal(high, upper)
    with pytest.raises(ValueError, match="Refitting"):
        loaded.fit(features)
    with pytest.raises(ValueError, match="Only"):
        CalibratedModel(BaselineModel().fit(features), 1).predict_quantiles(features)
    bad = tmp_path / "bad.pkl"
    bad.write_bytes(pickle.dumps({"not": "a model"}))
    with pytest.raises(ValueError, match="contract"):
        load_model(bad)
    first.feature_contract["version"] = "wrong"
    first.dump(path)
    with pytest.raises(ValueError, match="schema"):
        load_model(path)


def test_conformal_uses_correct_finite_sample_order_statistic() -> None:
    assert conformal_radius(np.arange(1, 11, dtype=float), 0.9) == 10
    assert conformal_radius(np.arange(1, 20, dtype=float), 0.9) == 18
    with pytest.raises(ValueError, match="Insufficient"):
        conformal_radius(np.array([1.0, 2.0]), 0.9)
    with pytest.raises(ValueError, match="Calibration requires"):
        conformal_radius(np.array([], dtype=float))
    with pytest.raises(ValueError, match="nonnegative"):
        conformal_radius(np.array([-1.0]))
    with pytest.raises(ValueError, match="nonnegative"):
        CalibratedModel(BaselineModel(), -1)


def test_metric_edge_cases_and_product_specific_training_scale() -> None:
    training = pl.DataFrame(
        {
            "product_id": ["a", "a", "a", "b", "b", "b", "c", "c"],
            "week": [1, 2, 3, 1, 2, 3, 1, 2],
            "units": [0.0, 2.0, 4.0, 10.0, 20.0, 30.0, 5.0, 5.0],
        }
    )
    scales = training_scales(training)
    assert scales == {"a": 2.0, "b": 10.0}
    test = pl.DataFrame({"product_id": ["a", "b", "c"], "units": [10.0, 50.0, 5.0]})
    value, excluded = mase(test, np.array([8.0, 40.0, 5.0]), scales)
    assert value == 1.0 and excluded == 1
    assert wape(np.zeros(2), np.ones(2)) is None
    assert wape(np.array([0, 10]), np.array([5, 5])) == 1.0
    assert mase(test, np.zeros(3), {}) == (None, 3)
    summary = analytical_summary(
        [
            {"model": "B0", "wape": 0.2, "mase": 1.0},
            {"model": "B0", "wape": 0.4, "mase": 3.0},
        ]
    )[0]
    assert summary["wape"]["std"] == pytest.approx(np.std([0.2, 0.4], ddof=1))


def test_no_shuffled_splits() -> None:
    model_path = Path(__file__).resolve().parents[1] / "packages" / "models" / "src"
    for source in model_path.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                assert name not in {"train_test_split", "KFold", "ShuffleSplit", "shuffle"}
    weeks = [date(2020, 1, 6) + timedelta(weeks=index) for index in range(45)]
    splits = rolling_origin_splits(list(reversed(weeks)))
    assert len(splits) == 8
    for split in splits:
        assert split.fit_end < split.calibration_week < split.decision_as_of < split.test_week
        assert split.fit_end + timedelta(days=14) == split.calibration_week
        assert split.calibration_week + timedelta(days=14) == split.test_week
    with pytest.raises(ValueError, match="Insufficient"):
        rolling_origin_splits(weeks[:8])
    with pytest.raises(ValueError, match="contiguous"):
        rolling_origin_splits(weeks[:30] + weeks[31:])
    with pytest.raises(ValueError, match="At least"):
        rolling_origin_splits(weeks, folds=0)


def test_eight_folds_and_test_labels_never_calibrate_themselves(features: pl.DataFrame) -> None:
    result = run_backtest(features, min_train_weeks=20, min_sales_weeks=10, n_estimators=3)
    assert len(result.artifacts["folds"]) == 48
    assert len(result.artifacts["coverage"]["folds"]) == 8
    assert result.incumbent.name in {"B0", "B1", "B2", "B3"}
    assert result.artifacts["coverage"]["coverage_split"] == "held_out_test"
    json.dumps(result.artifacts, allow_nan=False)
    final_week = features["week"].max()
    corrupted = features.with_columns(
        pl.when(pl.col("week") == final_week)
        .then(pl.col("units") * 1000)
        .otherwise(pl.col("units"))
        .alias("units")
    )
    changed = run_backtest(corrupted, min_train_weeks=20, min_sales_weeks=10, n_estimators=3)
    assert changed.model.radius == result.model.radius
    np.testing.assert_array_equal(
        changed.model.predict(result.test_frame), result.model.predict(result.test_frame)
    )
    for entry in result.artifacts["category_metrics"]:
        source = [
            row
            for row in result.artifacts["predictions"]
            if row["model"] == entry["model"] and row["category"] == entry["category"]
        ]
        expected = sum(abs(row["actual"] - row["predicted"]) for row in source) / sum(
            row["actual"] for row in source
        )
        assert entry["wape"] == pytest.approx(expected)
    for split in result.artifacts["split_metadata"]:
        assert split["universe"]["selected_products"] == 24
    assert result.artifacts["summary"][0]["wape"]["n"] == 8


def test_universe_is_training_only_and_input_failures_are_explicit(features: pl.DataFrame) -> None:
    future_only = (
        features.filter(pl.col("week") == features["week"].max())
        .head(1)
        .with_columns(pl.lit("future_product").alias("product_id"))
    )
    combined = pl.concat([features, future_only])
    result = run_backtest(combined, folds=1, min_sales_weeks=10, n_estimators=2, max_products=10)
    assert "future_product" not in result.support
    assert len(result.support) == 10
    assert result.artifacts["split_metadata"][0]["universe"]["excluded_compute_cap"] == 14
    with pytest.raises(ValueError, match="exactly one row"):
        run_backtest(pl.concat([features, features.head(1)]))
    with pytest.raises(ValueError, match="cutoff"):
        run_backtest(features.with_columns(pl.col("week").alias("as_of")))
    with pytest.raises(ValueError, match="thresholds"):
        run_backtest(features, min_distinct_prices=1)
    with pytest.raises(ValueError, match="No products"):
        run_backtest(features, min_sales_weeks=100)
