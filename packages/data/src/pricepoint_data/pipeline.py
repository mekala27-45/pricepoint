"""Deterministic ingestion, explicit credit accounting, and product-week panels."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

import polars as pl

DEFAULT_NON_PRODUCT_CODES = (
    "POST",
    "DOT",
    "M",
    "m",
    "D",
    "C2",
    "C3",
    "GIFT",
    "BANK CHARGES",
    "AMAZONFEE",
    "B",
    "S",
    "ADJUST",
    "ADJUST2",
    "TEST001",
    "TEST002",
    "CRUK",
    "DCGSSBOY",
    "DCGSSGIRL",
    "PADS",
    "gift_0001_10",
    "gift_0001_20",
    "gift_0001_30",
    "gift_0001_40",
    "gift_0001_50",
)

TRANSACTION_SCHEMA = {
    "invoice": pl.String,
    "product_id": pl.String,
    "description": pl.String,
    "quantity": pl.Float64,
    "price": pl.Float64,
    "timestamp": pl.Datetime("us"),
    "customer_id": pl.String,
    "country": pl.String,
}


@dataclass(frozen=True)
class DataConfig:
    """Cleaning thresholds are configuration, never inferred from future rows."""

    country: str = "United Kingdom"
    non_product_codes: tuple[str, ...] = DEFAULT_NON_PRODUCT_CODES
    outlier_min_history: int = 20
    outlier_history: int = 100
    outlier_ratio: float = 5.0
    min_sales_weeks: int = 20
    min_distinct_prices: int = 3

    @classmethod
    def load(cls, path: str | Path) -> DataConfig:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        values.pop("source", None)
        if "non_product_codes" in values:
            values["non_product_codes"] = tuple(values["non_product_codes"])
        return cls(**values)


@dataclass
class IngestResult:
    transactions: pl.DataFrame
    quarantine: pl.DataFrame
    counts: dict[str, int]


@dataclass
class CleanResult:
    transactions: pl.DataFrame
    quarantine: pl.DataFrame
    counts: dict[str, int]


@dataclass
class UniverseResult:
    product_ids: list[str]
    report: pl.DataFrame
    counts: dict[str, int]


def download(url: str, destination: str | Path, sha256: str) -> Path:
    """Download atomically and refuse bytes whose SHA-256 differs from the pin."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.file_digest(target.open("rb"), "sha256").hexdigest() != sha256:
            raise ValueError("Existing raw dataset SHA-256 does not match the configured pin")
        return target
    temporary = target.with_suffix(target.suffix + ".partial")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest() != sha256:
            raise ValueError("Downloaded dataset SHA-256 does not match the configured pin")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _normalize(frame: pl.DataFrame) -> pl.DataFrame:
    aliases = {
        "Invoice": "invoice",
        "InvoiceNo": "invoice",
        "StockCode": "product_id",
        "Description": "description",
        "Quantity": "quantity",
        "Price": "price",
        "UnitPrice": "price",
        "InvoiceDate": "timestamp",
        "Customer ID": "customer_id",
        "CustomerID": "customer_id",
        "Country": "country",
    }
    frame = frame.rename({key: value for key, value in aliases.items() if key in frame.columns})
    missing = set(TRANSACTION_SCHEMA) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing transaction columns: {sorted(missing)}")
    timestamp = pl.col("timestamp")
    if frame.schema["timestamp"] == pl.String:
        timestamp = timestamp.str.to_datetime(strict=False)
    return frame.select(
        pl.col("invoice").cast(pl.String).str.strip_chars().str.replace(r"\.0$", ""),
        pl.col("product_id").cast(pl.String).str.strip_chars().str.replace(r"\.0$", ""),
        pl.col("description").cast(pl.String).fill_null("").str.strip_chars(),
        pl.col("quantity").cast(pl.Float64, strict=False),
        pl.col("price").cast(pl.Float64, strict=False),
        timestamp.cast(pl.Datetime("us"), strict=False),
        pl.col("customer_id").cast(pl.String).str.replace(r"\.0$", ""),
        pl.col("country").cast(pl.String).fill_null(""),
    )


def ingest(path: str | Path) -> IngestResult:
    """Read all workbook sheets; quarantine malformed rows without losing lineage."""
    source = Path(path)
    if source.suffix == ".parquet":
        raw = pl.read_parquet(source)
    elif source.suffix == ".csv":
        raw = pl.read_csv(source, infer_schema_length=10000, try_parse_dates=True)
    else:
        sheets = pl.read_excel(source, sheet_id=0, engine="calamine", infer_schema_length=None)
        if isinstance(sheets, pl.DataFrame):
            raw = sheets
        else:
            raw = pl.concat(
                [_normalize(sheet) for sheet in sheets.values()], how="vertical_relaxed"
            )
    normalized = _normalize(raw).with_row_index("source_row")
    invalid = (
        pl.col("timestamp").is_null()
        | pl.col("quantity").is_null()
        | ~pl.col("quantity").is_finite()
        | pl.col("price").is_null()
        | ~pl.col("price").is_finite()
        | pl.col("invoice").is_null()
        | pl.col("product_id").is_null()
        | (pl.col("product_id").str.len_chars() == 0)
        | (pl.col("invoice").str.len_chars() == 0)
    )
    quarantine = normalized.filter(invalid).with_columns(pl.lit("invalid_schema").alias("reason"))
    accepted = normalized.filter(~invalid)
    return IngestResult(
        accepted,
        quarantine,
        {
            "raw_rows": raw.height,
            "schema_valid_rows": accepted.height,
            "schema_quarantine_rows": quarantine.height,
            "missing_customer_rows": accepted.filter(pl.col("customer_id").is_null()).height,
        },
    )


def _category(description: str) -> str:
    """Transparent description vocabulary; UCI does not provide categories."""
    text = description.upper()
    rules = (
        ("seasonal", ("CHRISTMAS", "XMAS", "EASTER", "ADVENT", "SANTA")),
        ("kitchen", ("MUG", "CUP", "TEA", "PLATE", "BOWL", "KITCHEN", "CAKE", "LUNCH")),
        ("lighting", ("CANDLE", "LIGHT", "LANTERN", "T-LIGHT", "T LIGHT")),
        ("bags", ("BAG", "PURSE", "WALLET", "TOTE")),
        ("garden", ("GARDEN", "FLOWER", "PLANT", "WATERING")),
        ("stationery", ("PENCIL", "PEN ", "NOTEBOOK", "CARD", "WRAP", "STICKER")),
        ("decor", ("HEART", "HANGING", "FRAME", "CLOCK", "DOORMAT", "CUSHION")),
        ("toys", ("TOY", "GAME", "DOLL", "JIGSAW", "CHILDREN")),
    )
    for category, words in rules:
        if any(word in text for word in words):
            return category
    return "other"


@dataclass
class _Sale:
    quantity: float
    timestamp: datetime
    invoice: str


def clean(frame: pl.DataFrame, config: DataConfig | None = None) -> CleanResult:
    """Match credits against prior purchases and book their effect when observed."""
    cfg = config or DataConfig()
    working = _normalize(frame)
    if "source_row" in frame.columns:
        working = working.with_columns(frame["source_row"])
    else:
        working = working.with_row_index("source_row")
    counts: dict[str, int] = {"input_rows": working.height}
    quarantines: list[pl.DataFrame] = []
    filters = (
        ("outside_country", pl.col("country") != cfg.country),
        ("non_product", pl.col("product_id").is_in(cfg.non_product_codes)),
        ("non_positive_price", (pl.col("price") <= 0) | ~pl.col("price").is_finite()),
        ("zero_quantity", pl.col("quantity") == 0),
        (
            "positive_credit_invoice",
            pl.col("invoice").str.starts_with("C") & (pl.col("quantity") > 0),
        ),
    )
    for reason, condition in filters:
        rejected = working.filter(condition).with_columns(pl.lit(reason).alias("reason"))
        counts[reason + "_rows"] = rejected.height
        quarantines.append(rejected)
        working = working.filter(~condition)
    sales: dict[tuple[str, str, float, str], deque[_Sale]] = defaultdict(deque)
    history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=cfg.outlier_history))
    output: list[dict[str, Any]] = []
    rejected_events: list[dict[str, Any]] = []
    categories: dict[str, str] = {}
    counts.update(
        {
            "price_outlier_rows": 0,
            "matched_credit_rows": 0,
            "same_day_cancellation_rows": 0,
            "return_rows": 0,
            "unmatched_credit_rows": 0,
            "partial_credit_rows": 0,
            "sale_rows": 0,
        }
    )
    for row in working.sort(["timestamp", "source_row"]).iter_rows(named=True):
        product = str(row["product_id"])
        quantity = float(row["quantity"])
        price = float(row["price"])
        timestamp = row["timestamp"]
        customer = str(row["customer_id"] or "")
        key = (customer, product, price, str(row["country"]))
        if quantity > 0:
            prices = history[product]
            if len(prices) >= cfg.outlier_min_history:
                typical = median(prices)
                if price < typical / cfg.outlier_ratio or price > typical * cfg.outlier_ratio:
                    rejected_events.append(dict(row, reason="price_outlier"))
                    counts["price_outlier_rows"] += 1
                    continue
            prices.append(price)
            if customer:
                sales[key].append(_Sale(quantity, timestamp, str(row["invoice"])))
            categories.setdefault(product, _category(str(row["description"])))
            output.append(
                dict(row, event_type="sale", matched_invoice="", category=categories[product])
            )
            counts["sale_rows"] += 1
            continue
        remaining = -quantity
        matched = 0.0
        matched_invoices: list[str] = []
        all_same_day = True
        available = sales[key] if customer else deque()
        while remaining > 1e-9 and available:
            sale = available[-1]
            take = min(remaining, sale.quantity)
            remaining -= take
            sale.quantity -= take
            matched += take
            matched_invoices.append(sale.invoice)
            all_same_day = all_same_day and sale.timestamp.date() == timestamp.date()
            if sale.quantity <= 1e-9:
                available.pop()
        if matched > 0:
            is_cancel = str(row["invoice"]).startswith("C") and all_same_day
            kind = "cancellation" if is_cancel else "return"
            output.append(
                dict(
                    row,
                    quantity=-matched,
                    event_type=kind,
                    matched_invoice="|".join(matched_invoices),
                    category=categories[product],
                )
            )
            counts["matched_credit_rows"] += 1
            counts["same_day_cancellation_rows" if is_cancel else "return_rows"] += 1
        if remaining > 1e-9:
            rejected_events.append(dict(row, quantity=-remaining, reason="unmatched_credit"))
            counts["unmatched_credit_rows"] += 1
            counts["partial_credit_rows"] += int(matched > 0)
    extra = {"event_type": pl.String, "matched_invoice": pl.String, "category": pl.String}
    accepted = pl.DataFrame(output, schema={**working.schema, **extra})
    if rejected_events:
        quarantines.append(
            pl.DataFrame(rejected_events, schema={**working.schema, "reason": pl.String})
        )
    quarantine = pl.concat(quarantines, how="diagonal_relaxed")
    counts["clean_rows"] = accepted.height
    counts["quarantine_rows"] = quarantine.height
    return CleanResult(accepted, quarantine, counts)


def build_panel(cleaned: pl.DataFrame, end_week: date | None = None) -> pl.DataFrame:
    """Fill every observable product-week; prices use earlier sales only."""
    if cleaned.is_empty():
        raise ValueError("Cannot build a panel without accepted transactions")
    events = cleaned.with_columns(pl.col("timestamp").dt.truncate("1w").dt.date().alias("week"))
    coverage_start = events["timestamp"].min()
    coverage_end = events["timestamp"].max()
    if not isinstance(coverage_start, datetime) or not isinstance(coverage_end, datetime):
        raise ValueError("Transaction coverage must have valid timestamps")
    if "category" not in events.columns:
        events = events.with_columns(pl.lit("other").alias("category"))
    metadata = (
        events.sort("timestamp")
        .group_by("product_id")
        .agg(
            pl.col("category").first(),
            pl.col("description").first(),
            pl.col("week").min().alias("first_week"),
        )
    )
    last_week = end_week or events["week"].max()
    if not isinstance(last_week, date):
        raise ValueError("Panel end must be a date")
    grid = (
        metadata.with_columns(
            pl.date_ranges("first_week", pl.lit(last_week), interval="1w").alias("week"),
        )
        .explode("week", empty_as_null=True)
        .drop("first_week")
    )
    weekly = events.group_by(["product_id", "week"]).agg(
        pl.col("quantity").sum().alias("units"),
        pl.col("quantity").clip(lower_bound=0).sum().alias("gross_units"),
        (-pl.col("quantity").clip(upper_bound=0)).sum().alias("returned_units"),
        (pl.col("price") * pl.col("quantity")).sum().alias("net_revenue"),
        pl.col("price").filter(pl.col("quantity") > 0).median().alias("price"),
    )
    return (
        grid.join(weekly, on=["product_id", "week"], how="left")
        .sort(["product_id", "week"])
        .with_columns(
            pl.col("units", "gross_units", "returned_units", "net_revenue").fill_null(0.0),
            pl.col("price").forward_fill().over("product_id"),
            (
                (pl.col("week") >= coverage_start.date())
                & (pl.col("week") + pl.duration(days=6) <= coverage_end.date())
            ).alias("is_complete_week"),
        )
        .filter(pl.col("price").is_not_null())
    )


def select_universe(
    panel: pl.DataFrame,
    fit_before: date,
    min_sales_weeks: int = 20,
    min_prices: int = 3,
) -> UniverseResult:
    """Select products using fit history only, including each exclusion reason."""
    past = panel.filter(pl.col("week") < fit_before)
    demand = "gross_units" if "gross_units" in past.columns else "units"
    report = (
        past.group_by("product_id")
        .agg(
            (pl.col(demand) > 0).sum().alias("sales_weeks"),
            pl.col("price").filter(pl.col(demand) > 0).n_unique().alias("distinct_prices"),
        )
        .with_columns(
            pl.when(pl.col("sales_weeks") < min_sales_weeks)
            .then(pl.lit("too_few_sales_weeks"))
            .when(pl.col("distinct_prices") < min_prices)
            .then(pl.lit("too_few_prices"))
            .otherwise(pl.lit("included"))
            .alias("reason"),
        )
        .sort("product_id")
    )
    products = report.filter(pl.col("reason") == "included")["product_id"].to_list()
    counts = {"considered_products": report.height, "included_products": len(products)}
    for reason in ("too_few_sales_weeks", "too_few_prices"):
        counts[reason] = report.filter(pl.col("reason") == reason).height
    return UniverseResult(products, report, counts)
