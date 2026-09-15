"""Versioned local model artifacts with checksums and atomic promotion pointers."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pricepoint_models.estimators import DemandModel, load_model
from pricepoint_models.gates import GATE_NAMES, GateResult


class Registry:
    """A local file registry; model pickle files are trusted build outputs only."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _directory(self, version: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", version):
            raise ValueError("Model version must be a simple safe directory name")
        return self.root / version

    def register(
        self,
        model: DemandModel,
        metrics: dict[str, Any],
        gates: list[GateResult] | None = None,
        *,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register once; refuse overwriting an existing immutable version."""
        model_version = version or f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:12]}"
        directory = self._directory(model_version)
        directory.mkdir(exist_ok=False)
        model.version = model_version
        artifact = directory / "model.pkl"
        model.dump(artifact)
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest: dict[str, Any] = {
            "version": model_version,
            "name": model.name,
            "created_at": datetime.now(UTC).isoformat(),
            "artifact": "model.pkl",
            "sha256": checksum,
            "python": platform.python_version(),
            "feature_contract": model.feature_contract,
            "metrics": metrics,
            "gates": [gate.to_dict() for gate in gates] if gates is not None else [],
            "metadata": metadata or {},
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8"
        )
        return manifest

    def manifest(self, version: str) -> dict[str, Any]:
        contents: Any = json.loads(
            (self._directory(version) / "manifest.json").read_text(encoding="utf-8")
        )
        if not isinstance(contents, dict) or contents.get("version") != version:
            raise ValueError("Invalid registry manifest")
        return contents

    def load(self, version: str) -> DemandModel:
        manifest = self.manifest(version)
        artifact = self._directory(version) / "model.pkl"
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if checksum != manifest["sha256"]:
            raise ValueError("Model checksum mismatch")
        model = load_model(artifact)
        if model.feature_contract != manifest["feature_contract"] or model.version != version:
            raise ValueError("Model artifact and manifest disagree")
        return model

    def list(self) -> list[dict[str, Any]]:
        incumbent = self.incumbent_version()
        result: list[dict[str, Any]] = []
        for manifest_path in sorted(self.root.glob("*/manifest.json")):
            item = self.manifest(manifest_path.parent.name)
            item["status"] = "incumbent" if item["version"] == incumbent else "candidate"
            result.append(item)
        return result

    def incumbent_version(self) -> str | None:
        pointer = self.root / "incumbent.json"
        if not pointer.exists():
            return None
        contents = json.loads(pointer.read_text(encoding="utf-8"))
        return str(contents["version"])

    def bootstrap(self, version: str, *, reason: str) -> None:
        """Install the measured baseline as the first incumbent, without claiming promotion."""
        if self.incumbent_version() is not None:
            raise ValueError("A registry incumbent already exists")
        if not reason.strip():
            raise ValueError("Baseline bootstrap requires a recorded reason")
        self.load(version)
        self._write_pointer(version, {"bootstrap_reason": reason})

    def promote(self, version: str, gates: Sequence[GateResult]) -> None:
        if (
            len(gates) != 6
            or {gate.name for gate in gates} != set(GATE_NAMES)
            or not all(gate.passed for gate in gates)
        ):
            raise ValueError("Promotion refused: all six distinct gates must pass")
        self.load(version)
        self._write_pointer(version, {"gates": [gate.to_dict() for gate in gates]})

    def _write_pointer(self, version: str, evidence: dict[str, Any]) -> None:
        temporary = self.root / f".incumbent-{uuid.uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(
                {"version": version, "updated_at": datetime.now(UTC).isoformat(), **evidence},
                allow_nan=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.root / "incumbent.json")
