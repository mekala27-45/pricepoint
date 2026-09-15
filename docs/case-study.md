# Pricepoint: the model that did not get promoted

## Problem

A pricing model can look convincing while using future data, ignoring returns, evaluating only products with sales, or assuming historical price correlations are causal. I built a small service that makes those failure modes inspectable.

## Interesting decision

The initial specification anticipated positive retail price coefficients. The actual lagged-price regressions did not produce that finding. I kept the observed result and documented the more basic identification problem: prices were not randomized, availability is unknown, and the feature represents a historical price rather than an assigned target-week treatment.

The more complex demand candidate also failed to beat a trailing-mean baseline. I kept the baseline in the API and demo. A flat demand curve is less dramatic visually, but accurately reflects what the selected model knows about price.

## Implementation

The pipeline quarantines malformed and unmatched rows, retains credits at their observed timestamps, creates weekly zero observations and builds temporal features. An independent Python serving implementation is compared with the Polars training pipeline. Every promotion condition has a deliberate failure test.

The registry contains immutable, checksummed models and appended gate assessments. The service returns incumbent predictions and scores eligible candidates in shadow mode. Historical monitoring records both the sales week and the date its outcome becomes observable, so it cannot retrain on a trigger before that trigger could exist.

## Evidence

The [results document](../RESULTS.md) contains all model folds, before-and-after coefficient intervals, interval coverage, actual latency histograms, feature agreement and the full simulated trigger timeline. Its tables are generated from artifacts and re-derived by CI.

A constructed-data experiment separately checks whether the regression can recover a known parameter under its own assumptions.

## Limits

This is not proof of causal price optimization. Transaction records do not reveal listings, inventory or randomized treatments. Gross demand and refunded revenue have different meanings. Calendar-driven distribution drift also causes repeated alerts even when those calendar changes are expected.

## What I would change next

Obtain availability data, run a bounded randomized price experiment, condition monitoring on expected seasonality, and validate the next candidate on a fresh prospective holdout. Additional model complexity comes after those changes.

## Links

[Demo](https://mekala27-45.github.io/pricepoint/) | [Repository](https://github.com/mekala27-45/pricepoint) | [Results](../RESULTS.md)
