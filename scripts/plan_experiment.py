"""An explicitly assumption-based experiment planning calculation."""

import json
import math

import numpy as np
import polars as pl
from scipy.stats import norm

from scripts.evaluate import ROOT, write_json

predictions = pl.read_parquet(ROOT / "artifacts/predictions.parquet").filter(
    (pl.col("model") == "C2") & (pl.col("fold") == 8)
)
residuals = np.log1p(predictions["actual"].to_numpy()) - np.log1p(
    predictions["predicted"].to_numpy()
)
sigma = float(np.std(residuals, ddof=1))
elasticity, change, power, alpha, products = -1.5, 0.1, 0.8, 0.05, 200
effect = abs(elasticity * math.log1p(change))
n = math.ceil(2 * (norm.ppf(1 - alpha / 2) + norm.ppf(power)) ** 2 * sigma**2 / effect**2)
report = {
    "sigma": sigma,
    "assumed_elasticity": elasticity,
    "price_change": change,
    "power": power,
    "alpha": alpha,
    "units_per_arm": n,
    "products_per_week": products,
    "weeks": math.ceil(n / (products / 2)),
    "unit": "independent product-week observation, approximation only",
    "methodology": "Two-arm normal approximation using measured held-out log1p-demand forecast residual SD. Serial dependence and interference are not estimated, so actual sizing must use a clustered pilot.",
}
write_json(ROOT / "artifacts/experiment.json", report)
print(json.dumps(report, indent=2))
