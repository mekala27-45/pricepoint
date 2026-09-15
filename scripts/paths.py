"""Locate a materialized project separately from installed Python package files."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


def _is_project_root(path: Path) -> bool:
    try:
        project = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return False
    return (
        project.get("project", {}).get("name") == "pricepoint"
        and (path / "config/data.json").is_file()
        and (path / "artifacts").is_dir()
    )


def project_root(*, cwd: Path | None = None, source_file: Path | None = None) -> Path:
    """Prefer explicit project location, then a validated cwd, then source checkout.

    Wheels contain executable modules, while data, configuration, and registry
    artifacts belong to a materialized source checkout or extracted source archive.
    No command should mistake site-packages for a writable project directory.
    """
    configured = os.environ.get("PRICEPOINT_ROOT")
    if configured is not None:
        chosen = Path(configured).expanduser().resolve()
        if not configured.strip() or not _is_project_root(chosen):
            raise ValueError(
                "PRICEPOINT_ROOT must name a pricepoint checkout with config and artifacts"
            )
        return chosen
    working = (cwd or Path.cwd()).resolve()
    if _is_project_root(working):
        return working
    source = (source_file or Path(__file__)).resolve().parents[1]
    if _is_project_root(source):
        return source
    raise ValueError(
        "Project files were not found. Run from the pricepoint checkout or set "
        "PRICEPOINT_ROOT to its directory; installed wheels do not contain runtime artifacts."
    )
