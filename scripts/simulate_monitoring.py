"""Historical drift and retraining simulation with observable trigger dates."""

from __future__ import annotations

import time
import warnings

import polars as pl
from pricepoint_models.estimators import LightGBMDemandModel
from pricepoint_monitor.simulation import Predict, simulate

from scripts.evaluate import ROOT, write_json


def run() -> None:
    features = pl.read_parquet(ROOT / "data/gold/features.parquet")
    started = time.perf_counter()

    def refit(training: pl.DataFrame) -> Predict:
        model = LightGBMDemandModel(n_estimators=100, quantiles=False).fit(training)
        return model.predict

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        timeline = simulate(features, refit, initial_weeks=26)
    write_json(ROOT / "artifacts/monitoring.json", timeline)
    write_json(
        ROOT / "artifacts/monitoring_summary.json",
        {
            "weeks": len(timeline),
            "triggers": sum(row["retrain"] for row in timeline),
            "completed_refits": sum("refit completed" in row["action"] for row in timeline),
            "runtime_seconds": time.perf_counter() - started,
            "warmup_weeks": 26,
            "methodology": "Walk-forward simulation of C2 on all products with available features, with an initial training warmup. Each trigger observes completed sales, waits until that information is available at a later decision cutoff, and refits. This does not automatically promote models into the service.",
        },
    )
    print(f"Simulated {len(timeline)} weeks and {sum(row['retrain'] for row in timeline)} triggers")


if __name__ == "__main__":
    run()
