"""Build raw, bronze, silver and gold layers with a lineage report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pricepoint_data import DataConfig, build_panel, clean, ingest, make_features, select_universe

ROOT = Path(__file__).resolve().parents[1]


def build_data() -> None:
    config = DataConfig.load(ROOT / "config/data.json")
    raw = ROOT / "data/raw/online_retail_II.xlsx"
    checksum = hashlib.sha256(raw.read_bytes()).hexdigest()
    expected = "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980"
    if checksum != expected:
        raise ValueError("Raw workbook checksum mismatch")
    for stage in ("bronze", "silver", "gold", "quarantine"):
        (ROOT / "data" / stage).mkdir(parents=True, exist_ok=True)
    print("Ingesting both workbook sheets", flush=True)
    ingested = ingest(raw)
    ingested.transactions.write_parquet(ROOT / "data/bronze/transactions.parquet")
    ingested.quarantine.write_parquet(ROOT / "data/quarantine/schema.parquet")
    print(f"Ingest counts: {ingested.counts}", flush=True)
    cleaned = clean(ingested.transactions, config)
    cleaned.transactions.write_parquet(ROOT / "data/silver/transactions_clean.parquet")
    cleaned.quarantine.write_parquet(ROOT / "data/quarantine/cleaning.parquet")
    print(f"Clean counts: {cleaned.counts}", flush=True)
    panel = build_panel(cleaned.transactions)
    panel.write_parquet(ROOT / "data/silver/panel.parquet")
    print(f"Panel rows: {panel.height}", flush=True)
    features = make_features(panel)
    features.write_parquet(ROOT / "data/gold/features.parquet")
    universe = select_universe(
        panel, panel["week"].max(), config.min_sales_weeks, config.min_distinct_prices
    )
    report = {
        "source": "UCI Online Retail II",
        "sha256": checksum,
        "ingest": ingested.counts,
        "clean": cleaned.counts,
        "panel_rows": panel.height,
        "panel_products": panel["product_id"].n_unique(),
        "panel_weeks": panel["week"].n_unique(),
        "gold_rows": features.height,
        "universe": universe.counts,
        "target": "gross units; returns retained separately",
    }
    (ROOT / "artifacts/data_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    universe.report.write_parquet(ROOT / "artifacts/universe.parquet")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    build_data()
