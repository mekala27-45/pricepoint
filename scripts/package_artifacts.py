"""Freeze evaluated artifacts, assess promotion, and build static demand surfaces."""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import time
import warnings
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import polars as pl
import structlog
from pricepoint_core.config import Settings
from pricepoint_core.schemas import FEATURE_CONTRACT, OptimizeRequest
from pricepoint_data.features import ServingFeatureStore
from pricepoint_models import BaselineModel, CalibratedModel, DemandModel
from pricepoint_models.gates import GateEvidence, evaluate_gates
from pricepoint_models.registry import Registry
from pricepoint_serve.engine import PredictionEngine

from scripts.evaluate import ROOT, write_json


def model_state_fingerprint(model: DemandModel) -> str:
    """Hash fitted state independently of its assigned registry version."""
    normalized = pickle.loads(pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL))
    normalized.version = "unregistered"
    if isinstance(normalized, CalibratedModel):
        normalized.base.version = "unregistered"
    return hashlib.sha256(pickle.dumps(normalized, protocol=pickle.HIGHEST_PROTOCOL)).hexdigest()


def model_identity(
    model: DemandModel,
    *,
    data_sha256: str,
    training_config: dict[str, Any],
    source_sha256: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    """Address artifacts by model content, data, configuration, and source provenance."""
    provenance = {
        "model_state_sha256": model_state_fingerprint(model),
        "data_sha256": data_sha256,
        "training_config": training_config,
        "source_sha256": dict(sorted(source_sha256.items())),
    }
    identity = hashlib.sha256(
        json.dumps(provenance, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()[:24]
    return identity, provenance


def comparable_incumbent(
    incumbent: DemandModel,
    evaluated_baseline: CalibratedModel,
) -> tuple[bool, str]:
    """Only identical non-fitted persistence rules share these historical fold predictions.

    A fitted frozen incumbent cannot borrow metrics from independently fitted
    rolling-fold models. That comparison needs its own untouched future labels.
    The conformal radius is irrelevant to point-forecast WAPE and is excluded.
    """
    if (
        isinstance(incumbent, CalibratedModel)
        and isinstance(incumbent.base, BaselineModel)
        and isinstance(evaluated_baseline.base, BaselineModel)
        and incumbent.base.kind in {"B0", "B1", "B2"}
        and incumbent.base.kind == evaluated_baseline.base.kind
        and incumbent.feature_contract == evaluated_baseline.feature_contract
        and model_state_fingerprint(incumbent.base)
        == model_state_fingerprint(evaluated_baseline.base)
    ):
        return True, "Retained incumbent has identical persistence-rule state and feature contract"
    return False, (
        "Retained incumbent lacks a matching held-out comparison. Fitted models require "
        "dedicated future evaluation; backtest baseline metrics cannot be substituted."
    )


def package() -> None:
    result = pickle.loads((ROOT / ".cache/evaluation.pkl").read_bytes())
    backtest = json.loads((ROOT / "artifacts/backtest.json").read_text())
    panel_path = ROOT / "data/silver/panel.parquet"
    panel = pl.read_parquet(panel_path)
    # Preserve all historical rows used by batch features, including the first partial week.
    (ROOT / "artifacts/serving_panel.parquet").write_bytes(panel_path.read_bytes())
    cutoff = date(2011, 12, 5)
    latest = panel.filter(pl.col("week") < cutoff).sort("week").unique("product_id", keep="last")
    product_rows = {str(row["product_id"]): row for row in latest.iter_rows(named=True)}
    store = ServingFeatureStore(panel)
    eligible = [
        product
        for product, support in result.support.items()
        if product in product_rows
        and support[0] <= product_rows[product]["price"] <= support[1]
        and support[1] - support[0] >= 0.1
    ]
    ranked = (
        result.train_frame.group_by("product_id")
        .agg(pl.col("units").sum())
        .sort(["units", "product_id"], descending=[True, False])["product_id"]
        .to_list()
    )
    chosen: list[str] = []
    for category in sorted(set(row["category"] for row in product_rows.values())):
        chosen.extend(
            [
                product
                for product in ranked
                if product in eligible and product_rows[product]["category"] == category
            ][:4]
        )
    frames = []
    for product in chosen:
        row = product_rows[product]
        vector = store.vector(product, float(row["price"]), cutoff)
        frames.append(
            pl.DataFrame(
                [{"product_id": product, "category": row["category"], "as_of": cutoff, **vector}]
            )
        )
    samples = []
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        for index in range(1100):
            frame = frames[index % len(frames)]
            product = str(frame["product_id"][0])
            started = time.perf_counter()
            vector = store.vector(product, float(frame["price"][0]), cutoff)
            request_frame = pl.DataFrame(
                [
                    {
                        "product_id": product,
                        "category": product_rows[product]["category"],
                        "as_of": cutoff,
                        **vector,
                    }
                ]
            )
            result.model.predict_interval(request_frame)
            if index >= 100:
                samples.append((time.perf_counter() - started) * 1000)
    latency: dict[str, Any] = {
        "samples": len(samples),
        "p50_ms": float(np.percentile(samples, 50)),
        "p95_ms": float(np.percentile(samples, 95)),
        "p99_ms": float(np.percentile(samples, 99)),
        "concurrency": 1,
        "warmup_requests": 100,
        "latency_samples_ms": samples,
        "methodology": "Warm single-candidate prediction in process, Python feature store plus Polars row construction and calibrated LightGBM scoring; excludes HTTP, logging and container overhead.",
    }
    write_json(ROOT / "artifacts/latency-gate.json", latency)
    summary = {row["model"]: row for row in backtest["summary"]}
    incumbent_name = backtest["incumbent_model"]
    category = backtest["category_metrics"]
    skew = json.loads((ROOT / "artifacts/skew.json").read_text())
    registry = Registry(ROOT / "artifacts/registry")
    retained_version = registry.incumbent_version()
    comparable, comparison_reason = (
        comparable_incumbent(registry.load(retained_version), result.incumbent)
        if retained_version is not None
        else (True, "First incumbent bootstrap uses the measured backtest baseline")
    )
    evidence = GateEvidence(
        candidate_wape=summary["C2"]["wape"]["mean"],
        incumbent_wape=summary[incumbent_name]["wape"]["mean"] if comparable else None,
        candidate_category_wape={
            row["category"]: row["wape"] for row in category if row["model"] == "C2"
        },
        incumbent_category_wape=(
            {row["category"]: row["wape"] for row in category if row["model"] == incumbent_name}
            if comparable
            else {}
        ),
        latency_p99_ms=latency["p99_ms"],
        latency_samples=len(samples),
        coverage=backtest["coverage"]["conformal"],
        coverage_samples=backtest["coverage"]["test_rows"],
        coverage_split="held_out_test",
        candidate_schema=result.model.feature_contract,
        serving_schema=FEATURE_CONTRACT,
        skew_max_abs=skew["max_abs_difference"],
        skew_pairs=skew["pairs"],
    )
    gates = evaluate_gates(evidence)
    fingerprint = hashlib.sha256((ROOT / "data/gold/features.parquet").read_bytes()).hexdigest()
    sources = [
        ROOT / "uv.lock",
        ROOT / "pyproject.toml",
        ROOT / "config/data.json",
        *sorted((ROOT / "packages/models/src").rglob("*.py")),
        *sorted((ROOT / "packages/data/src").rglob("*.py")),
        ROOT / "packages/core/src/pricepoint_core/schemas.py",
    ]
    source_hashes = {
        str(path.relative_to(ROOT).as_posix()): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
    }
    baseline_identity, baseline_provenance = model_identity(
        result.incumbent,
        data_sha256=fingerprint,
        training_config=backtest["methodology"],
        source_sha256=source_hashes,
    )
    candidate_identity, candidate_provenance = model_identity(
        result.model,
        data_sha256=fingerprint,
        training_config=backtest["methodology"],
        source_sha256=source_hashes,
    )
    metadata = {
        "support": result.support,
        "as_of": cutoff.isoformat(),
        "minimum_as_of": backtest["split_metadata"][-1]["decision_as_of"],
        "data_fingerprint": fingerprint,
        "target": "gross units",
    }
    final_test = backtest["split_metadata"][-1]["test_week"].replace("-", "")
    baseline_version = f"{incumbent_name}-{final_test}-{baseline_identity}"
    candidate_version = f"C2-{final_test}-{candidate_identity}"
    registry.register(
        result.incumbent,
        summary[incumbent_name],
        version=baseline_version,
        metadata={**metadata, "role": "baseline", "provenance": baseline_provenance},
    )
    if registry.incumbent_version() is None:
        registry.bootstrap(
            baseline_version, reason="Best measured baseline across expanding temporal folds"
        )
    registry.register(
        result.model,
        summary["C2"],
        version=candidate_version,
        metadata={**metadata, "role": "challenger", "provenance": candidate_provenance},
    )
    assessment = registry.record_assessment(
        candidate_version,
        gates,
        metadata={
            "backtest_sha256": hashlib.sha256(
                (ROOT / "artifacts/backtest.json").read_bytes()
            ).hexdigest(),
            "latency_sha256": hashlib.sha256(
                (ROOT / "artifacts/latency-gate.json").read_bytes()
            ).hexdigest(),
            "skew_sha256": hashlib.sha256((ROOT / "artifacts/skew.json").read_bytes()).hexdigest(),
            "compared_incumbent": retained_version or baseline_version,
            "incumbent_comparable": comparable,
            "comparison_reason": comparison_reason,
        },
    )
    if all(gate.passed for gate in gates):
        registry.promote(candidate_version, gates)
    write_json(
        ROOT / "artifacts/promotion.json",
        {
            "candidate": candidate_version,
            "incumbent": registry.incumbent_version(),
            "promoted": registry.incumbent_version() == candidate_version,
            "assessment_id": assessment["assessment_id"],
            "incumbent_comparable": comparable,
            "comparison_reason": comparison_reason,
            "gates": [gate.to_dict() for gate in gates],
        },
    )
    engine = PredictionEngine(
        Settings(registry=registry.root, panel=ROOT / "artifacts/serving_panel.parquet")
    )
    chosen = [
        product
        for product in chosen
        if product in engine.support
        and engine.support[product][0]
        <= product_rows[product]["price"]
        <= engine.support[product][1]
    ]
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    products: list[dict[str, Any]] = []
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        for product in chosen:
            row = product_rows[product]
            lo, hi = engine.support[product]
            current = float(row["price"])
            low_penny, high_penny = int(np.ceil(lo * 100)), int(np.floor(hi * 100))
            # Penny grid allows local interpolation, sparse surfaces are explicitly labeled.
            prices = sorted(
                set(
                    [current]
                    + [
                        round(value / 100, 2)
                        for value in np.linspace(
                            low_penny, high_penny, min(200, high_penny - low_penny + 1)
                        )
                    ]
                )
            )
            curve = engine.curve(product, prices, cutoff)
            recommendation = engine.optimize(
                OptimizeRequest(
                    product_id=product,
                    current_price=current,
                    cost_floor=round(lo * 0.6, 2),
                    max_markdown=0.5,
                    inventory=100.0,
                    as_of=cutoff,
                )
            )
            products.append(
                {
                    "id": product,
                    "name": row["description"],
                    "category": row["category"],
                    "current_price": current,
                    "min_price": prices[0],
                    "max_price": prices[-1],
                    "as_of": cutoff.isoformat(),
                    "curve": [point.model_dump() for point in curve],
                    "recommended_price": recommendation["recommended_price"],
                }
            )
    engine.save_shadow(ROOT / "artifacts/shadow_observations.json")
    disagreements = [row["absolute_disagreement"] for row in engine.shadow_observations]
    write_json(
        ROOT / "artifacts/shadow.json",
        {
            "samples": len(disagreements),
            "p50_units": float(np.percentile(disagreements, 50)) if disagreements else None,
            "p95_units": float(np.percentile(disagreements, 95)) if disagreements else None,
            "p99_units": float(np.percentile(disagreements, 99)) if disagreements else None,
            "mean_units": float(np.mean(disagreements)) if disagreements else None,
            "methodology": "Incumbent and candidate scored the same precomputed product-price grid; absolute disagreement in gross units, descriptive grid distribution rather than traffic-weighted production statistics.",
        },
    )
    labels = {
        "B0": "Naive",
        "B1": "Seasonal naive",
        "B2": "Trailing mean",
        "B3": "Global log-log",
        "C1": "Category log-log",
        "C2": "LightGBM Tweedie",
    }
    splits = {split["fold"]: split for split in backtest["split_metadata"]}
    promoted = engine.incumbent.version == candidate_version
    candidate_status = "C2 is the incumbent after promotion" if promoted else "C2 was not promoted"
    bundle = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "dataset": "UCI Online Retail II",
            "model_version": engine.incumbent.version,
            "nominal_coverage": 0.9,
            "source_note": (
                f"Measured {engine.incumbent.name} incumbent. {candidate_status}. "
                "Gross weekly demand; inferred product groups. Historical, observational "
                "evidence. Static curves interpolate a stored price grid."
            ),
        },
        "products": products,
        "backtest": {
            "summary": [
                {
                    "model": row["model"],
                    "label": labels[row["model"]],
                    "wape_mean": row["wape"]["mean"],
                    "wape_std": row["wape"]["std"],
                    "mase_mean": row["mase"]["mean"],
                    "mase_std": row["mase"]["std"],
                }
                for row in backtest["summary"]
            ],
            "folds": [
                {**row, "train_end": splits[row["fold"]]["fit_end"], "test_start": row["test_week"]}
                for row in backtest["folds"]
            ],
            "last_fold": [
                {key: row[key] for key in ("model", "product_id", "actual", "predicted")}
                for row in result.artifacts["predictions"]
                if row["fold"] == 8
            ],
        },
        "elasticity": [
            {**row, "observations": row.get("observations", row.get("rows", 0))}
            for row in backtest["elasticity"]
        ],
        "monitoring": json.loads((ROOT / "artifacts/monitoring.json").read_text())
        if (ROOT / "artifacts/monitoring.json").exists()
        else [],
    }
    write_json(ROOT / "web/public/bundle.json", bundle)
    write_json(
        ROOT / "artifacts/demo_metadata.json",
        {
            "products": len(products),
            "surface_points": sum(len(p["curve"]) for p in products),
            "incumbent": engine.incumbent.version,
            "candidate": candidate_version,
        },
    )
    print(
        json.dumps(
            {
                "incumbent": registry.incumbent_version(),
                "gates": [{"name": gate.name, "passed": gate.passed} for gate in gates],
                "products": len(products),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    package()
