"""Every gate is independently broken, then refused by the real registry."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from pricepoint_models import (
    BaselineModel,
    GateEvidence,
    Registry,
    evaluate_gates,
    feature_contract,
)


def passing_evidence() -> GateEvidence:
    return GateEvidence(
        candidate_wape=0.38,
        incumbent_wape=0.4,
        candidate_category_wape={"a": 0.38, "b": 0.4},
        incumbent_category_wape={"a": 0.4, "b": 0.4},
        latency_p99_ms=10,
        latency_samples=1000,
        coverage=0.9,
        coverage_samples=1000,
        coverage_split="held_out_test",
        candidate_schema=feature_contract(),
        serving_schema=feature_contract(),
        skew_max_abs=1e-12,
        skew_pairs=500,
    )


@pytest.mark.parametrize(
    "gate,changes",
    [
        ("wape_improvement", {"candidate_wape": 0.399}),
        ("category_non_regression", {"candidate_category_wape": {"a": 0.38, "b": 0.421}}),
        ("latency", {"latency_p99_ms": 15.0}),
        ("coverage", {"coverage": 0.879}),
        ("schema", {"candidate_schema": {"version": "incorrect", "features": []}}),
        ("training_serving_skew", {"skew_max_abs": 1e-4}),
    ],
)
def test_each_promotion_gate_deliberately_fails(
    tmp_path: Path, gate: str, changes: dict[str, Any]
) -> None:
    registry = Registry(tmp_path)
    model = BaselineModel("B2").fit(pl.DataFrame({"units": [1.0], "mean4": [1.0]}))
    registry.register(model, {"wape": 0.38}, version="candidate")
    results = evaluate_gates(replace(passing_evidence(), **changes))
    assert [result.name for result in results if not result.passed] == [gate]
    with pytest.raises(ValueError, match="Promotion refused"):
        registry.promote("candidate", results)
    assert registry.incumbent_version() is None


def test_missing_evidence_refuses_every_gate() -> None:
    assert not any(gate.passed for gate in evaluate_gates(GateEvidence()))


@pytest.mark.parametrize("mutation", ["order", "dtype", "version"])
def test_schema_gate_enforces_order_types_and_version(mutation: str) -> None:
    schema = copy.deepcopy(feature_contract())
    if mutation == "order":
        schema["features"].reverse()
    elif mutation == "dtype":
        schema["features"][0]["dtype"] = "float32"
    else:
        schema["version"] = "2"
    results = evaluate_gates(replace(passing_evidence(), candidate_schema=schema))
    assert [gate.name for gate in results if not gate.passed] == ["schema"]


@pytest.mark.parametrize(
    "changes,gate",
    [
        ({"coverage_split": "calibration"}, "coverage"),
        ({"coverage_samples": None}, "coverage"),
        ({"skew_pairs": 499}, "training_serving_skew"),
        ({"skew_tolerance": 1.0}, "training_serving_skew"),
        ({"latency_samples": 99}, "latency"),
        ({"candidate_category_wape": {"a": 0.3}}, "category_non_regression"),
        ({"candidate_wape": float("nan")}, "wape_improvement"),
        ({"candidate_wape": 0.0, "incumbent_wape": 0.0}, "wape_improvement"),
    ],
)
def test_claimed_evidence_must_be_complete(changes: dict[str, Any], gate: str) -> None:
    results = evaluate_gates(replace(passing_evidence(), **changes))
    assert [result.name for result in results if not result.passed] == [gate]


def test_registry_integrity_promotion_and_immutable_versions(tmp_path: Path) -> None:
    registry = Registry(tmp_path)
    model = BaselineModel().fit(pl.DataFrame({"units": [1.0], "mean4": [1.0]}))
    registry.register(model, {}, version="baseline")
    registry.bootstrap("baseline", reason="Measured best historical baseline")
    assert registry.incumbent_version() == "baseline"
    with pytest.raises(ValueError, match="already"):
        registry.bootstrap("baseline", reason="Duplicate")
    registry.register(model, {}, version="candidate")
    assert registry.load("candidate").version == "candidate"
    assert {row["status"] for row in registry.list()} == {"candidate", "incumbent"}
    gates = evaluate_gates(passing_evidence())
    registry.promote("candidate", gates)
    assert registry.incumbent_version() == "candidate"
    assert all(
        result["passed"]
        for result in json.loads((tmp_path / "incumbent.json").read_text())["gates"]
    )
    assert registry.register(model, {}, version="candidate")["version"] == "candidate"
    changed = BaselineModel("B0").fit(pl.DataFrame({"units": [1.0]}))
    with pytest.raises(FileExistsError):
        registry.register(changed, {}, version="candidate")
    with pytest.raises(ValueError, match="safe"):
        registry.load("../outside")
    with pytest.raises(ValueError, match="six"):
        registry.promote("candidate", [gates[0]] * 6)
    artifact = tmp_path / "candidate" / "model.pkl"
    artifact.write_bytes(artifact.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        registry.load("candidate")


def test_registry_rejects_modified_manifest_and_unexplained_bootstrap(tmp_path: Path) -> None:
    registry = Registry(tmp_path)
    model = BaselineModel().fit(pl.DataFrame({"units": [1.0]}))
    registry.register(model, {}, version="one")
    with pytest.raises(ValueError, match="reason"):
        registry.bootstrap("one", reason="")
    path = tmp_path / "one" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["feature_contract"] = {"version": "bad"}
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="disagree"):
        registry.load("one")
    manifest["version"] = "wrong-directory"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid"):
        registry.manifest("one")
