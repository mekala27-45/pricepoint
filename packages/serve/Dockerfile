FROM ghcr.io/astral-sh/uv:0.11.33 AS uv
FROM python:3.12.14-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    PRICEPOINT_REGISTRY=/app/artifacts/registry \
    PRICEPOINT_PANEL=/app/artifacts/serving_panel.parquet \
    PRICEPOINT_SHADOW=true
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
COPY scripts ./scripts
RUN uv sync --frozen --no-dev
COPY artifacts/registry ./artifacts/registry
COPY artifacts/serving_panel.parquet ./artifacts/serving_panel.parquet
RUN useradd --uid 10001 --create-home pricepoint && chown -R pricepoint:pricepoint /app
USER pricepoint
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["/app/.venv/bin/uvicorn", "pricepoint_serve.app:app", "--host", "0.0.0.0", "--port", "8000"]
