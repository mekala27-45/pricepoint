"""Reproduce evaluation evidence without fitting on test outcomes."""

from __future__ import annotations

import argparse
import json
import os
import pickle
import platform
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from pricepoint_models.backtest import BacktestResult, run_backtest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def backtest() -> BacktestResult:
    features = pl.read_parquet(ROOT / "data/gold/features.parquet")
    # The source ends on Friday; labels from this partial week are unavailable.
    features = features.filter(pl.col("week") < pl.date(2011, 12, 5))
    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        result = run_backtest(features)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = dict(result.artifacts)
    predictions = report.pop("predictions")
    pl.DataFrame(
        predictions, schema_overrides={"low": pl.Float64, "high": pl.Float64}
    ).write_parquet(ARTIFACTS / "predictions.parquet")
    report["measured_at"] = datetime.now(UTC).isoformat()
    report["runtime_seconds"] = time.perf_counter() - started
    report["platform"] = platform.platform()
    write_json(ARTIFACTS / "backtest.json", report)
    cache = ROOT / ".cache/evaluation.pkl"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(result))
    result.train_frame.write_parquet(ARTIFACTS / "training_features.parquet")
    result.test_frame.write_parquet(ARTIFACTS / "test_features.parquet")
    print(json.dumps(report["summary"], indent=2), flush=True)
    track(report)
    return result


def track(report: dict[str, Any]) -> None:
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    import mlflow

    mlflow.set_tracking_uri((ROOT / "mlruns").as_uri())
    mlflow.set_experiment("pricepoint")
    with mlflow.start_run(run_name="expanding-origin-public-retail") as run:
        mlflow.log_params(
            {
                "folds": 8,
                "split": "expanding",
                "decision_gap_weeks": 1,
                "dataset_sha256": "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980",
            }
        )
        for row in report["summary"]:
            mlflow.log_metrics(
                {
                    f"{row['model']}_wape": row["wape"]["mean"],
                    f"{row['model']}_mase": row["mase"]["mean"],
                }
            )
        mlflow.log_artifact(str(ARTIFACTS / "backtest.json"))
        write_json(
            ARTIFACTS / "tracking.json",
            {"run_id": run.info.run_id, "backend": "local file", "experiment": "pricepoint"},
        )


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    backtest()
