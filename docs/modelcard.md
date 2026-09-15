# Model card

## Intended use

`pricepoint` is an independent, reproducible demonstration of historical retail demand forecasting, uncertainty estimation, constrained pricing arithmetic, and model operations. It uses [UCI Online Retail II](https://doi.org/10.24432/C5CG6D), a public dataset unrelated to any employer. The intended reader is an engineer evaluating the evidence and operating design.

The service predicts gross weekly units for an eligible historical product at a proposed price and a supported historical decision date. It computes gross revenue as price times predicted units. The optimizer applies user-supplied cost, markdown, inventory, and fitted-support constraints. Outputs are scenarios for inspection, not validated instructions for setting current retail prices.

## Model identity and current serving behavior

The authoritative identities, hashes, support bounds, feature contract, and availability dates are in the [registry](../artifacts/registry), exposed through `pricepoint models` and `/v1/models`. The [promotion record](../artifacts/promotion.json) states which gates passed and which version remains incumbent.

The published service uses the B2 trailing-mean baseline for responses. C2, a LightGBM Tweedie demand model, is scored in shadow when its historical fitting and calibration are available at the request cutoff. A candidate's existence does not imply promotion. The baseline's demand curve is price-insensitive; the optimizer's behavior under it follows the supplied constraints and revenue or margin arithmetic.

## Training data and target

The source is historical transaction data from a UK online retailer. Both source years are ingested and the market is restricted to recorded United Kingdom transactions. The data pipeline handles malformed rows, explicit non-product codes, nonpositive prices, sequential price outliers, cancellation matches, and returns with stored quarantine evidence. [Data documentation](data.md) contains measured lineage and policy details.

The target is positive gross quantity before credit events. Signed quantities, returned quantities, and net revenue remain separate accounting fields. A same-day cancellation can therefore contribute to gross units and later reduce net units. Predictions do not estimate retained revenue after returns.

The source contains no inventory or product-availability feed. Zero-sale weeks can mean no demand, no stock, delisting, missing coverage, or a combination. The product-week panel records observed transaction absence as zero without claiming to distinguish those causes.

Product categories are coarse groups inferred from the first accepted description using a fixed keyword taxonomy. They are not retailer-supplied categories. Eligibility requires sufficient historical sales weeks and price variation using fit-period information only.

## Inputs and temporal scope

Inputs combine proposed and historical prices, lagged gross units, trailing demand moments, prior price changes, leave-one-out group demand, calendar variables, age, and zero-sale frequency. The ordered contract is versioned and checked at startup and promotion.

For a target week, the decision cutoff is one week earlier, and history is strictly earlier than that cutoff. Historical training uses the last known price, not the realized target-week price. A proposed serving price changes the corresponding price features, but the model was evaluated as a lagged-price forecaster. It has not been validated as a contemporaneous causal price-response model.

The frozen service rejects decision dates outside its artifact's evidence window. Its holiday approximation is scoped to the historical source, with England and Wales bank holidays used for the UK market. Neither the data nor that calendar should be treated as a current operational feed.

## Evaluation and uncertainty

[RESULTS](../RESULTS.md) is the single narrative source for measured performance. [Backtest artifacts](../artifacts/backtest.json) and [held-out predictions](../artifacts/predictions.parquet) support the complete per-fold comparison against the baseline family. [Metrics documentation](metrics.md) specifies temporal splits, WAPE, MASE, sample variation, calibration, and the quantile comparison.

Conformal bands use a separate earlier calibration period and are evaluated on held-out outcomes. Dependence across products and time limits exact exchangeability guarantees. Empirical historical coverage is evidence about this replay, not a guarantee about changed products or future traffic. The published conformal comparison describes C2; do not transfer its reported coverage to the separately calibrated B2 service without checking that model's own evidence.

The category coefficient analysis uses `log1p(gross units)`, product fixed effects, calendar controls, trend, and zero-sale frequency. Product-clustered standard errors and normal-reference intervals remain approximate, especially with few effective independent clusters. Reported coefficients are observational lagged-price associations.

## Limits on causal interpretation

Retail prices can change because demand, stock, product life cycle, or merchandising has changed. Those same variables can also affect units. Controls cannot eliminate unobserved confounding or selection into a price change. A coefficient with an economically plausible sign still does not establish causality; an implausible sign is a diagnostic, not proof of a particular mechanism.

The dataset has no treatment assignment, exposure logs, or reliable stock-out labels. The optimizer constrains extrapolation but does not repair those identification limits. A randomized price experiment with inventory monitoring, a predeclared estimand, and a power analysis would be needed before claiming causal revenue lift. See [the elasticity discussion](elasticity.md).

## Operations and monitoring

Models load once at startup. A registry checksum or schema mismatch stops serving. An independent Python feature store is checked against the Polars batch pipeline; deletion-based leakage checks and deliberate corruptions test the verification mechanism.

Shadow scoring records comparable candidate and incumbent predictions while returning the incumbent. Monitoring measures feature distribution changes, prediction distribution changes, and realized gross-demand error. Historical triggers respect data availability, idempotency, and cooldown. A simulated refit does not promote a model or publish a deployment.

Warm isolated candidate latency, full in-process ASGI latency, and container HTTP latency are separate measurements. Use their stored methods and raw samples when comparing them. The [runbook](runbook.md) covers startup failures, artifact review, refits, and pointer restoration.

## Uses outside scope

Do not use this historical artifact for current inventory decisions, causal elasticity claims, personalized pricing, estimates of profit without real costs, or net-return forecasting. There is no live operational validation, customer authentication service, durable production request history, or automated business approval system in this repository.
