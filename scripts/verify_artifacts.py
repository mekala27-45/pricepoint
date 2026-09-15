"""Recompute release figures from committed observations, offline."""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist, fmean, stdev
from typing import Any

import numpy as np
import polars as pl
import statsmodels.api as sm

from scripts.paths import project_root

ROOT = project_root()
ARTIFACTS = ROOT / "artifacts"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    errors: list[str], name: str, observed: Any, expected: Any, tolerance: float = 1e-9
) -> None:
    if observed is None or expected is None:
        valid = observed is expected
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        valid = isinstance(observed, (float, int)) and math.isclose(
            float(observed),
            float(expected),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    else:
        valid = observed == expected
    if not valid:
        errors.append(f"{name}: stored {observed!r}, recomputed {expected!r}")


def _wape(frame: pl.DataFrame) -> float | None:
    denominator = float(frame["actual"].abs().sum())
    if denominator == 0:
        return None
    return float((frame["actual"] - frame["predicted"]).abs().sum()) / denominator


def verify_backtest(artifacts: Path) -> list[str]:
    """Recompute fold/category errors, scale errors, summaries and held-out coverage."""
    report = read_json(artifacts / "backtest.json")
    predictions = pl.read_parquet(artifacts / "predictions.parquet")
    training = pl.read_parquet(artifacts / "training_features.parquet")
    errors: list[str] = []
    key = pl.struct("fold", "model", "product_id")
    compare(
        errors,
        "prediction unique keys",
        predictions.select(key.n_unique()).item(),
        predictions.height,
    )
    compare(errors, "temporal shuffle", report["methodology"]["shuffled"], False)
    split_rows = {int(row["fold"]): row for row in report["split_metadata"]}
    scale_cache: dict[int, pl.DataFrame] = {}
    for fold, split in split_rows.items():
        cutoff = date.fromisoformat(split["fit_end"])
        fit = training.filter(pl.col("week") <= cutoff).sort("product_id", "week")
        scale_cache[fold] = fit.group_by("product_id").agg(
            pl.col("units").diff().abs().mean().alias("scale")
        )
        test_week = date.fromisoformat(split["test_week"])
        compare(
            errors,
            f"fold{fold} decision gap",
            (test_week - date.fromisoformat(split["decision_as_of"])).days,
            7,
        )
        compare(errors, f"fold{fold} fit gap", (test_week - cutoff).days, 28)
        compare(
            errors,
            f"fold{fold} calibration gap",
            (test_week - date.fromisoformat(split["calibration_week"])).days,
            14,
        )
    for row in report["folds"]:
        fold = int(row["fold"])
        subset = predictions.filter((pl.col("fold") == fold) & (pl.col("model") == row["model"]))
        label = f"fold{fold}/{row['model']}"
        compare(errors, label + " rows", row["rows"], subset.height)
        compare(errors, label + " WAPE", row["wape"], _wape(subset))
        scaled = subset.join(scale_cache[fold], on="product_id", how="left")
        valid = scaled.filter(pl.col("scale") > 1e-12)
        mase = (
            float(((valid["actual"] - valid["predicted"]).abs() / valid["scale"]).mean())
            if valid.height
            else None
        )
        compare(errors, label + " MASE", row["mase"], mase)
        compare(
            errors,
            label + " MASE exclusions",
            row["mase_excluded_rows"],
            subset.height - valid.height,
        )
        compare(
            errors,
            label + " prediction week",
            subset["week"].unique().to_list(),
            [row["test_week"]],
        )
    for row in report["category_metrics"]:
        subset = predictions.filter(
            (pl.col("category") == row["category"]) & (pl.col("model") == row["model"])
        )
        compare(errors, f"{row['model']}/{row['category']} WAPE", row["wape"], _wape(subset))
        compare(errors, f"{row['model']}/{row['category']} rows", row["rows"], subset.height)
    for row in report["summary"]:
        for metric in ("wape", "mase"):
            values = [
                float(fold[metric])
                for fold in report["folds"]
                if fold["model"] == row["model"] and fold[metric] is not None
            ]
            compare(errors, f"{row['model']}/{metric} mean", row[metric]["mean"], fmean(values))
            compare(
                errors,
                f"{row['model']}/{metric} sample SD",
                row[metric]["std"],
                stdev(values) if len(values) > 1 else None,
            )
            compare(errors, f"{row['model']}/{metric} folds", row[metric]["n"], len(values))
    intervals = predictions.filter(pl.col("low").is_not_null() & pl.col("high").is_not_null())
    coverage = report["coverage"]
    actual_coverage = intervals.select(
        ((pl.col("actual") >= pl.col("low")) & (pl.col("actual") <= pl.col("high"))).mean()
    ).item()
    compare(errors, "conformal total coverage", coverage["conformal"], actual_coverage)
    compare(errors, "coverage rows", coverage["test_rows"], intervals.height)
    quantile_hits = 0.0
    quantile_rows = 0
    for row in coverage["folds"]:
        subset = intervals.filter(pl.col("fold") == row["fold"])
        covered = subset.select(
            ((pl.col("actual") >= pl.col("low")) & (pl.col("actual") <= pl.col("high"))).mean()
        ).item()
        compare(errors, f"fold{row['fold']} conformal coverage", row["conformal_coverage"], covered)
        compare(
            errors,
            f"fold{row['fold']} interval width",
            row["conformal_mean_width"],
            (subset["high"] - subset["low"]).mean(),
        )
        quantile_hits += row["quantile_coverage"] * row["test_rows"]
        quantile_rows += row["test_rows"]
    # Quantile bounds are not stored individually; this verifies the weighted fold reduction.
    compare(
        errors, "weighted quantile coverage", coverage["quantile"], quantile_hits / quantile_rows
    )
    return errors


def verify_elasticity(artifacts: Path) -> list[str]:
    """Refit the final category associations and clustered uncertainty from stored training rows."""
    report = read_json(artifacts / "backtest.json")
    training = pl.read_parquet(artifacts / "training_features.parquet")
    errors: list[str] = []
    controls = ["log_price", "week_sin", "week_cos", "trend", "zero_fraction"]
    critical = NormalDist().inv_cdf(0.975)
    for row in report["elasticity"]:
        if row["status"] != "estimated":
            continue
        subset = training.filter(pl.col("category") == row["category"]).with_columns(
            pl.col("units").log1p().alias("log_units")
        )
        groups = subset["product_id"].to_numpy()
        y = subset["log_units"].to_numpy()
        x = subset.select(controls).to_numpy()
        covariance: dict[str, Any] = {
            "cov_type": "cluster",
            "cov_kwds": {"groups": groups, "use_correction": True},
        }
        if subset["product_id"].n_unique() == 1:
            covariance = {"cov_type": "HC3"}
        before = sm.OLS(y, np.column_stack([np.ones(len(y)), x[:, 0]])).fit(**covariance)
        centered = subset.with_columns(
            *[
                (pl.col(name) - pl.col(name).mean().over("product_id")).alias(name)
                for name in [*controls, "log_units"]
            ]
        )
        after = sm.OLS(centered["log_units"].to_numpy(), centered.select(controls).to_numpy()).fit(
            **covariance
        )
        for label, estimate, position in (("before", before, 1), ("after", after, 0)):
            coefficient = float(estimate.params[position])
            se = float(estimate.bse[position])
            compare(errors, f"{row['category']}/{label} coefficient", row[label], coefficient, 1e-7)
            compare(
                errors, f"{row['category']}/{label} standard error", row[label + "_se"], se, 1e-7
            )
            compare(
                errors,
                f"{row['category']}/{label} CI low",
                row[label + "_low"],
                coefficient - critical * se,
                1e-7,
            )
            compare(
                errors,
                f"{row['category']}/{label} CI high",
                row[label + "_high"],
                coefficient + critical * se,
                1e-7,
            )
        compare(errors, row["category"] + " observations", row["rows"], subset.height)
        compare(
            errors, row["category"] + " products", row["products"], subset["product_id"].n_unique()
        )
    return errors


def verify_latency(path: Path) -> list[str]:
    artifact = read_json(path)
    errors: list[str] = []
    samples = np.asarray(artifact["latency_samples_ms"], dtype=float)
    if not len(samples) or not np.isfinite(samples).all() or (samples < 0).any():
        return [f"{path.name}: latency samples must be nonempty, finite and nonnegative"]
    for percentile in (50, 95, 99):
        compare(
            errors,
            f"{path.name} p{percentile}",
            artifact[f"p{percentile}_ms"],
            float(np.percentile(samples, percentile)),
        )
    count = (
        artifact["successful_requests"]
        if "successful_requests" in artifact
        else artifact["samples"]
    )
    compare(errors, path.name + " samples", count, len(samples))
    if "errors" in artifact:
        compare(errors, path.name + " request errors", artifact["errors"], 0)
        compare(
            errors,
            path.name + " throughput",
            artifact["throughput_rps"],
            len(samples) / artifact["duration_actual_s"],
        )
    if "histogram" in artifact:
        histogram = artifact["histogram"]
        edges = [float(row["low_ms"]) for row in histogram]
        edges.append(
            float("inf") if histogram[-1]["high_ms"] is None else float(histogram[-1]["high_ms"])
        )
        expected, _ = np.histogram(samples, bins=edges)
        compare(
            errors, path.name + " histogram", [row["count"] for row in histogram], expected.tolist()
        )
        compare(
            errors,
            path.name + " histogram population",
            sum(row["count"] for row in histogram),
            len(samples),
        )
    return errors


def verify_bundle(root: Path) -> list[str]:
    bundle = read_json(root / "web/public/bundle.json")
    report = read_json(root / "artifacts/backtest.json")
    errors: list[str] = []
    monitoring = read_json(root / "artifacts/monitoring.json")
    if bundle["monitoring"] != monitoring:
        errors.append("bundle monitoring differs from the complete recorded timeline")
    summaries = {row["model"]: row for row in report["summary"]}
    for row in bundle["backtest"]["summary"]:
        for metric in ("wape", "mase"):
            for stat in ("mean", "std"):
                compare(
                    errors,
                    f"bundle {row['model']}/{metric}/{stat}",
                    row[f"{metric}_{stat}"],
                    summaries[row["model"]][metric][stat],
                )
    folds = {(row["fold"], row["model"]): row for row in report["folds"]}
    compare(errors, "bundle fold population", len(bundle["backtest"]["folds"]), len(folds))
    for row in bundle["backtest"]["folds"]:
        for field in ("wape", "mase", "rows", "test_week"):
            compare(
                errors,
                f"bundle fold{row['fold']}/{row['model']}/{field}",
                row[field],
                folds[row["fold"], row["model"]][field],
            )
    groups = {row["category"]: row for row in report["elasticity"]}
    compare(errors, "bundle elasticity population", len(bundle["elasticity"]), len(groups))
    for row in bundle["elasticity"]:
        for field in ("before", "after", "before_low", "before_high", "after_low", "after_high"):
            if field in groups[row["category"]]:
                compare(
                    errors,
                    f"bundle {row['category']}/{field}",
                    row[field],
                    groups[row["category"]][field],
                )
    for product in bundle["products"]:
        for row in product["curve"]:
            compare(
                errors,
                f"curve {product['id']}/{row['price']} revenue",
                row["revenue"],
                row["price"] * row["units"],
            )
            if not 0 <= row["interval_low"] <= row["interval_high"]:
                errors.append(f"curve {product['id']}: invalid uncertainty interval")
    return errors


def verify_monitoring(artifacts: Path) -> list[str]:
    """Reconcile observations, cooldown decisions and delayed refits without model replay.

    The saved PSI, KS and WAPE observations are inputs here. Their underlying
    weekly predictions are not stored, so this checks the policy and chronology,
    not the statistical observations that require rerunning the simulation.
    """
    from pricepoint_core.schemas import FEATURE_NAMES

    timeline = read_json(artifacts / "monitoring.json")
    summary = read_json(artifacts / "monitoring_summary.json")
    errors: list[str] = []
    if not timeline:
        return ["monitoring timeline must contain observations"]
    compare(errors, "monitoring weeks", summary["weeks"], len(timeline))
    compare(
        errors, "monitoring triggers", summary["triggers"], sum(row["retrain"] for row in timeline)
    )
    completed_action = "refit completed using labels before decision cutoff"
    compare(
        errors,
        "monitoring completed refits",
        summary["completed_refits"],
        sum(row["action"] == completed_action for row in timeline),
    )
    first_training_week = pl.read_parquet(
        artifacts / "training_features.parquet", columns=["week"]
    )["week"].min()
    last_complete_week = (
        pl.read_parquet(artifacts / "serving_panel.parquet", columns=["week", "is_complete_week"])
        .filter(pl.col("is_complete_week"))["week"]
        .max()
    )
    compare(
        errors,
        "monitoring warmup boundary",
        timeline[0]["week"],
        (first_training_week + timedelta(weeks=summary["warmup_weeks"])).isoformat(),
    )
    compare(
        errors,
        "monitoring final complete week",
        timeline[-1]["week"],
        last_complete_week.isoformat(),
    )
    pending: date | None = None
    previous_week: date | None = None
    previous_train_end: str | None = None
    previous_reference_rows: int | None = None
    last_fired: date | None = None
    recent_errors: list[float] = []
    baseline = timeline[0]["baseline_wape"]
    if not math.isfinite(baseline) or baseline <= 0:
        return [*errors, "monitoring baseline WAPE must be finite and positive"]
    for index, row in enumerate(timeline):
        label = f"monitoring row{index}/{row['week']}"
        week = date.fromisoformat(row["week"])
        cutoff = week - timedelta(weeks=1)
        observed = week + timedelta(weeks=1)
        compare(errors, label + " Monday", week.weekday(), 0)
        if previous_week is not None:
            compare(errors, label + " chronology", (week - previous_week).days, 7)
        compare(
            errors, label + " observation availability", row["observed_at"], observed.isoformat()
        )
        compare(errors, label + " decision cutoff", row["decision_as_of"], cutoff.isoformat())
        compare(errors, label + " baseline", row["baseline_wape"], baseline)
        compare(errors, label + " PSI feature schema", set(row["psi"]), set(FEATURE_NAMES))
        if not all(math.isfinite(value) and value >= 0 for value in row["psi"].values()):
            errors.append(label + " PSI observations must be finite and nonnegative")
        if not math.isfinite(row["ks"]) or not 0 <= row["ks"] <= 1:
            errors.append(label + " KS must lie in [0, 1]")
        compare(errors, label + " undefined WAPE", row["undefined_wape"], row["wape"] is None)
        if row["wape"] is None:
            recent_errors.clear()
        elif math.isfinite(row["wape"]) and row["wape"] >= 0:
            recent_errors.append(row["wape"])
        else:
            errors.append(label + " WAPE must be finite and nonnegative or null")

        activated = pending if pending is not None and pending <= cutoff else None
        compare(
            errors,
            label + " completed action",
            row["action"],
            completed_action if activated is not None else "continued incumbent",
        )
        compare(
            errors,
            label + " completed trigger observation",
            row["refit_trigger_observed_at"],
            activated.isoformat() if activated is not None else None,
        )
        if date.fromisoformat(row["train_end"]) >= cutoff:
            errors.append(label + " training labels reach or exceed the decision cutoff")
        if not isinstance(row["reference_rows"], int) or row["reference_rows"] < 1:
            errors.append(label + " reference population must be positive")
        if activated is not None:
            pending = None
            compare(
                errors,
                label + " refit training end",
                row["train_end"],
                (cutoff - timedelta(weeks=1)).isoformat(),
            )
            if (
                previous_reference_rows is not None
                and row["reference_rows"] <= previous_reference_rows
            ):
                errors.append(label + " expanding refit must add reference observations")
        elif previous_week is not None:
            compare(errors, label + " unchanged training end", row["train_end"], previous_train_end)
            compare(
                errors,
                label + " unchanged reference population",
                row["reference_rows"],
                previous_reference_rows,
            )

        drifted = any(value > 0.25 for value in row["psi"].values())
        degraded = len(recent_errors) >= 4 and fmean(recent_errors[-4:]) > baseline * 1.1
        cooling = last_fired is not None and (week - last_fired).days < 14
        fired = (drifted or degraded) and not cooling
        compare(errors, label + " trigger policy", row["retrain"], fired)
        if fired:
            pending = min(pending, observed) if pending is not None else observed
            last_fired = week
        compare(
            errors,
            label + " scheduled decision cutoff",
            row["scheduled_as_of"],
            pending.isoformat() if pending else None,
        )
        previous_week = week
        previous_train_end = row["train_end"]
        previous_reference_rows = row["reference_rows"]
    return errors


def verify_experiment(artifacts: Path) -> list[str]:
    """Recompute the stated normal-approximation design from held-out residuals."""
    report = read_json(artifacts / "experiment.json")
    predictions = pl.read_parquet(artifacts / "predictions.parquet").filter(
        (pl.col("model") == "C2") & (pl.col("fold") == 8)
    )
    residuals = np.log1p(predictions["actual"].to_numpy()) - np.log1p(
        predictions["predicted"].to_numpy()
    )
    sigma = stdev(residuals.tolist())
    normal = NormalDist()
    effect = abs(report["assumed_elasticity"] * math.log1p(report["price_change"]))
    critical = normal.inv_cdf(1 - report["alpha"] / 2) + normal.inv_cdf(report["power"])
    units_per_arm = math.ceil(2 * critical**2 * sigma**2 / effect**2)
    errors: list[str] = []
    compare(errors, "experiment residual SD", report["sigma"], sigma)
    compare(errors, "experiment units per arm", report["units_per_arm"], units_per_arm)
    compare(
        errors,
        "experiment weeks",
        report["weeks"],
        math.ceil(2 * units_per_arm / report["products_per_week"]),
    )
    return errors


def verify_synthetic(artifacts: Path) -> list[str]:
    """Independently regenerate the published process and refit its OLS equations."""
    report = read_json(artifacts / "synthetic_validation.json")
    errors: list[str] = []
    categories, products, weeks = 4, 32, 104
    compare(errors, "synthetic rows", report["rows"], categories * products * weeks)
    compare(errors, "synthetic products", report["products"], categories * products)
    compare(errors, "synthetic weeks", report["weeks"], weeks)
    compare(errors, "synthetic categories", report["categories"], categories)
    compare(errors, "synthetic confidence level", report["confidence_level"], 0.95)
    expected_groups = {f"synthetic_{index}" for index in range(categories)}
    compare(
        errors,
        "synthetic estimate groups",
        {row["category"] for row in report["estimates"]},
        expected_groups,
    )
    compare(errors, "synthetic estimate population", len(report["estimates"]), categories)
    shocks = np.random.default_rng(report["seed"]).normal(
        0.0, 0.18, (categories, products, weeks, 2)
    )
    product = np.repeat(np.arange(products), weeks)
    week = np.tile(np.arange(weeks), products)
    sine = np.sin(2 * np.pi * week / 52)
    cosine = np.cos(2 * np.pi * week / 52)
    proxy = ((week + product) % 13) / 13
    critical = NormalDist().inv_cdf(0.975)
    recovered = 0
    for row in report["estimates"]:
        category = row["category"]
        if category not in expected_groups:
            continue
        shock = shocks[int(category.rsplit("_", 1)[1])].reshape(-1, 2)
        log_price = 0.8 + product / products + shock[:, 0]
        outcome = (
            5
            + 3 * product / products
            + report["true_coefficient"] * log_price
            + 0.25 * sine
            - 0.08 * cosine
            + 0.003 * week
            - 0.2 * proxy
            + shock[:, 1]
        )
        controls = np.column_stack([log_price, sine, cosine, week, proxy])
        covariance = {
            "cov_type": "cluster",
            "cov_kwds": {"groups": product, "use_correction": True},
        }
        before = sm.OLS(outcome, np.column_stack([np.ones(len(outcome)), log_price])).fit(
            **covariance
        )
        within_y = outcome.reshape(products, weeks)
        within_y = (within_y - within_y.mean(axis=1, keepdims=True)).reshape(-1)
        within_x = controls.reshape(products, weeks, -1)
        within_x = (within_x - within_x.mean(axis=1, keepdims=True)).reshape(-1, controls.shape[1])
        after = sm.OLS(within_y, within_x).fit(**covariance)
        for label, estimate, position in (("before", before, 1), ("after", after, 0)):
            coefficient, se = float(estimate.params[position]), float(estimate.bse[position])
            for suffix, expected in (
                ("", coefficient),
                ("_se", se),
                ("_low", coefficient - critical * se),
                ("_high", coefficient + critical * se),
            ):
                compare(
                    errors,
                    f"synthetic {category}/{label}{suffix}",
                    row[label + suffix],
                    expected,
                    1e-7,
                )
        contains = bool(
            after.params[0] - critical * after.bse[0]
            <= report["true_coefficient"]
            <= after.params[0] + critical * after.bse[0]
        )
        recovered += contains
        compare(
            errors, f"synthetic {category}/recovered", row["contains_true_coefficient"], contains
        )
        compare(
            errors,
            f"synthetic {category}/truth",
            row["true_coefficient"],
            report["true_coefficient"],
        )
        compare(errors, f"synthetic {category}/rows", row["rows"], products * weeks)
        compare(errors, f"synthetic {category}/products", row["products"], products)
    compare(errors, "synthetic recovered categories", report["categories_recovered"], recovered)
    return errors


def verify_shadow(artifacts: Path) -> list[str]:
    report = read_json(artifacts / "shadow.json")
    observations = read_json(artifacts / "shadow_observations.json")
    errors: list[str] = []
    differences = [abs(row["incumbent_units"] - row["candidate_units"]) for row in observations]
    compare(errors, "shadow samples", report["samples"], len(differences))
    compare(errors, "shadow mean", report["mean_units"], fmean(differences))
    for percentile in (50, 95, 99):
        compare(
            errors,
            f"shadow p{percentile}",
            report[f"p{percentile}_units"],
            float(np.percentile(differences, percentile)),
        )
    for index, (row, difference) in enumerate(zip(observations, differences, strict=True)):
        compare(errors, f"shadow observation{index}", row["absolute_disagreement"], difference)
    return errors


def verify_all(root: Path = ROOT, *, reports: bool = True) -> list[str]:
    from pricepoint_models.registry import Registry

    artifacts = root / "artifacts"
    errors = verify_backtest(artifacts) + verify_elasticity(artifacts) + verify_bundle(root)
    errors.extend(verify_shadow(artifacts))
    errors.extend(verify_monitoring(artifacts))
    errors.extend(verify_experiment(artifacts))
    errors.extend(verify_synthetic(artifacts))
    for name in ("latency-gate.json", "loadtest-inprocess.json"):
        errors.extend(verify_latency(artifacts / name))
    container = artifacts / "loadtest-container.json"
    if container.exists():
        errors.extend(verify_latency(container))
    registry = Registry(artifacts / "registry")
    entries = registry.list()
    if not entries or registry.incumbent_version() is None:
        errors.append("Registry must contain an incumbent and versioned artifacts")
    for entry in entries:
        try:
            registry.load(entry["version"])
        except (ValueError, OSError) as error:
            errors.append(f"registry {entry['version']}: {error}")
    if reports:
        from scripts.publish_results import render_sections

        for name, contents in render_sections().items():
            source = artifacts / "reports" / f"{name}.md"
            if (
                not source.exists()
                or source.read_text(encoding="utf-8").strip() != contents.strip()
            ):
                errors.append(f"{name}: stored report fragment differs from recomputed section")
    return errors


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--without-reports", action="store_true")
    args = parser.parse_args(argv)
    errors = verify_all(args.root, reports=not args.without_reports)
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        "Artifact gate passed: metrics, intervals, elasticity, registry, latency, "
        "monitoring, experiment sizing, synthetic recovery and publication evidence"
    )


if __name__ == "__main__":
    main()
