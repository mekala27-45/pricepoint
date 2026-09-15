from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

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
