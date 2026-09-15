"""Walk forward through historical weeks and record actual refit outcomes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray
from pricepoint_core.schemas import FEATURE_NAMES

from pricepoint_monitor.drift import ks, psi, rolling_wape
from pricepoint_monitor.trigger import RetrainingTrigger

Predict = Callable[[pl.DataFrame], NDArray[np.float64]]
Refit = Callable[[pl.DataFrame], Predict]


def simulate(
    features: pl.DataFrame,
    refit: Refit,
    initial_weeks: int = 26,
) -> list[dict[str, Any]]:
    """Retrain using only labels available before each decision's as_of date.

    Monitoring observes week W only once it ends. A fired trigger schedules a
    refit for the next decision; it never changes the score already observed.
    """
    weeks: list[date] = features["week"].unique().sort().to_list()
    if initial_weeks < 3 or len(weeks) <= initial_weeks + 2:
        raise ValueError("Historical simulation needs a training window and future weeks")
    reference = features.filter(pl.col("week") < weeks[initial_weeks - 2])
    model = refit(reference)
    baseline_frame = features.filter(pl.col("week") == weeks[initial_weeks - 1])
    baseline = rolling_wape(baseline_frame["units"], model(baseline_frame))
    baseline = max(baseline, 1e-8)
    reference_predictions = model(reference)
    trigger = RetrainingTrigger()
    history: list[float] = []
    timeline: list[dict[str, Any]] = []
    pending_as_of: date | None = None
    for week in weeks[initial_weeks:]:
        current = features.filter(pl.col("week") == week)
        cutoff = current["as_of"].min()
        if (
            not isinstance(cutoff, date)
            or cutoff != week - timedelta(weeks=1)
            or current["as_of"].n_unique() != 1
        ):
            raise ValueError("Simulation requires a common one-week decision cutoff per target")
        action = "continued incumbent"
        activated_observation: date | None = None
        if pending_as_of is not None and cutoff >= pending_as_of:
            reference = features.filter(pl.col("week") < cutoff)
            model = refit(reference)
            reference_predictions = model(reference)
            action = "refit completed using labels before decision cutoff"
            activated_observation = pending_as_of
            pending_as_of = None
        predicted = model(current)
        error = (
            rolling_wape(current["units"], predicted)
            if float(current["units"].abs().sum()) > 0
            else None
        )
        if error is None:
            # A zero-demand week has no WAPE denominator. It breaks a sequence
            # of consecutive weekly error measurements instead of becoming zero.
            history.clear()
        else:
            history.append(error)
        feature_psi = {
            name: psi(reference[name].to_numpy(), current[name].to_numpy())
            for name in FEATURE_NAMES
        }
        decision = trigger.evaluate(week, feature_psi, history, baseline)
        observed_at = week + timedelta(weeks=1)
        if decision.fired:
            # The forecast for W+7 was already decided at W. Outcomes from W
            # become known at W+7 and may first affect target W+14.
            pending_as_of = (
                min(pending_as_of, observed_at) if pending_as_of is not None else observed_at
            )
        timeline.append(
            {
                "week": week.isoformat(),
                "psi": feature_psi,
                "ks": ks(reference_predictions, predicted),
                "wape": error,
                "undefined_wape": error is None,
                "retrain": decision.fired,
                "reason": decision.reason,
                "action": action,
                "train_end": str(reference["week"].max()),
                "decision_as_of": str(cutoff),
                "reference_rows": reference.height,
                "baseline_wape": baseline,
                "observed_at": observed_at.isoformat(),
                "scheduled_as_of": pending_as_of.isoformat() if pending_as_of else None,
                "refit_trigger_observed_at": (
                    activated_observation.isoformat() if activated_observation else None
                ),
            }
        )
    return timeline
