from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from pricepoint_monitor.drift import ks, psi, rolling_wape
from pricepoint_monitor.trigger import RetrainingTrigger


def test_drift_sensitive_to_shift_including_constant_feature() -> None:
    x = np.arange(100, dtype=float)
    assert psi(x, x) == 0
    assert psi(x, x + 100) > 0.25
    assert psi(np.ones(100), np.zeros(100)) > 0.25
    assert ks(x, x + 100) == 1.0
    assert rolling_wape([1, 2], [1, 1]) == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        psi([], [1])
    with pytest.raises(ValueError):
        ks([float("nan")], [1])


def test_trigger_cooldown_override_persistence_and_idempotence(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    trigger = RetrainingTrigger(state_path=path)
    start = date(2011, 1, 3)
    first = trigger.evaluate(start, {"price": 0.3}, [], 0.2)
    assert first.fired
    assert not trigger.evaluate(start + timedelta(days=7), {"price": 0.3}, [], 0.2).fired
    resumed = RetrainingTrigger(state_path=path)
    assert resumed.evaluate(start, {"price": 0.0}, [], 0.2) == first
    assert resumed.evaluate(start + timedelta(days=8), {}, [], 0.2, manual=True).fired
    assert resumed.evaluate(start + timedelta(days=22), {}, [0.3] * 4, 0.2).fired
    with pytest.raises(ValueError):
        resumed.evaluate(start - timedelta(days=7), {}, [], 0.2)
    with pytest.raises(ValueError):
        resumed.evaluate(start + timedelta(days=30), {}, [], 0)


def test_trigger_needs_four_observations_and_strict_threshold() -> None:
    trigger = RetrainingTrigger()
    assert not trigger.evaluate(date(2011, 1, 3), {"price": 0.25}, [0.3] * 3, 0.2).fired
    assert trigger.evaluate(date(2011, 1, 10), {}, [0.3] * 4, 0.2).fired
