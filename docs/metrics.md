# Metrics and temporal evaluation

Use [RESULTS](../RESULTS.md) for measured values and [backtest.json](../artifacts/backtest.json) for fold-level evidence. This page defines what those values mean.

## Why WAPE and MASE

For observed demand `y` and prediction `p`, weighted absolute percentage error is:

```text
WAPE = sum(abs(y - p)) / sum(abs(y))
```

WAPE weights observations by their contribution to total demand. The code stores it as a ratio; a displayed percentage is that ratio multiplied by one hundred. A completely zero-demand group has an undefined denominator and is reported as undefined, not silently replaced with zero. A WAPE above one means absolute error exceeds total observed demand.

MAPE is undefined at zero and grows arbitrarily large near zero. A product-week retail panel contains real observed zero-sale weeks. Dropping those rows, adding an arbitrary denominator floor, or averaging only sufficiently large products would let the evaluator choose the answer by changing inclusion rules. That is why this project does not publish MAPE.

Mean absolute scaled error compares each product's prediction error with that product's historical one-step naive error:

```text
scale(product) = mean(abs(y[t] - y[t-1])) over base-fit weeks
MASE = mean(abs(y - p) / scale(product)) over eligible held-out rows
```

The scale only uses base-fit labels from the same fold. Products with a zero or unavailable scale are excluded from MASE and counted explicitly. MASE gives each included prediction equal weight after scaling; it answers a different question from WAPE. A model can improve one while worsening the other.

## Fold chronology

For a target week beginning on Monday `T`:

| Event | Week |
|:--|:--|
| Latest base-fit target label | `T - 28 days` |
| Held-out calibration target label | `T - 14 days` |
| Decision cutoff and reserved decision gap | `T - 7 days` |
| Held-out forecast target | `T` |

Features have an exclusive cutoff. The forecast for `T` therefore uses panel rows strictly before `T - 7 days`; its most recent weekly history is `T - 14 days`. Calibration itself is a historical forecast with the same decision lag, so the base model cannot have fit on its calibration outcomes. The fit window expands; rows are never shuffled.

Product eligibility is recomputed from base-fit data inside each fold. There is no final-period universe projected backward into earlier folds. The minimum history and price-variation rules are specified in the [data documentation](data.md). Incomplete source-boundary weeks cannot become target labels.

The price feature is the last known price before the decision cutoff. A realized test-week price is never injected into a feature vector. This supports lagged-price forecasting evaluation, not identification of demand under a randomized future price change.

## Baselines and candidates

| Model | Prediction rule |
|:--|:--|
| B0 | Most recently available weekly demand. |
| B1 | Demand at the seasonal lag relative to the decision cutoff. |
| B2 | Mean of the most recent available demand weeks. |
| B3 | Global log-price regression for `log1p(gross units)`. |
| C1 | Separate group regressions with product fixed effects, calendar controls, trend, and zero-sale frequency. |
| C2 | LightGBM Tweedie regression using the ordered feature contract. |

The baseline lags obey the same exclusive decision cutoff as every other model. In particular, a seasonal lag is defined relative to that cutoff, so it is not permission to read a later target-aligned week. The exact feature definitions are in [data.md](data.md).

Tweedie loss accommodates nonnegative demand with a mass at zero and a long positive tail. It does not itself guarantee calibration, monotonic price response, or a causal interpretation. The estimator uses a fixed, recorded configuration rather than a search over held-out outcomes.

## Aggregation and uncertainty

Every model has one WAPE and MASE per fold. The summary reports the arithmetic mean of those fold metrics and their sample standard deviation, with the number of available folds. This is not a pooled demand-weighted WAPE across all folds. Category WAPE, by contrast, is recomputed from all held-out prediction rows in that category across folds. The artifact verifier checks both reductions independently.

Split conformal intervals use absolute calibration residuals and a finite-sample adjusted residual quantile. Lower bounds are clipped at zero. Calibration labels precede the test forecast. Empirical coverage is the fraction of test outcomes inside the interval, endpoints included. Aggregate coverage is weighted by test-row count, and mean interval widths are also reported because very wide intervals can cover well without being useful.

Temporal dependence, product dependence, and changing availability violate the simplest exchangeability assumptions behind exact conformal guarantees. Published coverage is held-out empirical evidence for this historical evaluation. It is not a distribution-free promise for future retail traffic.

LightGBM lower and upper quantile models provide the comparison. Their per-fold empirical coverages and widths are stored. The current artifact verifier recomputes conformal coverage from individual saved bounds; for the quantile comparison it verifies the weighted reduction of saved fold coverage because individual quantile bounds are not committed.

## Association estimates

C1 uses `log1p(units)` so zero-sale weeks remain in the regression. Its log-price coefficient approximates a conventional units elasticity only where demand is appreciably above zero. Product fixed effects are absorbed by within-product demeaning. Standard errors cluster by product, with the implementation's finite-sample covariance adjustment and a normal-reference confidence interval. Few clusters and serial dependence limit that approximation.

The before/after control comparison is descriptive. It cannot remove unobserved inventory, availability, merchandising, or intentional price-setting effects. [The model card](modelcard.md) and [elasticity discussion](elasticity.md) explain the claims this evidence can support.

## Latency and monitoring metrics

Keep three latency measurements distinct:

- The promotion measurement times a warm, isolated candidate prediction, including Python features and row construction. It excludes HTTP, logging, incumbent scoring, and container overhead.
- The in-process ASGI load test includes request routing, serialization, feature construction, incumbent scoring, and enabled shadow scoring. It uses no network transport.
- The container load test uses TCP HTTP against the built image in CI. Its host, concurrency, requested and actual duration, warmup, successful requests, errors, percentiles, and histogram travel with the artifact.

Raw successful-request latency samples rederive the percentiles and histogram. Throughput is successful requests divided by actual elapsed time. Errors are counted separately and fail the load-test command. A concurrency-limited closed-loop load generator is not a guarantee at an externally imposed arrival rate.

Monitoring uses PSI for each feature, a two-sample KS statistic for prediction distributions, and WAPE when realized gross units arrive. PSI alert boundaries are conventional diagnostics, not calibrated probabilities of model failure. Calendar and trend features can drift predictably. A four-week arithmetic mean of defined weekly WAPEs is compared with the initial validation reference; an undefined zero-demand week breaks that consecutive history.
