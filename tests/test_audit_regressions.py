"""Regression tests for shadow chronology and effective manual retraining overrides."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from pricepoint_core.config import Settings
from pricepoint_data.features import batch_features
from pricepoint_models import BaselineModel, CalibratedModel, Registry
from pricepoint_monitor.trigger import RetrainingTrigger
from pricepoint_serve.engine import PredictionEngine


def engine_with_multiple_candidates(tmp_path: Path) -> PredictionEngine:
    start = date(2020, 1, 6)
    panel = pl.DataFrame(
        [
            {
                "product_id": "a",
                "category": "kitchen",
                "week": start + timedelta(weeks=week),
                "units": float(10 + week % 5),
                "gross_units": float(10 + week % 5),
                "price": 2.0 + 0.1 * (week % 3),
            }
            for week in range(30)
        ]
    )
    destination = tmp_path / "panel.parquet"
    panel.write_parquet(destination)
    cutoff = start + timedelta(weeks=30)
    training = batch_features(panel, cutoff).with_columns(pl.lit(20.0).alias("units"))
    registry = Registry(tmp_path / "registry")
    metadata = {
        "support": {"a": [2.0, 2.2]},
        "as_of": cutoff.isoformat(),
        "minimum_as_of": (cutoff - timedelta(weeks=4)).isoformat(),
    }
    registry.register(
        CalibratedModel(BaselineModel("B2").fit(training), 1.0),
        {},
        version="incumbent",
        metadata=metadata,
    )
    registry.bootstrap("incumbent", reason="Measured baseline")
    for version, registered in [
        ("z-old", "2020-01-01T00:00:00+00:00"),
        ("a-new", "2020-02-01T00:00:00+00:00"),
    ]:
        candidate_metadata = {**metadata, "minimum_as_of": cutoff.isoformat()}
        manifest = registry.register(
            CalibratedModel(BaselineModel("B0").fit(training), 2.0),
            {},
            version=version,
            metadata=candidate_metadata,
        )
        manifest["created_at"] = registered
        (registry.root / version / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
    return PredictionEngine(Settings(registry=registry.root, panel=destination, shadow=True))


def test_shadow_selects_latest_registration_independent_of_version_name(tmp_path: Path) -> None:
    engine = engine_with_multiple_candidates(tmp_path)
    assert engine.candidate is not None
    assert engine.candidate.version == "a-new"
    result = engine.predict("a", 2.1, engine.default_as_of)
    assert result.model_version == "incumbent"
    assert len(engine.shadow_observations) == 1
    assert engine.shadow_observations[0]["candidate_version"] == "a-new"


def test_shadow_skips_queries_before_candidate_calibration_is_observable(tmp_path: Path) -> None:
    engine = engine_with_multiple_candidates(tmp_path)
    result = engine.predict("a", 2.1, engine.default_as_of - timedelta(weeks=1))
    assert result.model_version == "incumbent"
    assert len(engine.shadow_observations) == 0
    engine.predict("a", 2.1, engine.default_as_of)
    assert len(engine.shadow_observations) == 1


def test_later_reference_baseline_does_not_displace_shadow_candidate(tmp_path: Path) -> None:
    engine = engine_with_multiple_candidates(tmp_path)
    metadata = {
        **engine.manifest["metadata"],
        "role": "baseline",
    }
    engine.registry.register(engine.incumbent, {}, version="new-reference", metadata=metadata)
    reloaded = PredictionEngine(
        Settings(
            registry=engine.registry.root,
            panel=tmp_path / "panel.parquet",
            shadow=True,
        )
    )
    assert reloaded.candidate is not None
    assert reloaded.candidate.version == "a-new"
    reference = next(item for item in engine.registry.list() if item["version"] == "new-reference")
    assert reference["status"] == "reference"


def test_manual_override_replaces_same_week_automatic_check_once(tmp_path: Path) -> None:
    path = tmp_path / "trigger.json"
    week = date(2020, 1, 6)
    trigger = RetrainingTrigger(state_path=path)
    automatic = trigger.evaluate(week, {"price": 0.0}, [], 0.3)
    assert not automatic.fired
    manual = trigger.evaluate(week, {"price": 0.0}, [], 0.3, manual=True)
    assert manual.fired and manual.overridden
    assert trigger.evaluate(week, {}, [], 0.3, manual=True) == manual
    persisted = RetrainingTrigger(state_path=path)
    assert persisted.evaluate(week, {}, [], 0.3, manual=True) == manual


def test_manual_override_cannot_rewrite_an_older_week() -> None:
    trigger = RetrainingTrigger()
    week = date(2020, 1, 6)
    trigger.evaluate(week, {}, [], 0.3)
    trigger.evaluate(week + timedelta(weeks=1), {}, [], 0.3)
    with pytest.raises(ValueError, match="chronological"):
        trigger.evaluate(week, {}, [], 0.3, manual=True)
