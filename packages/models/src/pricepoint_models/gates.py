"""Promotion is refused when any required evidence is absent or fails."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from pricepoint_models.estimators import feature_contract

GATE_NAMES = (
    "wape_improvement",
    "category_non_regression",
    "latency",
    "coverage",
    "schema",
    "training_serving_skew",
)


@dataclass(frozen=True)
class GateEvidence:
    candidate_wape: float | None = None
    incumbent_wape: float | None = None
    candidate_category_wape: dict[str, float] = field(default_factory=dict)
    incumbent_category_wape: dict[str, float] = field(default_factory=dict)
    latency_p99_ms: float | None = None
    latency_samples: int | None = None
    coverage: float | None = None
    coverage_samples: int | None = None
    coverage_split: str | None = None
    nominal: float = 0.9
    candidate_schema: dict[str, Any] | None = None
    serving_schema: dict[str, Any] | None = None
    skew_max_abs: float | None = None
    skew_pairs: int | None = None
    skew_tolerance: float = 1e-9


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value >= 0


def evaluate_gates(evidence: GateEvidence) -> list[GateResult]:
    """Assess all six gates; held-out coverage and measured skew are mandatory."""
    candidate = evidence.candidate_wape
    incumbent = evidence.incumbent_wape
    wape_pass = bool(
        _finite(candidate)
        and _finite(incumbent)
        and incumbent is not None
        and candidate is not None
        and incumbent > 0
        and candidate <= incumbent * 0.98
    )
    categories = evidence.incumbent_category_wape
    challenger = evidence.candidate_category_wape
    category_pass = bool(categories) and set(categories) == set(challenger)
    if category_pass:
        category_pass = all(
            _finite(value)
            and _finite(challenger[category])
            and challenger[category] <= value * 1.05
            for category, value in categories.items()
        )
    latency_pass = bool(
        _finite(evidence.latency_p99_ms)
        and evidence.latency_p99_ms is not None
        and evidence.latency_p99_ms < 15
        and evidence.latency_samples is not None
        and evidence.latency_samples >= 100
    )
    coverage_pass = bool(
        _finite(evidence.coverage)
        and evidence.coverage is not None
        and 0 < evidence.nominal < 1
        and evidence.coverage <= 1
        and abs(evidence.coverage - evidence.nominal) <= 0.02 + 1e-12
        and evidence.coverage_samples is not None
        and evidence.coverage_samples > 0
        and evidence.coverage_split == "held_out_test"
    )
    schema_pass = bool(
        evidence.candidate_schema == feature_contract()
        and evidence.serving_schema == feature_contract()
    )
    skew_pass = bool(
        _finite(evidence.skew_max_abs)
        and evidence.skew_max_abs is not None
        and 0 < evidence.skew_tolerance <= 1e-8
        and evidence.skew_max_abs <= evidence.skew_tolerance
        and evidence.skew_pairs is not None
        and evidence.skew_pairs >= 500
    )
    return [
        GateResult(
            "wape_improvement",
            wape_pass,
            "At least 2% relative WAPE improvement over a positive incumbent WAPE is required",
            {"candidate": candidate, "incumbent": incumbent},
        ),
        GateResult(
            "category_non_regression",
            category_pass,
            "Every incumbent category must be present and degrade by at most 5% relative",
            {"candidate": challenger, "incumbent": categories},
        ),
        GateResult(
            "latency",
            latency_pass,
            "Measured p99 must be below 15ms with at least 100 single-prediction observations",
            {"p99_ms": evidence.latency_p99_ms, "samples": evidence.latency_samples},
        ),
        GateResult(
            "coverage",
            coverage_pass,
            "Held-out test coverage must be within 2 percentage points of nominal",
            {
                "coverage": evidence.coverage,
                "nominal": evidence.nominal,
                "samples": evidence.coverage_samples,
                "split": evidence.coverage_split,
            },
        ),
        GateResult(
            "schema",
            schema_pass,
            "Ordered feature names, Float64 types, and contract version must match exactly",
            {"candidate": evidence.candidate_schema, "serving": evidence.serving_schema},
        ),
        GateResult(
            "training_serving_skew",
            skew_pass,
            "Independent-path skew on at least 500 pairs must be within the stated tight tolerance",
            {
                "max_abs": evidence.skew_max_abs,
                "pairs": evidence.skew_pairs,
                "tolerance": evidence.skew_tolerance,
            },
        ),
    ]
