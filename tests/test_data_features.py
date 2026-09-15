from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from pricepoint_data import (
    FEATURE_NAMES,
    PointInTimeFrame,
    ServingFeatureStore,
    batch_features,
    feature_vector,
    make_features,
    measure_skew,
)
from pricepoint_data.features import holiday_distance


@pytest.fixture(scope="module")
def panel() -> pl.DataFrame:
    rows = []
    for product in range(10):
        for week in range(65):
            units = float((product * 7 + week * 3) % 23)
            rows.append(
                {
                    "product_id": str(product),
                    "category": f"group{product % 3}",
                    "week": date(2010, 1, 4) + timedelta(weeks=week),
                    "units": units - 1,
                    "gross_units": units,
                    "price": 1.129 + product * 0.297 + (week // 5 % 4) * 0.181,
                    "description": "fixture",
                }
            )
    return pl.DataFrame(rows)


def pairs(count: int) -> list[tuple[str, date]]:
    return [
        (str(index % 10), date(2010, 1, 4) + timedelta(weeks=5 + index // 10))
        for index in range(count)
    ]


def test_no_future_leakage(panel: pl.DataFrame) -> None:
    for product, as_of in pairs(200):
        trimmed = panel.filter(pl.col("week") < as_of)
        full = batch_features(panel, as_of).filter(pl.col("product_id") == product)
        past = batch_features(trimmed, as_of).filter(pl.col("product_id") == product)
        assert full.equals(past)
        assert feature_vector(panel, product, 3.17, as_of) == feature_vector(
            trimmed, product, 3.17, as_of
        )


def test_training_serving_skew_500_pairs(panel: pl.DataFrame) -> None:
    result = measure_skew(panel, pairs(500))
    assert result["pairs"] == 500
    assert result["passed"]
    assert result["max_abs_difference"] < 1e-9


def test_skew_gate_detects_deliberate_serving_rounding_error(panel: pl.DataFrame) -> None:
    def corrupted(
        source: pl.DataFrame, product: str, price: float, as_of: date
    ) -> dict[str, float]:
        vector = feature_vector(source, product, price, as_of)
        vector["relative_price"] = round(vector["relative_price"], 1)
        return vector

    result = measure_skew(panel, pairs(500), serving_builder=corrupted)
    assert not result["passed"]
    assert result["max_abs_difference"] > 1e-3


def test_skew_gate_detects_schema_error_and_nonfinite_value(panel: pl.DataFrame) -> None:
    def missing(source: pl.DataFrame, product: str, price: float, as_of: date) -> dict[str, float]:
        vector = feature_vector(source, product, price, as_of)
        vector.pop("price")
        return vector

    def nonfinite(
        source: pl.DataFrame, product: str, price: float, as_of: date
    ) -> dict[str, float]:
        vector = feature_vector(source, product, price, as_of)
        vector["price"] = float("nan")
        return vector

    assert measure_skew(panel, pairs(1), missing)["reason"] == "feature_contract_mismatch"
    assert measure_skew(panel, pairs(1), nonfinite)["reason"] == "non_finite_feature"
    assert not measure_skew(panel, [])["passed"]


def test_point_in_time_frame_enforces_exclusive_cutoff(panel: pl.DataFrame) -> None:
    cutoff = date(2010, 2, 1)
    view = PointInTimeFrame(panel, cutoff)
    assert view.collect()["week"].max() < cutoff
    assert view.at(cutoff - timedelta(weeks=1)).height == 10
    assert view.before(cutoff - timedelta(weeks=1)).collect().height == 30
    with pytest.raises(ValueError, match="at or after"):
        view.at(cutoff)
    with pytest.raises(ValueError, match="extend"):
        view.before(cutoff + timedelta(days=1))
    with pytest.raises(ValueError, match="Missing time column"):
        PointInTimeFrame(panel, cutoff, "timestamp")


def test_features_have_correct_lags_category_leave_one_out_and_gross_target(
    panel: pl.DataFrame,
) -> None:
    as_of = date(2010, 2, 8)
    vector = feature_vector(panel, "0", 2.5, as_of)
    assert tuple(vector) == FEATURE_NAMES
    assert vector["lag1"] == 12
    assert vector["lag2"] == 9
    assert vector["lag52"] == 0
    own_changed = panel.with_columns(
        pl.when(pl.col("product_id") == "0")
        .then(pl.lit(10000.0))
        .otherwise(pl.col("gross_units"))
        .alias("gross_units"),
    )
    assert feature_vector(own_changed, "0", 2.5, as_of)["category_mean"] == vector["category_mean"]
    assert vector["price"] == 2.5


def test_gold_has_explicit_decision_lag_and_no_realized_price_leak(panel: pl.DataFrame) -> None:
    small = panel.filter(pl.col("week") <= date(2010, 2, 1))
    gold = make_features(small)
    assert gold.filter(pl.col("as_of") != pl.col("week") - pl.duration(days=7)).is_empty()
    expected = small.filter(pl.col("week") == date(2010, 2, 1)).sort("product_id")["gross_units"]
    actual = gold.filter(pl.col("week") == date(2010, 2, 1)).sort("product_id")["units"]
    assert actual.equals(expected.rename("units"))
    corrupted = small.with_columns(
        pl.when(pl.col("week") == date(2010, 2, 1))
        .then(pl.lit(900.0))
        .otherwise(pl.col("price"))
        .alias("price"),
    )
    assert gold.equals(make_features(corrupted))


def test_feature_edges_and_calendar(panel: pl.DataFrame) -> None:
    assert batch_features(panel, date(2000, 1, 1)).is_empty()
    with pytest.raises(ValueError, match="No history"):
        feature_vector(panel, "missing", 2, date(2010, 2, 1))
    with pytest.raises(ValueError, match="positive"):
        feature_vector(panel, "0", 0, date(2010, 2, 1))
    with pytest.raises(ValueError, match="three weekly"):
        make_features(panel.filter(pl.col("week") == date(2010, 1, 4)))
    assert holiday_distance(date(2011, 4, 29)) == 0
    assert holiday_distance(date(2010, 12, 27)) == 0
    assert holiday_distance(date(2010, 12, 28)) == 0
    fallback = panel.drop("gross_units").with_columns(pl.col("units").clip(lower_bound=0))
    assert measure_skew(fallback, pairs(10))["passed"]


def test_serving_store_retains_immutable_snapshot_and_recomputes_cutoffs(
    panel: pl.DataFrame,
) -> None:
    store = ServingFeatureStore(panel)
    product, as_of = pairs(1)[0]
    first = store.vector(product, 2.0, as_of)
    first["lag1"] = -900.0
    assert store.vector(product, 2.0, as_of)["lag1"] >= 0
    assert store.vector(product, 3.0, as_of)["price"] == 3
    for week in range(1, 20):
        store.vector(product, 2.0, as_of + timedelta(weeks=week))
    assert store.vector(product, 2.0, as_of) == feature_vector(panel, product, 2.0, as_of)
    assert measure_skew(panel, [(product, date(2015, 1, 5))])["passed"]


def test_gold_excludes_incomplete_observation_weeks(panel: pl.DataFrame) -> None:
    marked = panel.with_columns((pl.col("week") < date(2011, 1, 3)).alias("is_complete_week"))
    assert make_features(marked)["week"].max() == date(2010, 12, 27)
