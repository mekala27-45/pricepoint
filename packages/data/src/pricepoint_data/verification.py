"""Reproducible evidence from real data for leakage and implementation skew."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from pricepoint_data.features import FEATURE_NAMES, ServingFeatureStore, batch_features


def verification_pairs(panel: pl.DataFrame) -> list[tuple[str, date]]:
    """Ten temporal cutoffs, fifty products each, round-robin across derived groups."""
    complete = (
        panel.filter(pl.col("is_complete_week")) if "is_complete_week" in panel.columns else panel
    )
    weeks: list[date] = complete["week"].unique().sort().to_list()[4:]
    if len(weeks) < 10:
        raise ValueError("Verification requires at least fourteen complete weeks")
    cutoffs = [weeks[index * (len(weeks) - 1) // 9] for index in range(10)]
    pairs: list[tuple[str, date]] = []
    for cutoff in cutoffs:
        groups: dict[str, list[str]] = defaultdict(list)
        for row in (
            batch_features(panel, cutoff).select("product_id", "category").iter_rows(named=True)
        ):
            groups[str(row["category"])].append(str(row["product_id"]))
        for products in groups.values():
            products.sort(
                key=lambda product: hashlib.sha256(f"{cutoff}|{product}".encode()).hexdigest()
            )
        chosen: list[str] = []
        while len(chosen) < 50:
            added = 0
            for category in sorted(groups):
                if groups[category] and len(chosen) < 50:
                    chosen.append(groups[category].pop())
                    added += 1
            if not added:
                raise ValueError("Verification requires at least fifty products per cutoff")
        pairs.extend((product, cutoff) for product in chosen)
    return pairs


def verify_panel(panel_path: str | Path, destination: str | Path) -> dict[str, dict[str, Any]]:
    """Persist measured evidence, pair definitions and source hash for release claims."""
    source = Path(panel_path)
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    panel = pl.read_parquet(source)
    pairs = verification_pairs(panel)
    full_store = ServingFeatureStore(panel)
    batch_cache: dict[date, dict[str, dict[str, Any]]] = {}
    trimmed_stores: dict[date, ServingFeatureStore] = {}
    trimmed_batches: dict[date, dict[str, dict[str, Any]]] = {}
    maximum_skew = 0.0
    maximum_leakage = 0.0
    corrupt_difference = 0.0
    leakage_pairs: list[tuple[str, date]] = []
    for index, (product, as_of) in enumerate(pairs):
        if as_of not in batch_cache:
            batch_cache[as_of] = {
                str(row["product_id"]): row
                for row in batch_features(panel, as_of).iter_rows(named=True)
            }
        batch = batch_cache[as_of][product]
        serving = full_store.vector(product, float(batch["price"]), as_of)
        maximum_skew = max(
            maximum_skew, *(abs(float(batch[name]) - serving[name]) for name in FEATURE_NAMES)
        )
        # Corrupt a real serving arithmetic rule to prove the same comparator rejects it.
        corrupted = serving.copy()
        corrupted["relative_price"] = round(corrupted["relative_price"], 1)
        corrupt_difference = max(
            corrupt_difference,
            *(abs(float(batch[name]) - corrupted[name]) for name in FEATURE_NAMES),
        )
        if index % 50 >= 20:
            continue
        leakage_pairs.append((product, as_of))
        if as_of not in trimmed_stores:
            trimmed_stores.clear()
            trimmed_batches.clear()
            truncated = panel.filter(pl.col("week") < as_of)
            trimmed_stores[as_of] = ServingFeatureStore(truncated)
            trimmed_batches[as_of] = {
                str(row["product_id"]): row
                for row in batch_features(truncated, as_of).iter_rows(named=True)
            }
        truncated_serving = trimmed_stores[as_of].vector(product, float(batch["price"]), as_of)
        truncated_batch = trimmed_batches[as_of][product]
        maximum_leakage = max(
            maximum_leakage,
            *(abs(float(batch[name]) - float(truncated_batch[name])) for name in FEATURE_NAMES),
            *(abs(serving[name] - truncated_serving[name]) for name in FEATURE_NAMES),
        )
    with source.open("rb") as stream:
        panel_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    common = {
        "panel_sha256": panel_hash,
        "tolerance": 1e-9,
        "sampling": (
            "Ten evenly spaced complete-week cutoffs; fifty hash-ordered products per cutoff, "
            "round-robin across derived categories."
        ),
        "feature_names": list(FEATURE_NAMES),
        "source_panel_rows": panel.height,
    }
    skew = {
        **common,
        "pairs": len(pairs),
        "max_abs_difference": maximum_skew,
        "passed": maximum_skew <= 1e-9,
        "paths": ["Polars batch", "Python ServingFeatureStore"],
        "deliberate_rounding_corruption_max_abs_difference": corrupt_difference,
        "deliberate_corruption_detected": corrupt_difference > 1e-9,
    }
    leakage = {
        **common,
        "pairs": len(leakage_pairs),
        "max_abs_difference": maximum_leakage,
        "passed": maximum_leakage == 0.0,
        "operation": (
            "Delete every panel row at or after as_of, rebuild each independent path, "
            "compare every feature."
        ),
    }
    for name, result in (("skew", skew), ("leakage", leakage)):
        (target / f"{name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pair_definitions = {
        "skew": [{"product_id": product, "as_of": cutoff.isoformat()} for product, cutoff in pairs],
        "leakage": [
            {"product_id": product, "as_of": cutoff.isoformat()}
            for product, cutoff in leakage_pairs
        ],
    }
    (target / "verification_pairs.json").write_text(
        json.dumps(pair_definitions, indent=2), encoding="utf-8"
    )
    return {"skew": skew, "leakage": leakage}
