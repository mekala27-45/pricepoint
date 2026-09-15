"""Versioned contracts and validated public API payloads."""

from __future__ import annotations

import math
import secrets
import threading
import time
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
FEATURE_CONTRACT = {
    "version": "1",
    "features": [{"name": name, "dtype": "float64"} for name in FEATURE_NAMES],
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class MetricStat(StrictModel):
    mean: float
    std: float = Field(ge=0)
    n: int = Field(ge=1)


class PredictRequest(StrictModel):
    product_id: str = Field(min_length=1, max_length=64)
    price: float = Field(gt=0, le=100000)
    as_of: date

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_date(cls, value: object) -> object:
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value


class Prediction(StrictModel):
    product_id: str
    price: float
    units: float = Field(ge=0)
    revenue: float = Field(ge=0)
    interval_low: float = Field(ge=0)
    interval_high: float = Field(ge=0)
    model_version: str
    extrapolation_warning: bool = False

    @model_validator(mode="after")
    def ordered(self) -> Prediction:
        if self.interval_low > self.interval_high:
            raise ValueError("Interval endpoints are reversed")
        return self


class CurveRequest(StrictModel):
    product_id: str = Field(min_length=1, max_length=64)
    price_grid: list[float] = Field(min_length=2, max_length=201)
    as_of: date

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_date(cls, value: object) -> object:
        return date.fromisoformat(value) if isinstance(value, str) else value

    @field_validator("price_grid")
    @classmethod
    def valid_grid(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(v) or v <= 0 or v > 100000 for v in values):
            raise ValueError("Prices must be finite, positive and at most 100000")
        return values


class OptimizeRequest(StrictModel):
    product_id: str = Field(min_length=1, max_length=64)
    current_price: float = Field(gt=0, le=100000)
    cost_floor: float = Field(ge=0, le=100000)
    min_markdown: float = Field(default=0.0, ge=0, le=1)
    max_markdown: float = Field(default=0.5, ge=0, lt=1)
    inventory: float = Field(default=100.0, ge=0, le=1e9)
    objective: Literal["revenue", "margin"] = "revenue"
    as_of: date | None = None

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_date(cls, value: object) -> object:
        return date.fromisoformat(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_bounds(self) -> OptimizeRequest:
        if self.min_markdown > self.max_markdown:
            raise ValueError("Minimum markdown exceeds maximum markdown")
        return self


_uuid_lock = threading.Lock()
_last_uuid_int = 0


def uuid7() -> str:
    """Monotonic UUIDv7, including multiple calls within a millisecond."""
    global _last_uuid_int
    with _uuid_lock:
        milliseconds = time.time_ns() // 1_000_000
        random_bits = secrets.randbits(74)
        value = (
            (milliseconds << 80)
            | (7 << 76)
            | ((random_bits >> 62) << 64)
            | (2 << 62)
            | (random_bits & ((1 << 62) - 1))
        )
        if value <= _last_uuid_int:
            value = _last_uuid_int + 1
        _last_uuid_int = value
        return str(UUID(int=value))
