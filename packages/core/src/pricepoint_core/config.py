"""Explicit paths and serving environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    registry: Path = Path("artifacts/registry")
    panel: Path = Path("artifacts/serving_panel.parquet")
    shadow: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            registry=Path(os.getenv("PRICEPOINT_REGISTRY", "artifacts/registry")),
            panel=Path(os.getenv("PRICEPOINT_PANEL", "artifacts/serving_panel.parquet")),
            shadow=os.getenv("PRICEPOINT_SHADOW", "true").lower() == "true",
        )
