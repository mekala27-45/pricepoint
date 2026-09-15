# Elasticity: what these estimates can support

## Outcome and price exposure

This service predicts gross weekly units. The regression uses log(units + one), and its price covariate is the last observed price strictly before the decision cutoff. That makes the estimated coefficient a lagged observational association. It is not the causal effect of assigning the proposed price for the target week.

The log transform retains genuine zero weeks. It also changes the coefficient's interpretation: at small volumes, the coefficient is not a constant percentage elasticity of units. We report the coefficient and its interval with that limitation.

## What was controlled

The category model uses deterministic description-based groups because the source supplies no merchant categories. The uncontrolled regression contains an intercept and log price. The adjusted regression includes product fixed effects through within-product demeaning, calendar seasonality, trend and a recent-zero-sales proxy. Standard errors are clustered by product when enough products are available.

Product fixed effects account for persistent differences between products. Calendar terms absorb regular seasonal variation. The zero-sales proxy can only partially represent availability because inventory and listing status are absent.

Controls do not remove unobserved promotions, availability, endogenous price-setting or wholesale order effects. Their inclusion can move a coefficient without identifying a causal effect.

## The observed finding

Read the generated [coefficient table](../RESULTS.md#price-associations-before-and-after-controls) for every inferred group before and after controls. The observed retail run produced no positive coefficients. We did not manufacture positive coefficients to match an anticipated story. Negative coefficients are also compatible with confounding.

The stronger operational finding is that the gradient-boosted candidate lost to a trailing-mean baseline on aggregate held-out error and failed the category gate. The system leaves it in shadow mode. More complex forecasting did not justify deployment in this run.

## Constructed-data check

The synthetic validation generates product intercepts, seasonal effects, endogenous between-product price differences and a known within-product price coefficient. The adjusted estimator's confidence intervals are checked against that parameter. This validates the implementation under the generator's assumptions, not the assumptions for the UCI data.

Run the script and see the full [stored evidence](../artifacts/synthetic_validation.json):

~~~sh
uv run python -m scripts.validate_synthetic
~~~

## An experiment that would identify a price effect

1. Define a product population with reliable inventory and price execution.
2. Form comparable strata using demand history collected before treatment.
3. Randomly assign product-level price schedules within strata. Keep assignments stable for the analysis window and record adherence.
4. Specify bounded price changes, gross units, net revenue and margin outcomes, stock availability, refunds, and guardrail outcomes before launch.
5. Analyze intent to treat with product-clustered uncertainty. Treat substitution between products as interference rather than independent observations.
6. Use a pilot to estimate serial correlation and cluster-level variance; recalculate power before choosing the final sample and runtime.

The [planning calculation](../artifacts/experiment.json) uses measured forecast residual variation with explicitly assumed elasticity, price contrast, power and participating-product count. Its independent-observation formula is an illustration. Product-week observations are usually correlated, and this can understate the sample requirement. The [results section](../RESULTS.md#what-a-price-experiment-would-require) reports the calculated inputs and output together.

## Why the optimizer is constrained

The optimizer searches feasible penny-denominated prices, respects cost and inventory, and stays inside the fitted product-price range. Touching a support boundary produces a warning. Staying in range limits extrapolation; it does not turn an observational curve into a causal revenue estimate.

The deployed baseline is price-insensitive. Its optimal revenue decision generally keeps the highest allowed price. That behavior is disclosed in the demo instead of quietly replacing the selected model with the more visually interesting candidate.

## Sources

- [UCI Online Retail II dataset](https://doi.org/10.24432/C5CG6D): source, variables and license.
- [statsmodels OLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html): regression implementation.
- [A Gentle Introduction to Conformal Prediction](https://arxiv.org/abs/2107.07511): coverage assumptions and interpretation.
