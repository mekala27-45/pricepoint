from __future__ import annotations

import importlib.util
import json
import pickle
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]


def verifier() -> Any:
    specification = importlib.util.spec_from_file_location(
        "artifact_verifier",
        ROOT / "scripts/verify_artifacts.py",
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def cloned_metric_artifacts(tmp_path: Path) -> Path:
    for name in ("backtest.json", "predictions.parquet", "training_features.parquet"):
        shutil.copyfile(ROOT / "artifacts" / name, tmp_path / name)
    return tmp_path


def test_measured_fold_metrics_rederive_from_predictions_and_training(
    cloned_metric_artifacts: Path,
) -> None:
    assert verifier().verify_backtest(cloned_metric_artifacts) == []


@pytest.mark.parametrize("mutation", ["fold_wape", "summary_variance", "coverage"])
def test_artifact_gate_detects_deliberate_metric_corruption(
    cloned_metric_artifacts: Path,
    mutation: str,
) -> None:
    path = cloned_metric_artifacts / "backtest.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "fold_wape":
        report["folds"][0]["wape"] += 0.1
    elif mutation == "summary_variance":
        report["summary"][0]["wape"]["std"] = 0
    else:
        report["coverage"]["conformal"] = 0.99
    path.write_text(json.dumps(report), encoding="utf-8")
    assert verifier().verify_backtest(cloned_metric_artifacts)


def test_latency_gate_rejects_false_percentiles_and_histogram(tmp_path: Path) -> None:
    source = json.loads((ROOT / "artifacts/loadtest-inprocess.json").read_text(encoding="utf-8"))
    path = tmp_path / "latency.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    assert verifier().verify_latency(path) == []
    source["p99_ms"] = 0
    source["histogram"][0]["count"] += 1
    path.write_text(json.dumps(source), encoding="utf-8")
    failures = verifier().verify_latency(path)
    assert any("p99" in failure for failure in failures)
    assert any("histogram" in failure for failure in failures)


def test_backtest_creates_cache_and_artifact_directories_on_fresh_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import evaluate

    features = pl.DataFrame({"week": [date(2011, 11, 28), date(2011, 12, 5)], "units": [4.0, 1.0]})
    source = tmp_path / "data/gold/features.parquet"
    source.parent.mkdir(parents=True)
    features.write_parquet(source)
    received: list[pl.DataFrame] = []
    tracked: list[dict[str, Any]] = []

    def fit(frame: pl.DataFrame) -> SimpleNamespace:
        received.append(frame)
        return SimpleNamespace(
            artifacts={"summary": [], "predictions": [{"low": 1.0, "high": 5.0}]},
            train_frame=frame,
            test_frame=frame,
        )

    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    monkeypatch.setattr(evaluate, "ARTIFACTS", tmp_path / "artifacts")
    monkeypatch.setattr(evaluate, "run_backtest", fit)
    monkeypatch.setattr(evaluate, "track", tracked.append)
    evaluate.backtest()
    assert received[0]["week"].to_list() == [date(2011, 11, 28)]
    cached = pickle.loads((tmp_path / ".cache/evaluation.pkl").read_bytes())
    assert cached.train_frame.equals(received[0])
    assert pl.read_parquet(tmp_path / "artifacts/predictions.parquet").height == 1
    assert pl.read_parquet(tmp_path / "artifacts/training_features.parquet").equals(received[0])
    assert pl.read_parquet(tmp_path / "artifacts/test_features.parquet").equals(received[0])
    assert tracked and (tmp_path / "artifacts/backtest.json").is_file()


@pytest.fixture
def cloned_monitoring_artifacts(tmp_path: Path) -> Path:
    for name in ("monitoring.json", "monitoring_summary.json"):
        shutil.copyfile(ROOT / "artifacts" / name, tmp_path / name)
    # Only temporal anchors are needed by the independent chronology checks.
    pl.DataFrame({"week": [date(2009, 12, 14)]}).write_parquet(
        tmp_path / "training_features.parquet"
    )
    pl.DataFrame(
        {"week": [date(2011, 11, 28), date(2011, 12, 5)], "is_complete_week": [True, False]}
    ).write_parquet(tmp_path / "serving_panel.parquet")
    return tmp_path


def test_monitoring_reconciles_real_observation_and_refit_timeline(
    cloned_monitoring_artifacts: Path,
) -> None:
    assert verifier().verify_monitoring(cloned_monitoring_artifacts) == []


@pytest.mark.parametrize("field", ["weeks", "triggers", "completed_refits"])
def test_monitoring_rejects_false_summary_counts(
    cloned_monitoring_artifacts: Path, field: str
) -> None:
    path = cloned_monitoring_artifacts / "monitoring_summary.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report[field] += 1
    path.write_text(json.dumps(report), encoding="utf-8")
    assert any(
        field.replace("_", " ") in error
        for error in verifier().verify_monitoring(cloned_monitoring_artifacts)
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("reordered", "chronology"),
        ("premature_refit", "completed action"),
        ("early_observation", "observation availability"),
        ("early_schedule", "scheduled decision cutoff"),
        ("future_training", "training labels"),
        ("cooldown", "trigger policy"),
        ("undefined_wape", "undefined WAPE"),
    ],
)
def test_monitoring_rejects_corrupted_timing_and_policy(
    cloned_monitoring_artifacts: Path, mutation: str, expected: str
) -> None:
    path = cloned_monitoring_artifacts / "monitoring.json"
    timeline = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "reordered":
        timeline[0], timeline[1] = timeline[1], timeline[0]
    elif mutation == "premature_refit":
        timeline[1]["action"] = timeline[2]["action"]
        timeline[1]["refit_trigger_observed_at"] = timeline[0]["observed_at"]
    elif mutation == "early_observation":
        timeline[0]["observed_at"] = timeline[0]["week"]
    elif mutation == "early_schedule":
        timeline[0]["scheduled_as_of"] = timeline[0]["decision_as_of"]
    elif mutation == "future_training":
        timeline[2]["train_end"] = timeline[2]["decision_as_of"]
    elif mutation == "cooldown":
        timeline[1]["retrain"] = True
    else:
        next(row for row in timeline if row["wape"] is None)["undefined_wape"] = False
    path.write_text(json.dumps(timeline), encoding="utf-8")
    assert any(
        expected in error for error in verifier().verify_monitoring(cloned_monitoring_artifacts)
    )


def test_bundle_must_publish_the_exact_monitoring_timeline(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    public = tmp_path / "web/public"
    public.mkdir(parents=True)
    for name in ("backtest.json", "monitoring.json"):
        shutil.copyfile(ROOT / "artifacts" / name, artifacts / name)
    path = public / "bundle.json"
    shutil.copyfile(ROOT / "web/public/bundle.json", path)
    assert verifier().verify_bundle(tmp_path) == []
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["monitoring"][0]["observed_at"] = bundle["monitoring"][0]["week"]
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert any("bundle monitoring" in error for error in verifier().verify_bundle(tmp_path))


@pytest.mark.parametrize("field", ["sigma", "units_per_arm", "weeks"])
def test_experiment_sizing_is_rederived_from_held_out_residuals(tmp_path: Path, field: str) -> None:
    for name in ("experiment.json", "predictions.parquet"):
        shutil.copyfile(ROOT / "artifacts" / name, tmp_path / name)
    assert verifier().verify_experiment(tmp_path) == []
    path = tmp_path / "experiment.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report[field] += 1
    path.write_text(json.dumps(report), encoding="utf-8")
    assert verifier().verify_experiment(tmp_path)


@pytest.mark.parametrize("mutation", ["coefficient", "interval", "recovered", "rows"])
def test_synthetic_recovery_is_rederived_from_known_process(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "synthetic_validation.json"
    shutil.copyfile(ROOT / "artifacts/synthetic_validation.json", path)
    assert verifier().verify_synthetic(tmp_path) == []
    report = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "coefficient":
        report["estimates"][0]["after"] += 0.2
    elif mutation == "interval":
        report["estimates"][0]["after_low"] -= 0.2
    elif mutation == "recovered":
        report["categories_recovered"] = 0
    else:
        report["rows"] -= 1
    path.write_text(json.dumps(report), encoding="utf-8")
    assert verifier().verify_synthetic(tmp_path)
