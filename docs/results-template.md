# Results

The trailing mean remains incumbent. The demand candidate failed the aggregate error and category non-regression gates. The service keeps the candidate in shadow mode.

## Backtest summary

{{summary}}

WAPE is a ratio; lower is better. MASE is relative to each product's training-only one-step naive error. Standard deviations are across expanding temporal folds.

## Temporal split ledger

Decisions precede target weeks. Base fitting and calibration finish before their respective decision cutoffs. The final partial source week is excluded.

{{splits}}

## Every model, every fold

{{folds}}

## Price associations, before and after controls

{{elasticity}}

These are confidence intervals for log-price coefficients in log-transformed gross-demand regressions. The dependent variable is log(units + one), so the coefficient is not a constant percentage elasticity at low volumes. The price feature is the last price observable at the decision cutoff. These are lagged observational associations, not identified causal effects of a future price intervention. Description groups are inferred, not merchant-supplied categories.

## Prediction intervals

{{coverage}}

Calibration uses historical held-out observations. Pooled coverage does not guarantee per-product or future coverage under temporal dependence. Quantile intervals are more conservative in this evaluation; their extra width is shown above.

## Promotion decision

{{promotion}}

## Training and serving agreement

{{skew}}

The tests deliberately round a serving feature differently and verify the gate refuses it. Both paths retain the same known historical rows, including the observed first partial week; incomplete weeks are excluded as evaluation labels.

## HTTP latency and histogram

{{latency}}

This is a development-machine measurement, including shadow scoring. It is not an isolated production capacity estimate. The separate single-candidate gate measures a different path:

{{gate_latency}}

## Container latency

{{container}}

## Shadow disagreement

{{shadow}}

Only the incumbent is returned by the service and bundled demo. A price-insensitive baseline produces a flat units curve; the revenue curve and constrained optimizer still respond to price and inventory. The flat curve is a property of the winning model.

## Historical monitoring and retraining

{{monitoring}}

The simulation retrains a candidate family after information becomes available; it does not bypass promotion gates or change the live incumbent. Calendar, age and trend features predictably leave the training distribution, causing repeated alerts. The unconditional PSI rule is an exposed policy limitation, not evidence that every alert marks harmful drift. Undefined weekly WAPE is retained as a gap and breaks the consecutive error-history window.

## What a price experiment would require

{{experiment}}

Randomize comparable products within predeclared demand strata, hold assignments stable, cap discounts, track net revenue and margin, and analyze intent to treat. Estimate within-product serial dependence and cross-product interference before final sizing. Use cluster-aware power calculations and a predeclared stopping rule. Wholesale orders, stock availability and refund delay need separate guardrails.

## Known-parameter validation

{{synthetic}}

This checks estimator implementation on constructed data, not identification on retail data.

## Limitations and what I would change

- Transaction data do not reveal inventory or listing status. Filled panel gaps mean no observed transactions; they cannot prove a product was available for sale. Stock-out proxies are imperfect.
- Gross demand excludes refunds from its target. The cleaning ledger retains credits and net amounts separately. Forecast revenue is gross revenue, not realized net receipts.
- A credit cannot prove the customer's reason. Same-day cancellations and later returns follow an operational convention, not ground-truth labels.
- Inferred groups, lagged prices, log transforms and endogenous pricing constrain interpretation. A positive association alone does not diagnose the exact source of confounding.
- The incumbent was selected by aggregate backtest performance. A prospective holdout would reduce selection bias. Most test weeks occur in the pre-holiday period.
- Conformal exchangeability is approximate, the price grid is descriptive, and no randomized price experiment was run. Predictive error does not validate counterfactual revenue uplift.
- Registry files and model pickles are trusted build artifacts. A multi-writer registry would need authenticated provenance, locking and operational isolation.
- Next I would obtain availability data, design price experiments, condition seasonal alerts on the calendar, and assess group-specific interval coverage on a fresh temporal holdout before adding model complexity.
