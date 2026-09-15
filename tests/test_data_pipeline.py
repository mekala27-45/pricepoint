from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pricepoint_data import DataConfig, build_panel, clean, download, ingest, select_universe
from pricepoint_data.pipeline import TRANSACTION_SCHEMA


def transaction(**changes: Any) -> dict[str, Any]:
    return {
        "invoice": "100",
        "product_id": "A",
        "description": "BLUE MUG",
        "quantity": 4.0,
        "price": 2.0,
        "timestamp": datetime(2010, 1, 4, 12),
        "customer_id": "1",
        "country": "United Kingdom",
        **changes,
    }


def transactions(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=TRANSACTION_SCHEMA)


def test_ingest_quarantines_schema_failures_and_preserves_anonymous_sales(tmp_path: Path) -> None:
    path = tmp_path / "input.parquet"
    transactions(
        [
            transaction(),
            transaction(timestamp=None),
            transaction(price=float("nan")),
            transaction(customer_id=None),
            transaction(product_id=""),
        ]
    ).write_parquet(path)
    result = ingest(path)
    assert result.counts == {
        "raw_rows": 5,
        "schema_valid_rows": 2,
        "schema_quarantine_rows": 3,
        "missing_customer_rows": 1,
    }
    assert result.transactions.height + result.quarantine.height == 5


def test_ingest_source_aliases_csv_and_missing_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    path.write_text(
        "Invoice,StockCode,Description,Quantity,Price,InvoiceDate,Customer ID,Country\n"
        "100,1,BLUE MUG,4,2,2010-01-04T12:00:00,1,United Kingdom\n",
        encoding="utf-8",
    )
    assert ingest(path).transactions["product_id"].to_list() == ["1"]
    pl.DataFrame({"unknown": [1]}).write_parquet(tmp_path / "bad.parquet")
    with pytest.raises(ValueError, match="Missing transaction columns"):
        ingest(tmp_path / "bad.parquet")


def test_clean_rules_and_credit_accounting_have_exact_counts() -> None:
    result = clean(
        transactions(
            [
                transaction(quantity=10.0),
                transaction(invoice="C101", quantity=-2.0, timestamp=datetime(2010, 1, 4, 14)),
                transaction(invoice="C102", quantity=-3.0, timestamp=datetime(2010, 1, 11, 14)),
                transaction(invoice="C103", quantity=-8.0, timestamp=datetime(2010, 1, 18, 14)),
                transaction(product_id="POST"),
                transaction(price=0),
                transaction(price=-1),
                transaction(quantity=0),
                transaction(country="France"),
                transaction(invoice="C104", quantity=1),
                transaction(invoice="C105", customer_id=None, quantity=-1),
            ]
        )
    )
    assert result.counts == {
        "input_rows": 11,
        "outside_country_rows": 1,
        "non_product_rows": 1,
        "non_positive_price_rows": 2,
        "zero_quantity_rows": 1,
        "positive_credit_invoice_rows": 1,
        "price_outlier_rows": 0,
        "matched_credit_rows": 3,
        "same_day_cancellation_rows": 1,
        "return_rows": 2,
        "unmatched_credit_rows": 2,
        "partial_credit_rows": 1,
        "sale_rows": 1,
        "clean_rows": 4,
        "quarantine_rows": 8,
    }
    assert result.transactions["quantity"].sum() == 0
    assert result.transactions["event_type"].to_list() == [
        "sale",
        "cancellation",
        "return",
        "return",
    ]
    assert result.quarantine.filter(pl.col("reason") == "unmatched_credit")["quantity"].sum() == -4
    panel = build_panel(result.transactions)
    assert panel["units"].to_list() == [8, -3, -5]
    assert panel["gross_units"].to_list() == [10, 0, 0]
    assert panel["returned_units"].sum() == 10


def test_credit_never_changes_a_previously_observed_week() -> None:
    sale = transaction()
    credit = transaction(invoice="C101", quantity=-2, timestamp=datetime(2010, 2, 1))
    first = build_panel(clean(transactions([sale])).transactions)
    later = build_panel(clean(transactions([sale, credit])).transactions)
    assert first["units"].to_list() == later.head(1)["units"].to_list()


def test_credits_cannot_match_later_sales_or_other_customers() -> None:
    result = clean(
        transactions(
            [
                transaction(invoice="C99", quantity=-4, timestamp=datetime(2010, 1, 1)),
                transaction(),
                transaction(
                    invoice="C101", quantity=-4, customer_id="2", timestamp=datetime(2010, 1, 5)
                ),
            ]
        )
    )
    assert result.counts["unmatched_credit_rows"] == 2
    assert result.transactions["quantity"].sum() == 4


def test_outlier_rule_uses_only_prior_product_prices() -> None:
    rows = [transaction(timestamp=datetime(2010, 1, 4) + timedelta(minutes=i)) for i in range(20)]
    rows += [
        transaction(price=20, timestamp=datetime(2010, 1, 5)),
        transaction(product_id="PRODUCTB", price=20, timestamp=datetime(2010, 1, 5)),
    ]
    result = clean(transactions(rows))
    assert result.counts["price_outlier_rows"] == 1
    assert result.transactions.filter(pl.col("product_id") == "PRODUCTB").height == 1
    before = clean(transactions(rows[:-2])).transactions
    assert before.equals(result.transactions.head(20))


def test_category_uses_first_observed_description() -> None:
    result = clean(
        transactions(
            [
                transaction(),
                transaction(description="XMAS TREE", timestamp=datetime(2010, 2, 1)),
            ]
        )
    )
    assert result.transactions["category"].to_list() == ["kitchen", "kitchen"]


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 3), st.integers(0, 20), st.integers(-20, 40), st.integers(1, 20)),
        min_size=1,
        max_size=80,
    )
)
def test_panel_conserves_units_and_contains_every_week(
    observations: list[tuple[int, int, int, int]],
) -> None:
    rows = [
        transaction(
            product_id=str(product),
            timestamp=datetime(2010, 1, 4) + timedelta(weeks=week),
            quantity=float(quantity),
            price=float(price),
        )
        for product, week, quantity, price in observations
    ]
    # Seed a known positive-price sale for every product before signed accounting events.
    products = {str(row[0]) for row in observations}
    rows += [transaction(product_id=product, quantity=1.0) for product in products]
    source = transactions(rows)
    panel = build_panel(source)
    assert panel["units"].sum() == source["quantity"].sum()
    assert panel.select(pl.struct("product_id", "week").n_unique()).item() == panel.height
    last = max(row[1] for row in observations)
    assert panel.height == len(products) * (last + 1)
    assert panel.filter(pl.col("price").is_null()).is_empty()


def test_panel_zero_weeks_forward_fill_price_without_future_backfill() -> None:
    source = transactions(
        [
            transaction(),
            transaction(timestamp=datetime(2010, 1, 18), quantity=6, price=4),
        ]
    )
    panel = build_panel(source)
    assert panel["units"].to_list() == [4, 0, 6]
    assert panel["price"].to_list() == [2, 2, 4]
    with pytest.raises(ValueError, match="without accepted"):
        build_panel(source.head(0))


def test_modeling_universe_is_selected_from_fit_history_only() -> None:
    panel = pl.DataFrame(
        {
            "product_id": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
            "week": [date(2010, 1, 4), date(2010, 1, 11), date(2010, 1, 18)] * 3,
            "units": [1, 2, 3, 0, 1, 5, 2, 2, 2],
            "price": [1, 2, 3, 1, 2, 3, 1, 1, 2],
        }
    )
    result = select_universe(panel, date(2010, 1, 18), min_sales_weeks=2, min_prices=2)
    assert result.product_ids == ["A"]
    assert result.counts == {
        "considered_products": 3,
        "included_products": 1,
        "too_few_sales_weeks": 1,
        "too_few_prices": 1,
    }
    trimmed = panel.filter(pl.col("week") < date(2010, 1, 18))
    assert result.report.equals(select_universe(trimmed, date(2010, 1, 18), 2, 2).report)


def test_download_validates_fresh_and_cached_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"verified dataset"
    digest = hashlib.sha256(body).hexdigest()
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: io.BytesIO(body))
    target = tmp_path / "raw.xlsx"
    assert download("https://example.test/data", target, digest) == target
    assert download("https://example.test/data", target, digest) == target
    with pytest.raises(ValueError, match="Existing raw"):
        download("https://example.test/data", target, "wrong")
    with pytest.raises(ValueError, match="Downloaded dataset"):
        download("https://example.test/data", tmp_path / "bad.xlsx", "wrong")
    assert not (tmp_path / "bad.xlsx.partial").exists()


def test_config_loads_explicit_nonproduct_codes(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"non_product_codes": ["POST"], "source": {}}', encoding="utf-8")
    assert DataConfig.load(path).non_product_codes == ("POST",)


def test_panel_marks_partial_source_boundary_weeks() -> None:
    panel = build_panel(
        transactions(
            [
                transaction(timestamp=datetime(2009, 12, 1)),
                transaction(timestamp=datetime(2009, 12, 18)),
            ]
        )
    )
    assert panel["is_complete_week"].to_list() == [False, True, False]


def test_manual_lowercase_code_is_explicitly_excluded() -> None:
    result = clean(transactions([transaction(product_id="m"), transaction()]))
    assert result.counts["non_product_rows"] == 1


def test_data_document_counts_match_stored_lineage() -> None:
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / "artifacts/data_report.json").read_text(encoding="utf-8"))
    document = (root / "docs/data.md").read_text(encoding="utf-8")
    published = [
        line.split("|")[1:3]
        for line in document.splitlines()
        if line.startswith("| ")
        and (
            ".raw_rows |" in line
            or line.split("|")[1]
            .strip()
            .startswith(("ingest.", "clean.", "panel_", "gold_", "universe."))
        )
    ]
    assert len(published) >= 25
    for pointer, count in published:
        value = report
        for part in pointer.strip().split("."):
            value = value[part]
        assert count.strip() == f"{value:,}"
    clean_report = report["clean"]
    assert clean_report["clean_rows"] + clean_report["quarantine_rows"] == (
        clean_report["input_rows"] + clean_report["partial_credit_rows"]
    )
