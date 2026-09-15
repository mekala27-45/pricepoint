"""Independent Polars batch and ordinary-Python serving feature implementations."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from statistics import fmean, median, pstdev
from typing import Any

import polars as pl

FEATURE_NAMES = (
    "price",
    "relative_price",
    "log_price",
    "lag1",
    "lag2",
    "lag4",
    "lag52",
    "mean4",
    "std4",
    "weeks_since_change",
    "last_change",
    "category_mean",
    "week_sin",
    "week_cos",
    "holiday_distance",
    "age_weeks",
    "zero_fraction",
    "trend",
)


class PointInTimeFrame:
    """A materialized view whose exclusive time boundary cannot be extended."""

    def __init__(self, frame: pl.DataFrame, as_of: date, time_column: str = "week") -> None:
        if time_column not in frame.columns:
            raise ValueError(f"Missing time column: {time_column}")
        self.as_of = as_of
        self.time_column = time_column
        self.__past = frame.filter(pl.col(time_column) < as_of)

    def collect(self) -> pl.DataFrame:
        return self.__past.clone()

    def before(self, cutoff: date) -> PointInTimeFrame:
        if cutoff > self.as_of:
            raise ValueError("A point-in-time view cannot extend its original cutoff")
        return PointInTimeFrame(self.__past, cutoff, self.time_column)

    def at(self, when: date) -> pl.DataFrame:
        if when >= self.as_of:
            raise ValueError("Reading at or after as_of is forbidden")
        return self.__past.filter(pl.col(self.time_column) == when)


def _easter(year: int) -> date:
    """Gregorian computus, a deterministic calendar input shared by both paths."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    length = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * length) // 451
    month, day = divmod(h + length - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _bank_holidays(year: int) -> list[date]:
    def next_monday(day: date) -> date:
        return day + timedelta(days=(7 - day.weekday()) % 7)

    new_year = date(year, 1, 1)
    if new_year.weekday() >= 5:
        new_year = next_monday(new_year)
    christmas = date(year, 12, 25)
    boxing = date(year, 12, 26)
    occupied = {d for d in (christmas, boxing) if d.weekday() < 5}
    substitutions: list[date] = []
    for holiday in (christmas, boxing):
        if holiday.weekday() < 5:
            continue
        observed = next_monday(holiday)
        while observed in occupied:
            observed += timedelta(days=1)
        occupied.add(observed)
        substitutions.append(observed)
    easter = _easter(year)
    holidays = [
        new_year,
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        next_monday(date(year, 5, 1)),
        date(year, 5, 31) - timedelta(days=date(year, 5, 31).weekday()),
        date(year, 8, 31) - timedelta(days=date(year, 8, 31).weekday()),
        *occupied,
        *substitutions,
    ]
    if year == 2011:
        holidays.append(date(2011, 4, 29))
    return holidays


def holiday_distance(day: date) -> float:
    """Days to nearest observed England and Wales bank holiday."""
    return float(
        min(
            abs((holiday - day).days)
            for year in (day.year - 1, day.year, day.year + 1)
            for holiday in _bank_holidays(year)
        )
    )


def batch_features(panel: pl.DataFrame, as_of: date) -> pl.DataFrame:
    """Compute training vectors in Polars using strictly earlier weekly rows."""
    past = PointInTimeFrame(panel, as_of).collect().sort(["product_id", "week"])
    if past.is_empty():
        return pl.DataFrame(
            schema={
                "product_id": pl.String,
                "category": pl.String,
                "as_of": pl.Date,
                **dict.fromkeys(FEATURE_NAMES, pl.Float64),
            }
        )
    demand = "gross_units" if "gross_units" in past.columns else "units"
    past = past.with_columns(
        pl.col(demand).cast(pl.Float64).alias("_demand"),
        pl.col("price").shift(1).over("product_id").alias("_previous_price"),
    ).with_columns(
        (
            pl.col("_previous_price").is_not_null()
            & ((pl.col("price") - pl.col("_previous_price")).abs() > 1e-10)
        ).alias("_changed"),
    )
    recent4 = pl.col("week") >= as_of - timedelta(weeks=4)
    recent13 = pl.col("week") >= as_of - timedelta(weeks=13)
    expressions = [
        pl.col("category").first(),
        pl.col("price").last().alias("price"),
        pl.col("week").first().alias("_first_week"),
        pl.col("price")
        .filter(recent13)
        .median()
        .fill_null(pl.col("price").last())
        .alias("_median_price"),
        pl.col("_demand").filter(recent4).mean().fill_null(0).alias("mean4"),
        pl.col("_demand").filter(recent4).std(ddof=0).fill_null(0).alias("std4"),
        pl.col("week").filter(pl.col("_changed")).last().alias("_last_change_week"),
        ((pl.col("price") / pl.col("_previous_price")) - 1)
        .filter(pl.col("_changed"))
        .last()
        .fill_null(0)
        .alias("last_change"),
        (pl.col("_demand") == 0).filter(recent13).mean().fill_null(0).alias("zero_fraction"),
    ]
    for lag in (1, 2, 4, 52):
        expressions.append(
            pl.col("_demand")
            .filter(pl.col("week") == as_of - timedelta(weeks=lag))
            .first()
            .fill_null(0)
            .alias(f"lag{lag}")
        )
    target = as_of + timedelta(weeks=1)
    phase = 2 * math.pi * target.isocalendar().week / 52.1775
    result = (
        past.group_by("product_id")
        .agg(expressions)
        .with_columns(
            (pl.col("price") / pl.col("_median_price")).alias("relative_price"),
            pl.col("price").log().alias("log_price"),
            (
                (
                    pl.lit(as_of) - pl.col("_last_change_week").fill_null(pl.col("_first_week"))
                ).dt.total_days()
                / 7
            ).alias("weeks_since_change"),
            ((pl.lit(as_of) - pl.col("_first_week")).dt.total_days() / 7).alias("age_weeks"),
            pl.lit(as_of).alias("as_of"),
            pl.lit(math.sin(phase)).alias("week_sin"),
            pl.lit(math.cos(phase)).alias("week_cos"),
            pl.lit(holiday_distance(target)).alias("holiday_distance"),
            pl.lit((target - date(2009, 1, 5)).days / 7).alias("trend"),
        )
        .with_columns(
            pl.when(pl.len().over("category") > 1)
            .then(
                (pl.col("mean4").sum().over("category") - pl.col("mean4"))
                / (pl.len().over("category") - 1)
            )
            .otherwise(0.0)
            .alias("category_mean"),
        )
    )
    return result.select(
        "product_id",
        "category",
        "as_of",
        *[pl.col(name).cast(pl.Float64) for name in FEATURE_NAMES],
    ).sort("product_id")


def feature_vector(
    panel: pl.DataFrame, product_id: str, price: float, as_of: date
) -> dict[str, float]:
    """Serving implementation uses Python reductions, never batch expressions."""
    return ServingFeatureStore(panel).vector(product_id, price, as_of)


HistoryRow = tuple[date, float, float, str]


class ServingFeatureStore:
    """Immutable Python index loaded once with bounded, cutoff-specific caches."""

    def __init__(self, panel: pl.DataFrame) -> None:
        demand = "gross_units" if "gross_units" in panel.columns else "units"
        self._histories: dict[str, list[HistoryRow]] = {}
        self._contexts: dict[date, tuple[dict[str, float], dict[str, list[float]]]] = {}
        self._vectors: dict[tuple[str, date], dict[str, float]] = {}
        columns = ["product_id", "category", "week", demand, "price"]
        for pid, category, week, units, price in panel.select(columns).iter_rows():
            self._histories.setdefault(str(pid), []).append(
                (week, float(units), float(price), str(category))
            )
        for history in self._histories.values():
            history.sort(key=lambda row: row[0])

    def _category_context(self, as_of: date) -> tuple[dict[str, float], dict[str, list[float]]]:
        if as_of in self._contexts:
            return self._contexts[as_of]
        means: dict[str, float] = {}
        category_values: dict[str, list[float]] = {}
        earliest = as_of - timedelta(weeks=4)
        for product, history in self._histories.items():
            if history[0][0] >= as_of:
                continue
            values = [row[1] for row in history if earliest <= row[0] < as_of]
            means[product] = fmean(values) if values else 0.0
            category_values.setdefault(history[0][3], []).append(means[product])
        if len(self._contexts) >= 16:
            self._contexts.pop(next(iter(self._contexts)))
        self._contexts[as_of] = (means, category_values)
        return means, category_values

    def _base_vector(self, product_id: str, as_of: date) -> dict[str, float]:
        key = (product_id, as_of)
        if key in self._vectors:
            return self._vectors[key]
        own = [row for row in self._histories.get(product_id, []) if row[0] < as_of]
        if not own:
            raise ValueError(f"No history available for product {product_id} before {as_of}")
        means, category_values = self._category_context(as_of)
        values = category_values[own[0][3]]
        other_mean = (
            (math.fsum(values) - means[product_id]) / (len(values) - 1) if len(values) > 1 else 0.0
        )
        vector = _python_vector(own, own[-1][2], as_of, other_mean)
        if len(self._vectors) >= 65536:
            self._vectors.pop(next(iter(self._vectors)))
        self._vectors[key] = vector
        return vector

    def vector(self, product_id: str, price: float, as_of: date) -> dict[str, float]:
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Candidate price must be finite and positive")
        vector = self._base_vector(product_id, as_of).copy()
        typical = vector["price"] / vector["relative_price"]
        vector["price"] = price
        vector["relative_price"] = price / typical
        vector["log_price"] = math.log(price)
        return vector


def _python_vector(
    own: list[HistoryRow],
    price: float,
    as_of: date,
    category_mean: float,
) -> dict[str, float]:
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Candidate price must be finite and positive")
    first_week = own[0][0]
    by_week = {row[0]: row[1] for row in own}
    four = [row[1] for row in own if row[0] >= as_of - timedelta(weeks=4)]
    thirteen = [row for row in own if row[0] >= as_of - timedelta(weeks=13)]
    last_change = 0.0
    changed_week = first_week
    for previous, current in zip(own, own[1:], strict=False):
        if abs(current[2] - previous[2]) > 1e-10:
            last_change = current[2] / previous[2] - 1.0
            changed_week = current[0]
    typical_price = median(row[2] for row in thirteen) if thirteen else own[-1][2]
    target = as_of + timedelta(weeks=1)
    phase = 2.0 * math.pi * target.isocalendar().week / 52.1775
    vector = {
        "price": price,
        "relative_price": price / typical_price,
        "log_price": math.log(price),
        "lag1": by_week.get(as_of - timedelta(weeks=1), 0.0),
        "lag2": by_week.get(as_of - timedelta(weeks=2), 0.0),
        "lag4": by_week.get(as_of - timedelta(weeks=4), 0.0),
        "lag52": by_week.get(as_of - timedelta(weeks=52), 0.0),
        "mean4": fmean(four) if four else 0.0,
        "std4": pstdev(four) if four else 0.0,
        "weeks_since_change": (as_of - changed_week).days / 7.0,
        "last_change": last_change,
        "category_mean": category_mean,
        "week_sin": math.sin(phase),
        "week_cos": math.cos(phase),
        "holiday_distance": holiday_distance(target),
        "age_weeks": (as_of - first_week).days / 7.0,
        "zero_fraction": sum(row[1] == 0 for row in thirteen) / len(thirteen) if thirteen else 0.0,
        "trend": (target - date(2009, 1, 5)).days / 7.0,
    }
    return vector


def make_features(panel: pl.DataFrame) -> pl.DataFrame:
    """Gold labels are gross demand; realized target price is never a feature."""
    labels = (
        panel.filter(pl.col("is_complete_week")) if "is_complete_week" in panel.columns else panel
    )
    weeks: list[date] = labels["week"].unique().sort().to_list()
    gold: list[pl.DataFrame] = []
    demand = "gross_units" if "gross_units" in panel.columns else "units"
    for week in weeks:
        features = batch_features(panel, week - timedelta(weeks=1))
        if features.is_empty():
            continue
        target = labels.filter(pl.col("week") == week).select(
            "product_id",
            "week",
            pl.col(demand).alias("units"),
        )
        gold.append(features.join(target, on="product_id", how="inner"))
    if not gold:
        raise ValueError("At least three weekly observations are required to build gold features")
    return pl.concat(gold).sort(["week", "product_id"])


FeatureBuilder = Callable[[pl.DataFrame, str, float, date], dict[str, float]]


def measure_skew(
    panel: pl.DataFrame,
    pairs: Sequence[tuple[str, date]],
    serving_builder: FeatureBuilder = feature_vector,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Compare independent paths and return a machine-readable release-gate result."""
    maximum = 0.0
    cache: dict[date, dict[str, dict[str, Any]]] = {}
    store = ServingFeatureStore(panel) if serving_builder is feature_vector else None
    for product, as_of in pairs:
        if as_of not in cache:
            cache[as_of] = {
                str(row["product_id"]): row
                for row in batch_features(panel, as_of).iter_rows(named=True)
            }
        batch = cache[as_of][product]
        serving = (
            store.vector(product, float(batch["price"]), as_of)
            if store is not None
            else serving_builder(panel, product, float(batch["price"]), as_of)
        )
        if list(serving) != list(FEATURE_NAMES):
            return {
                "pairs": len(pairs),
                "max_abs_difference": None,
                "passed": False,
                "tolerance": tolerance,
                "reason": "feature_contract_mismatch",
            }
        for name in FEATURE_NAMES:
            difference = abs(float(batch[name]) - serving[name])
            if not math.isfinite(difference):
                return {
                    "pairs": len(pairs),
                    "max_abs_difference": None,
                    "passed": False,
                    "tolerance": tolerance,
                    "reason": "non_finite_feature",
                }
            maximum = max(maximum, difference)
    return {
        "pairs": len(pairs),
        "max_abs_difference": maximum,
        "passed": bool(pairs) and maximum <= tolerance,
        "tolerance": tolerance,
    }
