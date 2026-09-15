"""Load models once; validate history and score an optional shadow candidate."""

from __future__ import annotations

import json
import math
from collections import deque
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import structlog
from pricepoint_core.config import Settings
from pricepoint_core.schemas import FEATURE_CONTRACT, OptimizeRequest, Prediction
from pricepoint_data.features import ServingFeatureStore
from pricepoint_models.estimators import CalibratedModel
from pricepoint_models.optimizer import optimize, with_candidate_prices
from pricepoint_models.registry import Registry

log = structlog.get_logger()


class PredictionEngine:
    def __init__(self, settings: Settings) -> None:
        if not settings.registry.exists() or not settings.panel.exists():
            raise FileNotFoundError("Required model registry or serving panel is missing")
        self.registry = Registry(settings.registry)
        version = self.registry.incumbent_version()
        if version is None:
            raise ValueError("Registry has no incumbent")
        incumbent = self.registry.load(version)
        if not isinstance(incumbent, CalibratedModel):
            raise ValueError("Serving requires a calibrated incumbent")
        if incumbent.feature_contract != FEATURE_CONTRACT:
            raise ValueError("Serving feature contract does not match model")
        self.incumbent = incumbent
        self.manifest = self.registry.manifest(version)
        metadata = self.manifest["metadata"]
        self.support: dict[str, list[float]] = metadata["support"]
        self.default_as_of = date.fromisoformat(metadata["as_of"])
        self.minimum_as_of = date.fromisoformat(metadata["minimum_as_of"])
        self.panel = pl.read_parquet(settings.panel)
        complete = (
            self.panel.filter(pl.col("is_complete_week"))
            if "is_complete_week" in self.panel.columns
            else self.panel
        )
        latest = complete["week"].max()
        if not isinstance(latest, date):
            raise ValueError("Serving panel must contain complete dated weeks")
        self.maximum_as_of = latest + timedelta(weeks=1)
        self.store = ServingFeatureStore(self.panel)
        self.categories = {
            str(row["product_id"]): str(row["category"])
            for row in self.panel.sort("week")
            .unique("product_id", keep="first")
            .iter_rows(named=True)
        }
        self.candidate: CalibratedModel | None = None
        self.candidate_minimum_as_of: date | None = None
        candidates = [
            item
            for item in self.registry.list()
            if item["status"] == "candidate" and item["metadata"].get("role") != "baseline"
        ]
        if settings.shadow and candidates:
            newest = max(
                candidates,
                key=lambda item: (
                    item.get("latest_assessment", {}).get("recorded_at", item["created_at"]),
                    item["version"],
                ),
            )
            candidate = self.registry.load(newest["version"])
            if (
                not isinstance(candidate, CalibratedModel)
                or candidate.feature_contract != FEATURE_CONTRACT
            ):
                raise ValueError("Shadow artifact does not match serving contract")
            self.candidate = candidate
            self.candidate_minimum_as_of = date.fromisoformat(newest["metadata"]["minimum_as_of"])
        self.shadow_observations: deque[dict[str, Any]] = deque(maxlen=10000)
        self.requests = 0
        log.info(
            "model_loaded",
            incumbent=version,
            candidate=self.candidate.version if self.candidate else None,
        )

    def row(self, product: str, price: float, as_of: date) -> pl.DataFrame:
        if product not in self.support:
            raise KeyError(f"Unknown or ineligible product: {product}")
        if as_of.weekday() != 0:
            raise ValueError("as_of must be an ISO-week Monday")
        if not self.minimum_as_of <= as_of <= self.maximum_as_of:
            raise ValueError(
                f"as_of must be between {self.minimum_as_of} and {self.maximum_as_of}; "
                "the frozen artifact cannot serve outside its evidence period"
            )
        values = self.store.vector(product, price, as_of)
        return pl.DataFrame(
            [
                {
                    "product_id": product,
                    "category": self.categories[product],
                    "as_of": as_of,
                    **values,
                }
            ]
        )

    def _shadow(self, frame: pl.DataFrame, incumbent: list[float]) -> None:
        self.requests += frame.height
        if self.candidate is None:
            return
        requested_cutoff = frame["as_of"].min()
        if not isinstance(requested_cutoff, date):
            raise ValueError("Shadow requests require a decision date")
        if self.candidate_minimum_as_of is None or requested_cutoff < self.candidate_minimum_as_of:
            log.info(
                "shadow_skipped",
                candidate_version=self.candidate.version,
                requested_as_of=requested_cutoff.isoformat(),
                reason="Candidate fitting and calibration were not yet observable at this cutoff",
            )
            return
        candidate = self.candidate.predict(frame).tolist()
        for product, price, actual, proposed in zip(
            frame["product_id"], frame["price"], incumbent, candidate, strict=True
        ):
            observation = {
                "product_id": product,
                "price": price,
                "incumbent_version": self.incumbent.version,
                "candidate_version": self.candidate.version,
                "incumbent_units": actual,
                "candidate_units": proposed,
                "absolute_disagreement": abs(actual - proposed),
                "relative_disagreement": abs(actual - proposed) / max(actual, 1.0),
            }
            self.shadow_observations.append(observation)
            log.info("shadow_prediction", **observation)

    def curve(self, product: str, prices: list[float], as_of: date) -> list[Prediction]:
        if not prices or any(not math.isfinite(price) or price <= 0 for price in prices):
            raise ValueError("Candidate prices must be finite and positive")
        frame = with_candidate_prices(self.row(product, prices[0], as_of), prices)
        point, lower, upper = self.incumbent.predict_interval(frame)
        self._shadow(frame, point.tolist())
        support = self.support[product]
        return [
            Prediction(
                product_id=product,
                price=price,
                units=float(units),
                revenue=float(units * price),
                interval_low=float(low),
                interval_high=float(high),
                model_version=self.incumbent.version,
                extrapolation_warning=not support[0] < price < support[1],
            )
            for price, units, low, high in zip(prices, point, lower, upper, strict=True)
        ]

    def predict(self, product: str, price: float, as_of: date) -> Prediction:
        return self.curve(product, [price], as_of)[0]

    def optimize(self, request: OptimizeRequest) -> dict[str, Any]:
        cutoff = request.as_of or self.default_as_of
        row = self.row(request.product_id, request.current_price, cutoff)
        result = optimize(
            self.incumbent,
            row,
            current_price=request.current_price,
            cost_floor=request.cost_floor,
            min_markdown=request.min_markdown,
            max_markdown=request.max_markdown,
            inventory=request.inventory,
            support=self.support[request.product_id],
            objective=request.objective,
        )
        chosen = with_candidate_prices(row, [float(result["recommended_price"])])
        self._shadow(chosen, self.incumbent.predict(chosen).tolist())
        return result

    def save_shadow(self, destination: Path) -> None:
        destination.write_text(
            json.dumps(list(self.shadow_observations), indent=2), encoding="utf-8"
        )
