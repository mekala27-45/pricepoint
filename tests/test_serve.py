import asyncio
from datetime import date, timedelta
from pathlib import Path

import httpx
import polars as pl
import pytest
from asgi_lifespan import LifespanManager
from pricepoint_core.config import Settings
from pricepoint_data.features import batch_features
from pricepoint_models.estimators import BaselineModel, CalibratedModel
from pricepoint_models.registry import Registry
from pricepoint_serve.app import create_app


def serving_settings(tmp_path: Path, shadow: bool = True) -> Settings:
    start = date(2010, 1, 4)
    rows = [
        {
            "product_id": product,
            "category": "kitchen",
            "description": product,
            "week": start + timedelta(weeks=week),
            "price": 2.0 + week % 3 * 0.1,
            "units": float(10 + week % 7),
            "gross_units": float(10 + week % 7),
        }
        for product in ("A", "X")
        for week in range(60)
    ]
    panel = pl.DataFrame(rows)
    panel_path = tmp_path / "panel.parquet"
    panel.write_parquet(panel_path)
    cutoff = start + timedelta(weeks=60)
    frame = batch_features(panel, cutoff).with_columns(pl.lit(15.0).alias("units"))
    registry = Registry(tmp_path / "registry")
    metadata = {
        "support": {"A": [1.0, 3.0], "X": [1.0, 3.0]},
        "as_of": cutoff.isoformat(),
        "minimum_as_of": (cutoff - timedelta(weeks=4)).isoformat(),
    }
    incumbent = CalibratedModel(BaselineModel("B2").fit(frame), 4.0)
    registry.register(incumbent, {}, metadata=metadata, version="baseline")
    registry.bootstrap("baseline", reason="Measured reference")
    candidate = CalibratedModel(BaselineModel("B0").fit(frame), 5.0)
    registry.register(candidate, {}, metadata=metadata, version="candidate")
    return Settings(registry=registry.root, panel=panel_path, shadow=shadow)


def test_asgi_routes_return_incumbent_and_log_shadow(tmp_path: Path) -> None:
    application = create_app(serving_settings(tmp_path))

    async def scenario() -> None:
        async with LifespanManager(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://test"
            ) as client:
                cutoff = application.state.engine.default_as_of.isoformat()
                payload = {"product_id": "A", "price": 2.0, "as_of": cutoff}
                response = await client.post("/v1/predict", json=payload)
                assert response.status_code == 200
                assert response.json()["model_version"] == "baseline"
                assert response.json()["revenue"] == response.json()["units"] * 2
                assert len(application.state.engine.shadow_observations) == 1
                curve = await client.post(
                    "/v1/curve",
                    json={"product_id": "A", "price_grid": [1.0, 2.0, 3.0], "as_of": cutoff},
                )
                assert len(curve.json()) == 3
                assert curve.json()[0]["extrapolation_warning"]
                optimal = await client.post(
                    "/v1/optimize",
                    json={
                        "product_id": "A",
                        "current_price": 2.0,
                        "cost_floor": 1.2,
                        "inventory": 4.0,
                        "min_markdown": 0.0,
                        "max_markdown": 0.5,
                        "objective": "margin",
                    },
                )
                assert optimal.status_code == 200, optimal.text
                assert optimal.json()["expected_units"] <= 4
                assert optimal.json()["recommended_price"] >= 1.2
                assert (await client.get("/healthz")).json()["status"] == "ok"
                assert len((await client.get("/v1/models")).json()) == 2
                assert "pricepoint_requests_total" in (await client.get("/metrics")).text
                unknown = await client.post(
                    "/v1/predict", json={**payload, "product_id": "missing"}
                )
                assert unknown.status_code == 404
                assert (
                    await client.post("/v1/predict", json={**payload, "price": -1})
                ).status_code == 422
                assert (
                    await client.post("/v1/predict", json={**payload, "as_of": "2040-01-02"})
                ).status_code == 422
                assert (
                    await client.post(
                        "/v1/optimize",
                        json={"product_id": "A", "current_price": 2.0, "cost_floor": 9.0},
                    )
                ).status_code == 422

    asyncio.run(scenario())


def test_missing_artifact_fails_at_startup(tmp_path: Path) -> None:
    application = create_app(Settings(registry=tmp_path / "missing", panel=tmp_path / "absent"))

    async def scenario() -> None:
        with pytest.raises(FileNotFoundError):
            async with LifespanManager(application):
                pass

    asyncio.run(scenario())
