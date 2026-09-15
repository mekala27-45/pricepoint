"""Content identities, immutable registrations, and append-only gate assessments."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from pricepoint_models import (
    BaselineModel,
    CalibratedModel,
    GateEvidence,
    GateResult,
    Registry,
    evaluate_gates,
    feature_contract,
)

from scripts.package_artifacts import comparable_incumbent, model_identity, model_state_fingerprint


def baseline(kind: str = "B2", radius: float = 2.0) -> CalibratedModel:
    frame = pl.DataFrame(
        {"units": [3.0, 2.0, 1.0], "mean4": [3.0, 3.0, 2.0], "log_price": [0.0, 1.0, 2.0]}
    )
    if kind == "B3":
        base = BaselineModel("B3").fit(frame)
    elif kind == "B1":
        base = BaselineModel("B1").fit(frame)
    else:
        base = BaselineModel("B2").fit(frame)
    return CalibratedModel(base, radius)


def passing_gates(latency: float = 1.0) -> list[GateResult]:
    return evaluate_gates(
        GateEvidence(
            candidate_wape=0.2,
            incumbent_wape=0.3,
            candidate_category_wape={"a": 0.2},
            incumbent_category_wape={"a": 0.3},
            latency_p99_ms=latency,
            latency_samples=100,
            coverage=0.9,
            coverage_samples=100,
            coverage_split="held_out_test",
            candidate_schema=feature_contract(),
            serving_schema=feature_contract(),
            skew_max_abs=0.0,
            skew_pairs=500,
        )
    )


def test_model_identity_changes_with_model_data_configuration_and_source() -> None:
    model = baseline()
    keywords = dict(
        data_sha256="dataset-a",
        training_config={"trees": 100},
        source_sha256={"model.py": "code-a"},
    )
    original, provenance = model_identity(model, **keywords)
    model.version = "registered"
    model.base.version = "registered-base"
    assert model_identity(model, **keywords)[0] == original
    assert model_identity(baseline(radius=3), **keywords)[0] != original
    assert model_identity(model, **{**keywords, "data_sha256": "dataset-b"})[0] != original
    assert model_identity(model, **{**keywords, "training_config": {"trees": 200}})[0] != original
    assert (
        model_identity(model, **{**keywords, "source_sha256": {"model.py": "code-b"}})[0]
        != original
    )
    assert provenance["model_state_sha256"] == model_state_fingerprint(model)


def test_comparability_excludes_fitted_incumbents_and_ignores_interval_radius() -> None:
    original = baseline(radius=1.0)
    evaluated = baseline(radius=100.0)
    original.version = "old-artifact"
    assert comparable_incumbent(original, evaluated)[0]
    assert not comparable_incumbent(baseline("B1"), evaluated)[0]
    assert not comparable_incumbent(baseline("B3"), baseline("B3"))[0]
    assert not comparable_incumbent(original.base, evaluated)[0]
    original.feature_contract["version"] = "different"
    assert not comparable_incumbent(original, evaluated)[0]


def test_identical_registration_is_idempotent_and_assessments_are_append_only(
    tmp_path: Path,
) -> None:
    registry = Registry(tmp_path)
    model = baseline()
    registry.register(model, {"wape": 0.2}, version="model", metadata={"role": "challenger"})
    manifest_path = tmp_path / "model" / "manifest.json"
    artifact_path = tmp_path / "model" / "model.pkl"
    original_manifest = manifest_path.read_bytes()
    original_model = artifact_path.read_bytes()
    registry.register(model, {"wape": 0.2}, version="model", metadata={"role": "challenger"})
    first = registry.record_assessment("model", passing_gates(), metadata={"run": "first"})
    first_path = tmp_path / "model" / "assessments" / f"{first['assessment_id']}.json"
    first_bytes = first_path.read_bytes()
    second = registry.record_assessment("model", passing_gates(20.0), metadata={"run": "second"})
    assert first["assessment_id"] != second["assessment_id"]
    assert first_path.read_bytes() == first_bytes
    assert manifest_path.read_bytes() == original_manifest
    assert artifact_path.read_bytes() == original_model
    view = registry.manifest("model")
    assert view["assessment_count"] == 2
    assert view["latest_assessment"]["metadata"]["run"] == "second"
    assert [gate["name"] for gate in view["gates"] if not gate["passed"]] == ["latency"]
    assert registry.list()[0]["latest_assessment"] == second
    assert registry.load("model").version == "model"
    with pytest.raises(ValueError, match="six distinct"):
        registry.record_assessment("model", passing_gates()[:1])
    with pytest.raises(FileExistsError, match="provenance"):
        registry.register(model, {"wape": 9.0}, version="model", metadata={"role": "challenger"})


def test_assessment_cannot_claim_evidence_for_another_artifact(tmp_path: Path) -> None:
    registry = Registry(tmp_path)
    registry.register(baseline(), {}, version="one")
    assessment = registry.record_assessment("one", passing_gates())
    path = tmp_path / "one" / "assessments" / f"{assessment['assessment_id']}.json"
    assessment["artifact_sha256"] = "different-artifact"
    path.write_text(json.dumps(assessment), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        registry.load("one")
