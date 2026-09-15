"""ASGI serving with startup validation and bounded request contracts."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pricepoint_core.config import Settings
from pricepoint_core.schemas import (
    CurveRequest,
    OptimizeRequest,
    Prediction,
    PredictRequest,
    StrictModel,
)
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from starlette.concurrency import run_in_threadpool

from pricepoint_serve.engine import PredictionEngine


class Optimization(StrictModel):
    recommended_price: float
    expected_units: float
    expected_revenue: float
    expected_margin: float
    interval: list[float]
    extrapolation_warning: bool
    warning_reason: str | None
    markdown: float
    objective: str
    inventory: float
    grid_candidates: int
    model_version: str


def create_app(settings: Settings | None = None) -> FastAPI:
    chosen = settings or Settings.from_env()
    metrics_registry = CollectorRegistry()
    requests = Counter(
        "pricepoint_requests_total",
        "HTTP responses",
        ["route", "status"],
        registry=metrics_registry,
    )
    latency = Histogram(
        "pricepoint_request_seconds",
        "HTTP request duration",
        ["route"],
        registry=metrics_registry,
        buckets=(0.001, 0.002, 0.005, 0.01, 0.015, 0.03, 0.1, 1),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        level = getattr(logging, os.getenv("PRICEPOINT_LOG_LEVEL", "INFO").upper(), logging.INFO)
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(level),
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
        )
        application.state.engine = PredictionEngine(chosen)
        yield

    application = FastAPI(title="pricepoint", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def instrument(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        route = (
            request.url.path
            if request.url.path
            in {"/v1/predict", "/v1/curve", "/v1/optimize", "/v1/models", "/healthz", "/metrics"}
            else "other"
        )
        requests.labels(route, str(response.status_code)).inc()
        latency.labels(route).observe(time.perf_counter() - started)
        return response

    async def invoke(function: Callable[..., Any], *args: Any) -> Any:
        try:
            return await run_in_threadpool(function, *args)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/v1/predict", response_model=Prediction)
    async def predict(request: PredictRequest) -> Any:
        return await invoke(
            application.state.engine.predict, request.product_id, request.price, request.as_of
        )

    @application.post("/v1/curve", response_model=list[Prediction])
    async def curve(request: CurveRequest) -> Any:
        return await invoke(
            application.state.engine.curve, request.product_id, request.price_grid, request.as_of
        )

    @application.post("/v1/optimize", response_model=Optimization)
    async def optimize(request: OptimizeRequest) -> Any:
        return await invoke(application.state.engine.optimize, request)

    @application.get("/v1/models")
    async def models() -> list[dict[str, Any]]:
        return application.state.engine.registry.list()  # type: ignore[no-any-return]

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        engine: PredictionEngine = application.state.engine
        return {"status": "ok", "model_version": engine.incumbent.version}

    @application.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(metrics_registry), media_type="text/plain; version=0.0.4")

    return application


app = create_app()
