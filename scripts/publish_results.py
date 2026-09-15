"""Render published measurements from machine-readable evidence."""

from __future__ import annotations

import json
from typing import Any

from scripts.evaluate import ROOT, write_json


def load(name: str) -> Any:
    return json.loads((ROOT / "artifacts" / name).read_text(encoding="utf-8"))


def table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(row) + " |" for row in rows]
    )


def number(value: float | None, spec: str = ".3f") -> str:
    return format(value, spec) if value is not None else "Undefined"


def render_sections() -> dict[str, str]:
    report = load("backtest.json")
    skew, leakage = load("skew.json"), load("leakage.json")
    result: dict[str, str] = {}
    result["summary"] = table(
        ["Model", "WAPE (mean +/- SD)", "MASE (mean +/- SD)"],
        [
            [
                row["model"],
                f"{row['wape']['mean']:.4f} +/- {row['wape']['std']:.4f}",
                f"{row['mase']['mean']:.4f} +/- {row['mase']['std']:.4f}",
            ]
            for row in report["summary"]
        ],
    )
    result["skew"] = (
        f"1. {skew['pairs']} sampled feature vectors, two independent computation paths, "
        f"maximum absolute difference of {skew['max_abs_difference']:.3e}.\n\n"
        f"2. {leakage['pairs']} future-deletion checks passed with maximum difference "
        f"{leakage['max_abs_difference']:.3e}. Stored pairs and the panel hash make the sample repeatable."
    )
    result["folds"] = table(
        ["Fold", "Target week", "Model", "WAPE", "MASE", "Products", "Undefined MASE rows"],
        [
            [
                str(row["fold"]),
                row["test_week"],
                row["model"],
                number(row["wape"]),
                number(row["mase"]),
                str(row["rows"]),
                str(row["mase_excluded_rows"]),
            ]
            for row in report["folds"]
        ],
    )
    result["splits"] = table(
        ["Fold", "Fit labels through", "Calibration week", "Decision cutoff / gap", "Test week"],
        [
            [
                str(row["fold"]),
                row["fit_end"],
                row["calibration_week"],
                row["decision_as_of"],
                row["test_week"],
            ]
            for row in report["split_metadata"]
        ],
    )
    elastic = report["elasticity"]
    positive_before = sum(row.get("before") is not None and row["before"] > 0 for row in elastic)
    positive_after = sum(row.get("after") is not None and row["after"] > 0 for row in elastic)
    result["elasticity"] = (
        f"{positive_before} of {len(elastic)} inferred groups have a positive unadjusted price coefficient; "
        f"{positive_after} have a positive adjusted coefficient.\n\n"
        + table(
            ["Inferred group", "Before controls", "Before CI", "After controls", "After CI"],
            [
                [
                    row["category"],
                    number(row.get("before")),
                    f"[{number(row.get('before_low'))}, {number(row.get('before_high'))}]",
                    number(row.get("after")),
                    f"[{number(row.get('after_low'))}, {number(row.get('after_high'))}]",
                ]
                for row in elastic
            ],
        )
    )
    coverage = report["coverage"]
    result["coverage"] = (
        f"Nominal coverage: {coverage['nominal']:.2%}. Pooled held-out conformal coverage: "
        f"{coverage['conformal']:.2%}. Quantile comparison coverage: {coverage['quantile']:.2%} "
        f"across {coverage['test_rows']:,} product-week observations.\n\n"
        + table(
            [
                "Fold",
                "Conformal coverage",
                "Quantile coverage",
                "Conformal width (units)",
                "Quantile width (units)",
            ],
            [
                [
                    str(row["fold"]),
                    f"{row['conformal_coverage']:.2%}",
                    f"{row['quantile_coverage']:.2%}",
                    f"{row['conformal_mean_width']:.2f}",
                    f"{row['quantile_mean_width']:.2f}",
                ]
                for row in coverage["folds"]
            ],
        )
    )
    promotion = load("promotion.json")
    result["promotion"] = (
        f"Incumbent: {promotion['incumbent']}. Candidate promoted: {str(promotion['promoted']).lower()}.\n\n"
        + table(
            ["Gate", "Result", "Rule"],
            [
                [row["name"], "Pass" if row["passed"] else "Refused", row["reason"]]
                for row in promotion["gates"]
            ],
        )
    )
    latency = load("loadtest-inprocess.json")
    result["latency"] = (
        table(
            ["Transport", "p50 (ms)", "p95 (ms)", "p99 (ms)", "Successful requests/s", "Errors"],
            [
                [
                    latency["transport"],
                    f"{latency['p50_ms']:.3f}",
                    f"{latency['p95_ms']:.3f}",
                    f"{latency['p99_ms']:.3f}",
                    f"{latency['throughput_rps']:.2f}",
                    str(latency["errors"]),
                ]
            ],
        )
        + f"\n\nMeasured {latency['measured_at']} on {latency['platform']}, Python {latency['python']}. "
        + f"Concurrency {latency['concurrency']}, duration {latency['duration_requested_s']:.0f}s "
        + f"(actual {latency['duration_actual_s']:.3f}s), warmup {latency['warmup_requests']} requests. "
        + latency["methodology"]
        + "\n\n"
        + table(
            ["Latency bin (ms)", "Successful requests"],
            [
                [
                    f"{row['low_ms']:g} to {number(row['high_ms'], 'g') if row['high_ms'] is not None else 'infinity'}",
                    str(row["count"]),
                ]
                for row in latency["histogram"]
            ],
        )
    )
    gate_latency = load("latency-gate.json")
    result["gate_latency"] = (
        f"Candidate inference p99: {gate_latency['p99_ms']:.3f} ms from {gate_latency['samples']} "
        f"measured requests. {gate_latency['methodology']}"
    )
    if (ROOT / "artifacts/loadtest-container.json").exists():
        container = load("loadtest-container.json")
        result["container"] = (
            table(
                ["p50 (ms)", "p95 (ms)", "p99 (ms)", "Successful requests/s", "Errors"],
                [
                    [
                        f"{container['p50_ms']:.3f}",
                        f"{container['p95_ms']:.3f}",
                        f"{container['p99_ms']:.3f}",
                        f"{container['throughput_rps']:.2f}",
                        str(container["errors"]),
                    ]
                ],
            )
            + f"\n\nContainer TCP measurement: {container['duration_requested_s']:.0f}s at concurrency "
            + f"{container['concurrency']}, {container['warmup_requests']} warmup requests, "
            + f"{container['platform']}. CI stores the resolved base and built image identifiers."
            + f"\n\n{container['methodology']}"
            + "\n\n"
            + table(
                ["Latency bin (ms)", "Successful requests"],
                [
                    [
                        f"{row['low_ms']:g} to "
                        + (f"{row['high_ms']:g}" if row["high_ms"] is not None else "infinity"),
                        str(row["count"]),
                    ]
                    for row in container["histogram"]
                ],
            )
        )
    else:
        result["container"] = (
            "Container latency has not been measured locally. CI builds the image and publishes a TCP benchmark artifact. No container latency claim is made until that run is retrieved."
        )
    shadow = load("shadow.json")
    result["shadow"] = (
        table(
            ["Scored pairs", "Mean disagreement (units)", "p50", "p95", "p99"],
            [
                [
                    str(shadow["samples"]),
                    f"{shadow['mean_units']:.3f}",
                    f"{shadow['p50_units']:.3f}",
                    f"{shadow['p95_units']:.3f}",
                    f"{shadow['p99_units']:.3f}",
                ]
            ],
        )
        + "\n\n"
        + shadow["methodology"]
    )
    timeline = load("monitoring.json")
    monitoring = load("monitoring_summary.json")
    result["monitoring"] = (
        f"{monitoring['weeks']} evaluated weeks, {monitoring['triggers']} triggers, "
        f"{monitoring['completed_refits']} completed refits after "
        f"{monitoring['warmup_weeks']} initial weeks.\n\n"
        + table(
            ["Sales week", "Observed at", "WAPE", "Max feature PSI", "Trigger", "Action"],
            [
                [
                    row["week"],
                    row["observed_at"],
                    number(row["wape"]),
                    f"{max(row['psi'].values()):.3f}",
                    "Yes" if row["retrain"] else "No",
                    row["action"],
                ]
                for row in timeline
            ],
        )
    )
    exp = load("experiment.json")
    result["experiment"] = (
        f"Measured log-demand forecast residual SD: {exp['sigma']:.3f}. Under a planning assumption "
        f"of elasticity {exp['assumed_elasticity']:.2f}, a {exp['price_change']:.0%} price difference, "
        f"{exp['power']:.0%} power and two-sided alpha {exp['alpha']:.2f}, the independent-unit approximation "
        f"requires {exp['units_per_arm']:,} product-week observations per arm. With "
        f"{exp['products_per_week']} participating products split equally between arms, this implies "
        f"{exp['weeks']} weeks. These are planning assumptions, not a validated experiment sample size."
    )
    synthetic = load("synthetic_validation.json")
    result["synthetic"] = "Synthetic validation evidence:\n\n" + "\n".join(
        "    " + line for line in json.dumps(synthetic, indent=2).splitlines()
    )
    return result


def block(name: str, sections: dict[str, str]) -> str:
    return f"<!-- {name}:start -->\n{sections[name]}\n<!-- {name}:end -->"


def publish() -> None:
    sections = render_sections()
    output = ROOT / "artifacts/reports"
    output.mkdir(parents=True, exist_ok=True)
    for key, section in sections.items():
        (output / f"{key}.md").write_text(section + "\n", encoding="utf-8")
    editorial = (ROOT / "docs/results-template.md").read_text(encoding="utf-8")
    for key in sections:
        editorial = editorial.replace("{{" + key + "}}", block(key, sections))
    (ROOT / "RESULTS.md").write_text(editorial, encoding="utf-8")
    readme = (ROOT / "docs/readme-template.md").read_text(encoding="utf-8")
    for key in ("summary", "skew"):
        readme = readme.replace("{{" + key + "}}", block(key, sections))
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    registry: dict[str, Any] = {"schema_version": "1", "claims": [], "blocks": []}
    for key in sections:
        registry["blocks"].append(
            {"id": key, "document": "RESULTS.md", "source": f"artifacts/reports/{key}.md"}
        )
    for key in ("summary", "skew"):
        registry["blocks"].append(
            {"id": key, "document": "README.md", "source": f"artifacts/reports/{key}.md"}
        )
    write_json(ROOT / "artifacts/claims.json", registry)
    print("Rendered measured results and their claim registry")


if __name__ == "__main__":
    publish()
