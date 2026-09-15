"""Async HTTP load generator, including errors, warmup and raw latency samples."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import structlog
from asgi_lifespan import LifespanManager


async def measure(
    client: httpx.AsyncClient,
    payloads: list[dict[str, Any]],
    *,
    seconds: float,
    concurrency: int,
    warmup: int = 100,
) -> dict[str, Any]:
    if not payloads or seconds <= 0 or concurrency < 1 or warmup < 0:
        raise ValueError("Require payloads, positive duration and concurrency, nonnegative warmup")
    for index in range(warmup):
        response = await client.post("/v1/predict", json=payloads[index % len(payloads)])
        response.raise_for_status()
    samples: list[float] = []
    errors: list[str] = []
    started = time.perf_counter()
    deadline = started + seconds

    async def worker(offset: int) -> None:
        index = offset
        while time.perf_counter() < deadline:
            begin = time.perf_counter()
            try:
                response = await client.post("/v1/predict", json=payloads[index % len(payloads)])
                response.raise_for_status()
                samples.append((time.perf_counter() - begin) * 1000)
            except (httpx.HTTPError, ValueError) as error:
                errors.append(str(error))
            index += concurrency

    await asyncio.gather(*(worker(index) for index in range(concurrency)))
    elapsed = time.perf_counter() - started
    if not samples:
        raise ValueError("Load test completed without a successful response")
    counts, edges = np.histogram(samples, bins=[0, 1, 2, 5, 10, 15, 25, 50, 100, float("inf")])
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": concurrency,
        "duration_requested_s": seconds,
        "duration_actual_s": elapsed,
        "warmup_requests": warmup,
        "successful_requests": len(samples),
        "errors": len(errors),
        "error_examples": errors[:5],
        "throughput_rps": len(samples) / elapsed,
        "p50_ms": float(np.percentile(samples, 50)),
        "p95_ms": float(np.percentile(samples, 95)),
        "p99_ms": float(np.percentile(samples, 99)),
        "histogram": [
            {
                "low_ms": float(edges[i]),
                "high_ms": None if np.isinf(edges[i + 1]) else float(edges[i + 1]),
                "count": int(count),
            }
            for i, count in enumerate(counts)
        ],
        "latency_samples_ms": samples,
        "methodology": (
            "Closed-loop concurrent clients; latency includes client serialization, "
            "ASGI routing, feature construction, incumbent and enabled shadow scoring. "
            "Warmup excluded. Throughput counts successful responses only."
        ),
    }


async def run(args: argparse.Namespace) -> None:
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    payloads = [
        {"product_id": p["id"], "price": p["current_price"], "as_of": p["as_of"]}
        for p in bundle["products"][:20]
    ]
    if args.url:
        async with httpx.AsyncClient(base_url=args.url, timeout=30) as client:
            result = await measure(
                client, payloads, seconds=args.seconds, concurrency=args.concurrency
            )
        result["transport"] = "TCP HTTP to container" if args.container else "TCP HTTP"
    else:
        from pricepoint_serve.app import create_app

        application = create_app()
        async with LifespanManager(application):
            structlog.configure(
                wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://test"
            ) as client:
                result = await measure(
                    client, payloads, seconds=args.seconds, concurrency=args.concurrency
                )
        result["transport"] = "in-process ASGI, no network or container"
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "latency_samples_ms"}, indent=2
        )
    )
    if result["errors"]:
        raise SystemExit("Load test had request errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url")
    parser.add_argument("--container", action="store_true")
    parser.add_argument("--bundle", default="web/public/bundle.json")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", default="artifacts/loadtest-inprocess.json")
    asyncio.run(run(parser.parse_args()))
