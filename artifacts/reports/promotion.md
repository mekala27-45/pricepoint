Incumbent: B2-20111128-33c7c8ff9f6d. Candidate promoted: false.

| Gate | Result | Rule |
| --- | --- | --- |
| wape_improvement | Refused | At least 2% relative WAPE improvement over a positive incumbent WAPE is required |
| category_non_regression | Refused | Every incumbent category must be present and degrade by at most 5% relative |
| latency | Pass | Measured p99 must be below 15ms with at least 100 single-prediction observations |
| coverage | Pass | Held-out test coverage must be within 2 percentage points of nominal |
| schema | Pass | Ordered feature names, Float64 types, and contract version must match exactly |
| training_serving_skew | Pass | Independent-path skew on at least 500 pairs must be within the stated tight tolerance |
