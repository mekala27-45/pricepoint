"""Primary command-line interface for the reproducible public-data service."""

from __future__ import annotations

import json
import zipfile
from datetime import date
from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True, help="Evaluate, serve and monitor public retail demand.")
console = Console()


class Objective(StrEnum):
    revenue = "revenue"
    margin = "margin"


@app.command()
def data() -> None:
    """Download pinned public data and build the documented Parquet layers."""
    from pricepoint_data import download

    from scripts.build_data import build_data
    from scripts.evaluate import ROOT

    destination = ROOT / "data/raw/online-retail-ii.zip"
    download(
        "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip",
        destination,
        "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb",
    )
    workbook = destination.parent / "online_retail_II.xlsx"
    if not workbook.exists():
        with zipfile.ZipFile(destination) as archive:
            # Extract the named member only, never arbitrary archive paths.
            workbook.write_bytes(archive.read("online_retail_II.xlsx"))
    build_data()


@app.command()
def train() -> None:
    """Run expanding evaluation and record a local MLflow experiment."""
    from scripts.evaluate import backtest

    backtest()


@app.command()
def monitor() -> None:
    """Simulate historical drift, cooldown and observably scheduled refits."""
    from scripts.simulate_monitoring import run

    run()


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the service with startup artifact validation."""
    import uvicorn

    uvicorn.run("pricepoint_serve.app:app", host=host, port=port)


@app.command()
def predict(product_id: str, price: float, as_of: str = "2011-12-05") -> None:
    """Score a proposed price through the same path as the API."""
    from pricepoint_serve.engine import PredictionEngine

    from pricepoint_core.config import Settings

    result = PredictionEngine(Settings.from_env()).predict(
        product_id, price, date.fromisoformat(as_of)
    )
    console.print_json(result.model_dump_json())


@app.command()
def optimize(
    product_id: str,
    current_price: float,
    cost_floor: float,
    inventory: float = 100.0,
    min_markdown: float = 0.0,
    max_markdown: float = 0.5,
    objective: Objective = Objective.revenue,
) -> None:
    """Search every feasible penny under cost, support and inventory bounds."""
    from pricepoint_serve.engine import PredictionEngine

    from pricepoint_core.config import Settings
    from pricepoint_core.schemas import OptimizeRequest

    request = OptimizeRequest(
        product_id=product_id,
        current_price=current_price,
        cost_floor=cost_floor,
        inventory=inventory,
        min_markdown=min_markdown,
        max_markdown=max_markdown,
        objective=objective.value,
    )
    result = PredictionEngine(Settings.from_env()).optimize(request)
    console.print_json(json.dumps(result))


@app.command()
def models(registry_path: Path = Path("artifacts/registry")) -> None:
    """Show immutable model versions and the recorded promotion status."""
    from pricepoint_models.registry import Registry

    table = Table("Version", "Model", "Status", "Passed gates")
    for row in Registry(registry_path).list():
        table.add_row(
            row["version"],
            row["name"],
            row["status"],
            str(sum(gate["passed"] for gate in row["gates"])),
        )
    console.print(table)


@app.command()
def check() -> None:
    """Re-derive published numerical evidence and artifact integrity."""
    from scripts.check_published_numbers import main as check_claims
    from scripts.verify_artifacts import main as verify

    verify([])
    check_claims()


if __name__ == "__main__":
    app()
