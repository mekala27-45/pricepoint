"""A realized outcome cannot trigger a refit before that outcome is observable."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from pricepoint_core.schemas import FEATURE_NAMES
from pricepoint_monitor.simulation import Predict, simulate
from pricepoint_monitor.trigger import RetrainingTrigger, TriggerDecision


def history() -> pl.DataFrame:
    start = date(2020, 1, 6)
    return pl.DataFrame(
        [
            {
                "product_id": f"p{product}",
                "week": start + timedelta(weeks=index),
                "as_of": start + timedelta(weeks=index - 1),
                "units": float(10 + index),
                **{name: float(index) for name in FEATURE_NAMES},
            }
            for index in range(14)
            for product in range(20)
        ]
    )


def test_retraining_waits_until_trigger_outcome_is_observable() -> None:
    fit_ends: list[date] = []

    def refit(frame: pl.DataFrame) -> Predict:
        fit_ends.append(frame["week"].max())
        mean = float(frame["units"].mean())
        return lambda future: np.full(future.height, mean, dtype=np.float64)

    timeline = simulate(history(), refit, initial_weeks=4)
    first = timeline[0]
    assert first["retrain"]
    observed_at = date.fromisoformat(first["week"]) + timedelta(days=7)
    assert first["observed_at"] == observed_at.isoformat()
    assert first["scheduled_as_of"] == observed_at.isoformat()
    assert timeline[1]["action"] == "continued incumbent"
    assert timeline[1]["scheduled_as_of"] == first["scheduled_as_of"]
    assert timeline[2]["action"].startswith("refit completed")
    assert timeline[2]["refit_trigger_observed_at"] == observed_at.isoformat()
    assert date.fromisoformat(timeline[2]["decision_as_of"]) >= observed_at
    assert fit_ends[1] == date.fromisoformat(first["week"])
    for entry in timeline:
        assert date.fromisoformat(entry["train_end"]) < date.fromisoformat(entry["decision_as_of"])
        if entry["refit_trigger_observed_at"] is not None:
            assert entry["refit_trigger_observed_at"] <= entry["decision_as_of"]


def test_not_yet_observed_outcome_cannot_change_next_decision() -> None:
    def refit(frame: pl.DataFrame) -> Predict:
        mean = float(frame["units"].mean())
        return lambda future: np.full(future.height, mean, dtype=np.float64)

    original = history()
    changed_week = original["week"].unique().sort()[4]
    corrupted = original.with_columns(
        pl.when(pl.col("week") == changed_week)
        .then(pl.col("units") * 10000)
        .otherwise(pl.col("units"))
        .alias("units")
    )
    first = simulate(original, refit, initial_weeks=4)
    second = simulate(corrupted, refit, initial_weeks=4)
    assert first[1]["wape"] == second[1]["wape"]
    assert first[1]["train_end"] == second[1]["train_end"]
    assert first[2]["wape"] != second[2]["wape"]


def test_simulation_rejects_insufficient_initial_history() -> None:
    with pytest.raises(ValueError, match="training window"):
        simulate(history(), lambda frame: lambda future: np.ones(future.height), initial_weeks=1)


def test_zero_demand_week_is_undefined_and_breaks_consecutive_wape_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pricepoint_monitor import simulation

    observed_lengths: dict[date, int] = {}

    class RecordingTrigger(RetrainingTrigger):
        def evaluate(
            self,
            week: date,
            feature_psi: dict[str, float],
            recent_wape: list[float],
            baseline_wape: float,
            manual: bool = False,
        ) -> TriggerDecision:
            observed_lengths[week] = len(recent_wape)
            return super().evaluate(week, feature_psi, recent_wape, baseline_wape, manual)

    monkeypatch.setattr(simulation, "RetrainingTrigger", RecordingTrigger)
    original = history()
    zero_week = original["week"].unique().sort()[7]
    frame = original.with_columns(
        pl.when(pl.col("week") == zero_week).then(0.0).otherwise(pl.col("units")).alias("units")
    )
    timeline = simulate(
        frame, lambda training: lambda future: np.ones(future.height), initial_weeks=4
    )
    zero_result = next(row for row in timeline if row["week"] == zero_week.isoformat())
    assert zero_result["wape"] is None
    assert zero_result["undefined_wape"]
    assert zero_result["psi"] and zero_result["ks"] >= 0
    assert observed_lengths[zero_week] == 0
    assert observed_lengths[zero_week + timedelta(weeks=1)] == 1
    assert observed_lengths[zero_week + timedelta(weeks=3)] == 3
    assert observed_lengths[zero_week + timedelta(weeks=4)] == 4
