# Results

The trailing mean remains incumbent. The demand candidate failed the aggregate error and category non-regression gates. The service keeps the candidate in shadow mode.

## Backtest summary

<!-- summary:start -->
| Model | WAPE (mean +/- SD) | MASE (mean +/- SD) |
| --- | --- | --- |
| B0 | 0.7917 +/- 0.1488 | 1.0787 +/- 0.1105 |
| B1 | 1.2191 +/- 0.2702 | 1.6495 +/- 0.1213 |
| B2 | 0.7043 +/- 0.1061 | 0.9634 +/- 0.0864 |
| B3 | 1.2079 +/- 0.0880 | 4.0954 +/- 0.0919 |
| C1 | 0.8316 +/- 0.1013 | 1.1683 +/- 0.0954 |
| C2 | 0.7150 +/- 0.1307 | 1.0595 +/- 0.1094 |
<!-- summary:end -->

WAPE is a ratio; lower is better. MASE is relative to each product's training-only one-step naive error. Standard deviations are across expanding temporal folds.

## Temporal split ledger

Decisions precede target weeks. Base fitting and calibration finish before their respective decision cutoffs. The final partial source week is excluded.

<!-- splits:start -->
| Fold | Fit labels through | Calibration week | Decision cutoff / gap | Test week |
| --- | --- | --- | --- | --- |
| 1 | 2011-09-12 | 2011-09-26 | 2011-10-03 | 2011-10-10 |
| 2 | 2011-09-19 | 2011-10-03 | 2011-10-10 | 2011-10-17 |
| 3 | 2011-09-26 | 2011-10-10 | 2011-10-17 | 2011-10-24 |
| 4 | 2011-10-03 | 2011-10-17 | 2011-10-24 | 2011-10-31 |
| 5 | 2011-10-10 | 2011-10-24 | 2011-10-31 | 2011-11-07 |
| 6 | 2011-10-17 | 2011-10-31 | 2011-11-07 | 2011-11-14 |
| 7 | 2011-10-24 | 2011-11-07 | 2011-11-14 | 2011-11-21 |
| 8 | 2011-10-31 | 2011-11-14 | 2011-11-21 | 2011-11-28 |
<!-- splits:end -->

## Every model, every fold

<!-- folds:start -->
| Fold | Target week | Model | WAPE | MASE | Products | Undefined MASE rows |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2011-10-10 | B0 | 0.849 | 0.979 | 2498 | 0 |
| 1 | 2011-10-10 | B1 | 1.719 | 1.819 | 2498 | 0 |
| 1 | 2011-10-10 | B2 | 0.826 | 0.931 | 2498 | 0 |
| 1 | 2011-10-10 | B3 | 1.340 | 4.016 | 2498 | 0 |
| 1 | 2011-10-10 | C1 | 0.982 | 1.179 | 2498 | 0 |
| 1 | 2011-10-10 | C2 | 0.951 | 1.241 | 2498 | 0 |
| 2 | 2011-10-17 | B0 | 1.127 | 1.021 | 2510 | 0 |
| 2 | 2011-10-17 | B1 | 1.545 | 1.720 | 2510 | 0 |
| 2 | 2011-10-17 | B2 | 0.853 | 0.844 | 2510 | 0 |
| 2 | 2011-10-17 | B3 | 1.334 | 3.979 | 2510 | 0 |
| 2 | 2011-10-17 | C1 | 0.958 | 1.071 | 2510 | 0 |
| 2 | 2011-10-17 | C2 | 0.856 | 0.990 | 2510 | 0 |
| 3 | 2011-10-24 | B0 | 0.809 | 1.226 | 2519 | 0 |
| 3 | 2011-10-24 | B1 | 1.181 | 1.764 | 2519 | 0 |
| 3 | 2011-10-24 | B2 | 0.790 | 1.120 | 2519 | 0 |
| 3 | 2011-10-24 | B3 | 1.243 | 4.276 | 2519 | 0 |
| 3 | 2011-10-24 | C1 | 0.884 | 1.351 | 2519 | 0 |
| 3 | 2011-10-24 | C2 | 0.760 | 1.227 | 2519 | 0 |
| 4 | 2011-10-31 | B0 | 0.725 | 0.998 | 2550 | 0 |
| 4 | 2011-10-31 | B1 | 0.977 | 1.527 | 2550 | 0 |
| 4 | 2011-10-31 | B2 | 0.713 | 0.962 | 2550 | 0 |
| 4 | 2011-10-31 | B3 | 1.181 | 4.157 | 2550 | 0 |
| 4 | 2011-10-31 | C1 | 0.847 | 1.224 | 2550 | 0 |
| 4 | 2011-10-31 | C2 | 0.699 | 1.041 | 2550 | 0 |
| 5 | 2011-11-07 | B0 | 0.744 | 1.271 | 2562 | 0 |
| 5 | 2011-11-07 | B1 | 1.167 | 1.531 | 2562 | 0 |
| 5 | 2011-11-07 | B2 | 0.634 | 0.998 | 2562 | 0 |
| 5 | 2011-11-07 | B3 | 1.121 | 4.109 | 2562 | 0 |
| 5 | 2011-11-07 | C1 | 0.731 | 1.138 | 2562 | 0 |
| 5 | 2011-11-07 | C2 | 0.618 | 0.999 | 2562 | 0 |
| 6 | 2011-11-14 | B0 | 0.736 | 1.093 | 2578 | 0 |
| 6 | 2011-11-14 | B1 | 1.028 | 1.696 | 2578 | 0 |
| 6 | 2011-11-14 | B2 | 0.618 | 1.027 | 2578 | 0 |
| 6 | 2011-11-14 | B3 | 1.130 | 4.105 | 2578 | 0 |
| 6 | 2011-11-14 | C1 | 0.746 | 1.210 | 2578 | 0 |
| 6 | 2011-11-14 | C2 | 0.597 | 1.007 | 2578 | 0 |
| 7 | 2011-11-21 | B0 | 0.680 | 1.012 | 2595 | 0 |
| 7 | 2011-11-21 | B1 | 1.138 | 1.647 | 2595 | 0 |
| 7 | 2011-11-21 | B2 | 0.615 | 0.943 | 2595 | 0 |
| 7 | 2011-11-21 | B3 | 1.156 | 4.076 | 2595 | 0 |
| 7 | 2011-11-21 | C1 | 0.757 | 1.119 | 2595 | 0 |
| 7 | 2011-11-21 | C2 | 0.616 | 0.984 | 2595 | 0 |
| 8 | 2011-11-28 | B0 | 0.663 | 1.030 | 2608 | 0 |
| 8 | 2011-11-28 | B1 | 0.998 | 1.492 | 2608 | 0 |
| 8 | 2011-11-28 | B2 | 0.586 | 0.882 | 2608 | 0 |
| 8 | 2011-11-28 | B3 | 1.158 | 4.045 | 2608 | 0 |
| 8 | 2011-11-28 | C1 | 0.747 | 1.055 | 2608 | 0 |
| 8 | 2011-11-28 | C2 | 0.622 | 0.986 | 2608 | 0 |
<!-- folds:end -->

## Price associations, before and after controls

<!-- elasticity:start -->
0 of 9 inferred groups have a positive unadjusted price coefficient; 0 have a positive adjusted coefficient.

| Inferred group | Before controls | Before CI | After controls | After CI |
| --- | --- | --- | --- | --- |
| other | -0.357 | [-0.419, -0.295] | -0.403 | [-0.450, -0.356] |
| stationery | -0.644 | [-0.841, -0.448] | -0.326 | [-0.463, -0.190] |
| garden | -0.246 | [-0.404, -0.088] | -0.456 | [-0.592, -0.319] |
| kitchen | -0.436 | [-0.582, -0.289] | -0.340 | [-0.428, -0.253] |
| bags | -0.703 | [-0.944, -0.463] | -0.190 | [-0.301, -0.079] |
| lighting | -0.433 | [-0.630, -0.237] | -0.354 | [-0.465, -0.242] |
| seasonal | -0.470 | [-0.595, -0.345] | -0.688 | [-0.891, -0.484] |
| decor | -0.439 | [-0.588, -0.289] | -0.399 | [-0.496, -0.303] |
| toys | -0.279 | [-0.475, -0.084] | -0.319 | [-0.500, -0.139] |
<!-- elasticity:end -->

These are confidence intervals for log-price coefficients in log-transformed gross-demand regressions. The dependent variable is log(units + one), so the coefficient is not a constant percentage elasticity at low volumes. The price feature is the last price observable at the decision cutoff. These are lagged observational associations, not identified causal effects of a future price intervention. Description groups are inferred, not merchant-supplied categories.

## Prediction intervals

<!-- coverage:start -->
Nominal coverage: 90.00%. Pooled held-out conformal coverage: 90.40%. Quantile comparison coverage: 95.54% across 20,420 product-week observations.

| Fold | Conformal coverage | Quantile coverage | Conformal width (units) | Quantile width (units) |
| --- | --- | --- | --- | --- |
| 1 | 87.63% | 96.56% | 76.02 | 96.09 |
| 2 | 91.43% | 96.06% | 87.26 | 88.73 |
| 3 | 92.85% | 95.79% | 82.01 | 82.15 |
| 4 | 90.55% | 93.53% | 71.63 | 79.16 |
| 5 | 89.03% | 94.22% | 64.21 | 87.09 |
| 6 | 89.91% | 95.15% | 70.21 | 89.09 |
| 7 | 90.83% | 96.22% | 73.81 | 96.12 |
| 8 | 90.95% | 96.78% | 73.32 | 107.64 |
<!-- coverage:end -->

Calibration uses historical held-out observations. Pooled coverage does not guarantee per-product or future coverage under temporal dependence. Quantile intervals are more conservative in this evaluation; their extra width is shown above.

## Promotion decision

<!-- promotion:start -->
Incumbent: B2-20111128-33c7c8ff9f6d. Candidate promoted: false.

| Gate | Result | Rule |
| --- | --- | --- |
| wape_improvement | Refused | At least 2% relative WAPE improvement over a positive incumbent WAPE is required |
| category_non_regression | Refused | Every incumbent category must be present and degrade by at most 5% relative |
| latency | Pass | Measured p99 must be below 15ms with at least 100 single-prediction observations |
| coverage | Pass | Held-out test coverage must be within 2 percentage points of nominal |
| schema | Pass | Ordered feature names, Float64 types, and contract version must match exactly |
| training_serving_skew | Pass | Independent-path skew on at least 500 pairs must be within the stated tight tolerance |
<!-- promotion:end -->

## Training and serving agreement

<!-- skew:start -->
1. 500 sampled feature vectors, two independent computation paths, maximum absolute difference of 1.137e-13.

2. 200 future-deletion checks passed with maximum difference 0.000e+00. Stored pairs and the panel hash make the sample repeatable.
<!-- skew:end -->

The tests deliberately round a serving feature differently and verify the gate refuses it. Both paths retain the same known historical rows, including the observed first partial week; incomplete weeks are excluded as evaluation labels.

## HTTP latency and histogram

<!-- latency:start -->
| Transport | p50 (ms) | p95 (ms) | p99 (ms) | Successful requests/s | Errors |
| --- | --- | --- | --- | --- | --- |
| in-process ASGI, no network or container | 7.480 | 17.189 | 24.778 | 452.53 | 0 |

Measured 2026-09-15T19:49:01.439725+00:00 on Windows-11-10.0.26200-SP0, Python 3.12.14. Concurrency 4, duration 30s (actual 30.005s), warmup 100 requests. Closed-loop concurrent clients; latency includes client serialization, ASGI routing, feature construction, incumbent and enabled shadow scoring. Warmup excluded. Throughput counts successful responses only.

| Latency bin (ms) | Successful requests |
| --- | --- |
| 0 to 1 | 0 |
| 1 to 2 | 1 |
| 2 to 5 | 939 |
| 5 to 10 | 9491 |
| 10 to 15 | 2107 |
| 15 to 25 | 907 |
| 25 to 50 | 111 |
| 50 to 100 | 14 |
| 100 to infinity | 8 |
<!-- latency:end -->

This is a development-machine measurement, including shadow scoring. It is not an isolated production capacity estimate. The separate single-candidate gate measures a different path:

<!-- gate_latency:start -->
Candidate inference p99: 0.853 ms from 1000 measured requests. Warm single-candidate prediction in process, Python feature store plus Polars row construction and calibrated LightGBM scoring; excludes HTTP, logging and container overhead.
<!-- gate_latency:end -->

## Container latency

<!-- container:start -->
| p50 (ms) | p95 (ms) | p99 (ms) | Successful requests/s | Errors |
| --- | --- | --- | --- | --- |
| 11.526 | 15.006 | 16.427 | 345.12 | 0 |

Container TCP measurement: 30s at concurrency 4, 100 warmup requests, Linux-6.17.0-1022-azure-x86_64-with-glibc2.39. CI stores the resolved base and built image identifiers.

Closed-loop concurrent clients; latency includes client serialization, ASGI routing, feature construction, incumbent and enabled shadow scoring. Warmup excluded. Throughput counts successful responses only.

| Latency bin (ms) | Successful requests |
| --- | --- |
| 0 to 1 | 0 |
| 1 to 2 | 0 |
| 2 to 5 | 20 |
| 5 to 10 | 2236 |
| 10 to 15 | 7577 |
| 15 to 25 | 515 |
| 25 to 50 | 0 |
| 50 to 100 | 8 |
| 100 to infinity | 0 |
<!-- container:end -->

The [benchmark provenance](artifacts/container-provenance.json) records the successful CI run, tested commit, artifact checksum, base image digests and application image identity. This is a single-run host measurement with closed-loop clients; it does not establish a production latency SLO.

## Shadow disagreement

<!-- shadow:start -->
| Scored pairs | Mean disagreement (units) | p50 | p95 | p99 |
| --- | --- | --- | --- | --- |
| 4403 | 249.149 | 62.086 | 1243.755 | 2769.877 |

Incumbent and candidate scored the same precomputed product-price grid; absolute disagreement in gross units, descriptive grid distribution rather than traffic-weighted production statistics.
<!-- shadow:end -->

Only the incumbent is returned by the service and bundled demo. A price-insensitive baseline produces a flat units curve; the revenue curve and constrained optimizer still respond to price and inventory. The flat curve is a property of the winning model.

## Historical monitoring and retraining

<!-- monitoring:start -->
77 evaluated weeks, 39 triggers, 38 completed refits after 26 initial weeks.

| Sales week | Observed at | WAPE | Max feature PSI | Trigger | Action |
| --- | --- | --- | --- | --- | --- |
| 2010-06-14 | 2010-06-21 | 0.953 | 18.522 | Yes | continued incumbent |
| 2010-06-21 | 2010-06-28 | 1.083 | 18.527 | No | continued incumbent |
| 2010-06-28 | 2010-07-05 | 0.798 | 18.666 | Yes | refit completed using labels before decision cutoff |
| 2010-07-05 | 2010-07-12 | 0.842 | 18.672 | No | continued incumbent |
| 2010-07-12 | 2010-07-19 | 0.827 | 18.745 | Yes | refit completed using labels before decision cutoff |
| 2010-07-19 | 2010-07-26 | 0.769 | 18.747 | No | continued incumbent |
| 2010-07-26 | 2010-08-02 | 0.787 | 18.833 | Yes | refit completed using labels before decision cutoff |
| 2010-08-02 | 2010-08-09 | 0.876 | 18.839 | No | continued incumbent |
| 2010-08-09 | 2010-08-16 | 0.804 | 18.914 | Yes | refit completed using labels before decision cutoff |
| 2010-08-16 | 2010-08-23 | 0.789 | 18.917 | No | continued incumbent |
| 2010-08-23 | 2010-08-30 | 0.838 | 18.984 | Yes | refit completed using labels before decision cutoff |
| 2010-08-30 | 2010-09-06 | 0.813 | 18.989 | No | continued incumbent |
| 2010-09-06 | 2010-09-13 | 0.908 | 19.051 | Yes | refit completed using labels before decision cutoff |
| 2010-09-13 | 2010-09-20 | 0.812 | 19.052 | No | continued incumbent |
| 2010-09-20 | 2010-09-27 | 0.728 | 19.116 | Yes | refit completed using labels before decision cutoff |
| 2010-09-27 | 2010-10-04 | 0.764 | 19.127 | No | continued incumbent |
| 2010-10-04 | 2010-10-11 | 0.676 | 19.192 | Yes | refit completed using labels before decision cutoff |
| 2010-10-11 | 2010-10-18 | 0.634 | 9.987 | No | continued incumbent |
| 2010-10-18 | 2010-10-25 | 0.712 | 10.571 | Yes | refit completed using labels before decision cutoff |
| 2010-10-25 | 2010-11-01 | 0.887 | 10.581 | No | continued incumbent |
| 2010-11-01 | 2010-11-08 | 0.736 | 10.496 | Yes | refit completed using labels before decision cutoff |
| 2010-11-08 | 2010-11-15 | 0.647 | 10.498 | No | continued incumbent |
| 2010-11-15 | 2010-11-22 | 0.588 | 10.154 | Yes | refit completed using labels before decision cutoff |
| 2010-11-22 | 2010-11-29 | 0.624 | 10.155 | No | continued incumbent |
| 2010-11-29 | 2010-12-06 | 0.672 | 10.210 | Yes | refit completed using labels before decision cutoff |
| 2010-12-06 | 2010-12-13 | 0.664 | 10.215 | No | continued incumbent |
| 2010-12-13 | 2010-12-20 | 1.503 | 10.264 | Yes | refit completed using labels before decision cutoff |
| 2010-12-20 | 2010-12-27 | 6.151 | 10.267 | No | continued incumbent |
| 2010-12-27 | 2011-01-03 | Undefined | 10.817 | Yes | refit completed using labels before decision cutoff |
| 2011-01-03 | 2011-01-10 | 0.928 | 10.314 | No | continued incumbent |
| 2011-01-10 | 2011-01-17 | 0.996 | 10.363 | Yes | refit completed using labels before decision cutoff |
| 2011-01-17 | 2011-01-24 | 0.995 | 10.363 | No | continued incumbent |
| 2011-01-24 | 2011-01-31 | 0.879 | 10.412 | Yes | refit completed using labels before decision cutoff |
| 2011-01-31 | 2011-02-07 | 0.943 | 10.412 | No | continued incumbent |
| 2011-02-07 | 2011-02-14 | 1.182 | 10.459 | Yes | refit completed using labels before decision cutoff |
| 2011-02-14 | 2011-02-21 | 0.890 | 10.460 | No | continued incumbent |
| 2011-02-21 | 2011-02-28 | 0.752 | 10.506 | Yes | refit completed using labels before decision cutoff |
| 2011-02-28 | 2011-03-07 | 0.790 | 10.510 | No | continued incumbent |
| 2011-03-07 | 2011-03-14 | 0.801 | 10.551 | Yes | refit completed using labels before decision cutoff |
| 2011-03-14 | 2011-03-21 | 0.773 | 10.556 | No | continued incumbent |
| 2011-03-21 | 2011-03-28 | 0.773 | 10.594 | Yes | refit completed using labels before decision cutoff |
| 2011-03-28 | 2011-04-04 | 0.683 | 10.819 | No | continued incumbent |
| 2011-04-04 | 2011-04-11 | 0.848 | 10.630 | Yes | refit completed using labels before decision cutoff |
| 2011-04-11 | 2011-04-18 | 0.784 | 10.631 | No | continued incumbent |
| 2011-04-18 | 2011-04-25 | 0.922 | 10.666 | Yes | refit completed using labels before decision cutoff |
| 2011-04-25 | 2011-05-02 | 0.980 | 10.668 | No | continued incumbent |
| 2011-05-02 | 2011-05-09 | 0.757 | 10.712 | Yes | refit completed using labels before decision cutoff |
| 2011-05-09 | 2011-05-16 | 0.712 | 10.715 | No | continued incumbent |
| 2011-05-16 | 2011-05-23 | 0.712 | 10.744 | Yes | refit completed using labels before decision cutoff |
| 2011-05-23 | 2011-05-30 | 0.839 | 10.755 | No | continued incumbent |
| 2011-05-30 | 2011-06-06 | 0.949 | 10.784 | Yes | refit completed using labels before decision cutoff |
| 2011-06-06 | 2011-06-13 | 0.787 | 10.785 | No | continued incumbent |
| 2011-06-13 | 2011-06-20 | 0.778 | 10.811 | Yes | refit completed using labels before decision cutoff |
| 2011-06-20 | 2011-06-27 | 0.823 | 10.817 | No | continued incumbent |
| 2011-06-27 | 2011-07-04 | 0.912 | 10.855 | Yes | refit completed using labels before decision cutoff |
| 2011-07-04 | 2011-07-11 | 0.730 | 10.860 | No | continued incumbent |
| 2011-07-11 | 2011-07-18 | 0.722 | 10.875 | Yes | refit completed using labels before decision cutoff |
| 2011-07-18 | 2011-07-25 | 0.687 | 10.876 | No | continued incumbent |
| 2011-07-25 | 2011-08-01 | 0.739 | 10.905 | Yes | refit completed using labels before decision cutoff |
| 2011-08-01 | 2011-08-08 | 0.773 | 10.908 | No | continued incumbent |
| 2011-08-08 | 2011-08-15 | 0.900 | 10.936 | Yes | refit completed using labels before decision cutoff |
| 2011-08-15 | 2011-08-22 | 0.864 | 10.940 | No | continued incumbent |
| 2011-08-22 | 2011-08-29 | 0.746 | 10.969 | Yes | refit completed using labels before decision cutoff |
| 2011-08-29 | 2011-09-05 | 0.756 | 10.969 | No | continued incumbent |
| 2011-09-05 | 2011-09-12 | 0.719 | 10.995 | Yes | refit completed using labels before decision cutoff |
| 2011-09-12 | 2011-09-19 | 0.726 | 10.999 | No | continued incumbent |
| 2011-09-19 | 2011-09-26 | 0.756 | 11.034 | Yes | refit completed using labels before decision cutoff |
| 2011-09-26 | 2011-10-03 | 0.860 | 11.036 | No | continued incumbent |
| 2011-10-03 | 2011-10-10 | 0.803 | 11.057 | Yes | refit completed using labels before decision cutoff |
| 2011-10-10 | 2011-10-17 | 0.898 | 11.062 | No | continued incumbent |
| 2011-10-17 | 2011-10-24 | 0.790 | 11.086 | Yes | refit completed using labels before decision cutoff |
| 2011-10-24 | 2011-10-31 | 0.725 | 11.091 | No | continued incumbent |
| 2011-10-31 | 2011-11-07 | 0.662 | 11.114 | Yes | refit completed using labels before decision cutoff |
| 2011-11-07 | 2011-11-14 | 0.608 | 11.117 | No | continued incumbent |
| 2011-11-14 | 2011-11-21 | 0.590 | 11.135 | Yes | refit completed using labels before decision cutoff |
| 2011-11-21 | 2011-11-28 | 0.605 | 11.137 | No | continued incumbent |
| 2011-11-28 | 2011-12-05 | 0.615 | 11.158 | Yes | refit completed using labels before decision cutoff |
<!-- monitoring:end -->

The simulation retrains a candidate family after information becomes available; it does not bypass promotion gates or change the live incumbent. Calendar, age and trend features predictably leave the training distribution, causing repeated alerts. The unconditional PSI rule is an exposed policy limitation, not evidence that every alert marks harmful drift. Undefined weekly WAPE is retained as a gap and breaks the consecutive error-history window.

## What a price experiment would require

<!-- experiment:start -->
Measured log-demand forecast residual SD: 1.033. Under a planning assumption of elasticity -1.50, a 10% price difference, 80% power and two-sided alpha 0.05, the independent-unit approximation requires 820 product-week observations per arm. With 200 participating products split equally between arms, this implies 9 weeks. These are planning assumptions, not a validated experiment sample size.
<!-- experiment:end -->

Randomize comparable products within predeclared demand strata, hold assignments stable, cap discounts, track net revenue and margin, and analyze intent to treat. Estimate within-product serial dependence and cross-product interference before final sizing. Use cluster-aware power calculations and a predeclared stopping rule. Wholesale orders, stock availability and refund delay need separate guardrails.

## Known-parameter validation

<!-- synthetic:start -->
Synthetic validation evidence:

    {
      "measured_at": "2026-09-15T19:28:54.939640+00:00",
      "seed": 42,
      "rows": 13312,
      "products": 128,
      "weeks": 104,
      "true_coefficient": -1.5,
      "confidence_level": 0.95,
      "categories_recovered": 4,
      "categories": 4,
      "estimates": [
        {
          "category": "synthetic_0",
          "status": "estimated",
          "rows": 3328,
          "products": 32,
          "before": 0.6594923374946422,
          "before_se": 0.09433904833181522,
          "before_low": 0.4745912004285009,
          "before_high": 0.8443934745607835,
          "after": -1.4671783051606715,
          "after_se": 0.02141363270850733,
          "after_low": -1.5091482540475147,
          "after_high": -1.4252083562738282,
          "covariance": "product_cluster",
          "controls": [
            "product_fixed_effects",
            "week_sin",
            "week_cos",
            "trend",
            "zero_fraction"
          ],
          "outcome": "log1p(units)",
          "interpretation": "Lagged historical-price association with log1p gross units; not contemporaneous or causal elasticity",
          "true_coefficient": -1.5,
          "contains_true_coefficient": true
        },
        {
          "category": "synthetic_1",
          "status": "estimated",
          "rows": 3328,
          "products": 32,
          "before": 0.6838963390834589,
          "before_se": 0.09557943488596372,
          "before_low": 0.49656408904427884,
          "before_high": 0.871228589122639,
          "after": -1.4934101235384603,
          "after_se": 0.015896606635606613,
          "after_low": -1.5245669000206497,
          "after_high": -1.4622533470562709,
          "covariance": "product_cluster",
          "controls": [
            "product_fixed_effects",
            "week_sin",
            "week_cos",
            "trend",
            "zero_fraction"
          ],
          "outcome": "log1p(units)",
          "interpretation": "Lagged historical-price association with log1p gross units; not contemporaneous or causal elasticity",
          "true_coefficient": -1.5,
          "contains_true_coefficient": true
        },
        {
          "category": "synthetic_2",
          "status": "estimated",
          "rows": 3328,
          "products": 32,
          "before": 0.6642015845323339,
          "before_se": 0.09683164959515789,
          "before_low": 0.4744150387622219,
          "before_high": 0.8539881303024459,
          "after": -1.4943430490347662,
          "after_se": 0.019442731868587554,
          "after_low": -1.532450103258267,
          "after_high": -1.4562359948112655,
          "covariance": "product_cluster",
          "controls": [
            "product_fixed_effects",
            "week_sin",
            "week_cos",
            "trend",
            "zero_fraction"
          ],
          "outcome": "log1p(units)",
          "interpretation": "Lagged historical-price association with log1p gross units; not contemporaneous or causal elasticity",
          "true_coefficient": -1.5,
          "contains_true_coefficient": true
        },
        {
          "category": "synthetic_3",
          "status": "estimated",
          "rows": 3328,
          "products": 32,
          "before": 0.6739691302512414,
          "before_se": 0.1008108977973,
          "before_low": 0.4763834013193851,
          "before_high": 0.8715548591830977,
          "after": -1.5163397436339054,
          "after_se": 0.020428180330161926,
          "after_low": -1.5563782413507123,
          "after_high": -1.4763012459170985,
          "covariance": "product_cluster",
          "controls": [
            "product_fixed_effects",
            "week_sin",
            "week_cos",
            "trend",
            "zero_fraction"
          ],
          "outcome": "log1p(units)",
          "interpretation": "Lagged historical-price association with log1p gross units; not contemporaneous or causal elasticity",
          "true_coefficient": -1.5,
          "contains_true_coefficient": true
        }
      ],
      "methodology": "Known log1p-demand process with product effects, seasonality, trend, a simulated availability covariate in the zero_fraction slot, and independent Gaussian price and outcome perturbations. All rows fit the recovery experiment; no data split or predictive-performance claim is made. The remaining features are adapter inputs unused by C1. Product-cluster covariance supplies the confidence intervals.",
      "limitation": "Recovery under known exogenous within-product price variation checks estimator arithmetic. Real retail prices are observational and need not satisfy that assumption."
    }
<!-- synthetic:end -->

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
