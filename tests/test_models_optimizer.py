"""Constraints are enforced on penny prices, including tight fractional bounds."""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pricepoint_models import BaselineModel, CalibratedModel, optimize
from pricepoint_models.optimizer import with_candidate_prices


def feature_row() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "price": [10.0],
            "relative_price": [2.0],
            "log_price": [2.302585],
            "mean4": [30.0],
            "units": [30.0],
        }
    )


def model() -> CalibratedModel:
    return CalibratedModel(BaselineModel().fit(feature_row()), 5.0)


@given(cost=st.integers(100, 899), inventory=st.integers(0, 1000))
@settings(max_examples=25, deadline=None)
def test_optimizer_never_violates_cost_support_or_inventory(cost: int, inventory: int) -> None:
    result = optimize(
        model(),
        feature_row(),
        current_price=10,
        cost_floor=cost / 100,
        min_markdown=0.1,
        max_markdown=0.8,
        inventory=inventory,
        support=(2.0, 9.0),
    )
    assert cost / 100 <= result["recommended_price"] <= 9.0
    assert 2.0 <= result["recommended_price"] <= 9.0
    assert result["expected_units"] <= inventory
    assert result["interval"][1] <= inventory
    assert result["recommended_price"] * 100 == pytest.approx(
        round(result["recommended_price"] * 100)
    )
    if result["recommended_price"] in (2.0, 9.0):
        assert result["extrapolation_warning"]


def test_optimizer_revenue_margin_support_boundary_and_candidate_features() -> None:
    constraints: dict[str, Any] = dict(
        current_price=10.0,
        cost_floor=3.001,
        min_markdown=0.0,
        max_markdown=0.7,
        inventory=20.0,
        support=(2.0, 9.999),
    )
    result = optimize(model(), feature_row(), **constraints)
    assert result["recommended_price"] == 9.99
    assert result["extrapolation_warning"]
    assert result["expected_revenue"] == pytest.approx(199.8)
    assert result["grid_candidates"] == 699
    margin = optimize(model(), feature_row(), objective="margin", **constraints)
    assert margin["expected_margin"] == pytest.approx(20 * (9.99 - 3.001))
    changed = with_candidate_prices(feature_row(), [5.0])
    assert changed["relative_price"][0] == 1.0
    assert changed["mean4"][0] == 30.0
    constraints["max_markdown"] = 0.2
    constraints["min_markdown"] = 0.2
    interior = optimize(model(), feature_row(), **constraints)
    assert interior["recommended_price"] == 8.0
    assert not interior["extrapolation_warning"]


@pytest.mark.parametrize(
    "changed,match",
    [
        ({"cost_floor": 20.0}, "No penny"),
        ({"cost_floor": -1.0}, "nonnegative"),
        ({"inventory": -1.0}, "nonnegative"),
        ({"current_price": float("inf")}, "finite"),
        ({"min_markdown": 0.9, "max_markdown": 0.2}, "Markdown"),
        ({"support": (10.0, 5.0)}, "Historical"),
        ({"objective": "profit"}, "Objective"),
    ],
)
def test_optimizer_rejects_infeasible_or_invalid_requests(
    changed: dict[str, Any], match: str
) -> None:
    constraints: dict[str, Any] = dict(
        current_price=10.0,
        cost_floor=2.0,
        min_markdown=0.0,
        max_markdown=0.5,
        inventory=30.0,
        support=(2.0, 10.0),
    )
    constraints.update(changed)
    with pytest.raises(ValueError, match=match):
        optimize(model(), feature_row(), **constraints)


def test_optimizer_requires_single_row_positive_price_and_calibration() -> None:
    with pytest.raises(ValueError, match="Exactly one"):
        with_candidate_prices(pl.concat([feature_row(), feature_row()]), [2.0])
    with pytest.raises(ValueError, match="positive"):
        with_candidate_prices(feature_row(), [-1.0])
    with pytest.raises(ValueError, match="calibrated"):
        optimize(
            BaselineModel().fit(feature_row()),
            feature_row(),
            current_price=10,
            cost_floor=2,
            min_markdown=0,
            max_markdown=0.5,
            inventory=10,
            support=(2, 10),
        )
