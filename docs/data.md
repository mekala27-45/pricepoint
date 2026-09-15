# Data contract and accounting decisions

This independent project uses [UCI Online Retail II](https://doi.org/10.24432/C5CG6D), public transaction data from a UK online retailer. Both workbook sheets are ingested. No employer data or systems are used. The source covers 2009-12-01 through 2011-12-09 and does not contain product categories, inventory, availability, advertising, experimental assignments, or a canonical return-to-sale link.

## Reproducible source

`config/data.json` records the download URL and separate SHA-256 pins for the ZIP and extracted workbook. Downloading uses a temporary file and atomic rename only after its hash passes. An existing file with different bytes fails verification. Raw workbooks and transaction-level customer identifiers stay in ignored local data directories.

The normalized bronze schema is `invoice`, `product_id`, `description`, `quantity`, `price`, `timestamp`, `customer_id`, and `country`, with `source_row` preserving workbook-concatenation order. Identifiers remain strings. Invalid identifiers, timestamps, nonnumeric quantities, and nonfinite prices are quarantined with a reason. Missing customer IDs are allowed for positive sales because anonymous purchases remain demand observations. They cannot be used for credit matching.

## Ordered cleaning rules

Each row first passes the following rules, in this order. Counts represent the first applicable rejection reason. Every rejected row remains in a quarantine Parquet file.

1. Keep United Kingdom transactions. This makes the market, currency assumption, and calendar coherent. Country is the dataset's recorded country, not independently verified shipping location.
2. Exclude the explicit non-product code list in `config/data.json`. It covers postage, carriage, manual entries including lowercase `m`, fees, discounts, tests, adjustments, gift vouchers, and nominal-price auxiliary codes. Product selection is never an inline stock-code regex. Alphanumeric product IDs are otherwise retained.
3. Reject prices at or below zero and nonfinite values. These cannot enter a log-price model. Reject zero quantities and positive quantities on credit-prefixed invoices.
4. Apply a per-product sequential price rule to positive sales. After at least twenty accepted prior prices, reject a price outside one fifth to five times the median of the most recent one hundred accepted transaction prices. A rejected price never updates this history. This broad ratio rule avoids assuming a Gaussian price distribution. It can still reject a genuine large repricing, and its transaction-weighted history adapts slowly when a new price regime is very different.
5. Match negative quantities against already observed, still-uncredited positive quantities with exactly the same customer ID, product, unit price, and country. Consume the most recent available purchase first. Missing-customer credits and unmatched remainders go to quarantine. Matching is an accounting heuristic, not ground-truth attribution.

### Cancellations and returns

A negative `C`-prefixed invoice matched entirely to same-calendar-day purchases is classified as a cancellation. Later credits, and negative transactions without that prefix, are classified as returns when matched. The source provides credit notes but no business-process return label, so these names describe an explicit operational rule. A credit spanning same-day and older purchases is classified as a return.

A matched credit is a negative event at its actual timestamp. The original sale remains unchanged in all earlier snapshots. A partial match creates an accepted negative event and a quarantined remainder sharing `source_row`; accounting counts therefore include split rows. A purchase cannot be credited twice beyond its original quantity.

## Measured lineage

The table is checked against `artifacts/data_report.json` by `test_data_document_counts_match_stored_lineage`. Rule tests separately exercise invalid schemas, chronology, customer isolation, partial matching, price rejection, and explicit code exclusion.

| Artifact field | Measured count |
|:--|--:|
| ingest.raw_rows | 1,067,371 |
| ingest.schema_valid_rows | 1,067,371 |
| ingest.schema_quarantine_rows | 0 |
| ingest.missing_customer_rows | 243,007 |
| clean.outside_country_rows | 86,041 |
| clean.non_product_rows | 3,624 |
| clean.non_positive_price_rows | 6,129 |
| clean.zero_quantity_rows | 0 |
| clean.positive_credit_invoice_rows | 0 |
| clean.price_outlier_rows | 3,258 |
| clean.matched_credit_rows | 13,137 |
| clean.same_day_cancellation_rows | 1,235 |
| clean.return_rows | 11,902 |
| clean.unmatched_credit_rows | 2,608 |
| clean.partial_credit_rows | 104 |
| clean.sale_rows | 952,678 |
| clean.clean_rows | 965,815 |
| clean.quarantine_rows | 101,660 |
| panel_rows | 433,107 |
| panel_products | 4,883 |
| panel_weeks | 106 |
| gold_rows | 418,462 |
| universe.considered_products | 4,882 |
| universe.included_products | 2,834 |
| universe.too_few_sales_weeks | 1,732 |
| universe.too_few_prices | 316 |

The clean and quarantine counts sum to source rows plus the partial-credit split count. Country exclusions occur before other cleaning rules. Missing-customer counts describe bronze, so they include rows that later fail cleaning.

## Product-week panel

Weeks start on Monday. Every product has exactly one row for every week from its first accepted transaction through the common source boundary. Missing observed transactions produce zero units. This expresses recorded sales, not proof that the product was stocked or offered for sale. A discontinued item and an available item with no demand both appear as zeros because the source cannot distinguish them.

- `units`: signed quantities, preserving the exact sum of accepted transactions.
- `gross_units`: positive quantities before any cancellation or return credits. This is the nonnegative modeling target and the source for demand-history features.
- `returned_units`: magnitude of negative accepted quantities, including same-day cancellations.
- `net_revenue`: signed quantity times observed transaction price, for accounting.
- `price`: median positive-sale transaction price within the week, then forward-filled from prior known weeks. There is no backward fill.
- `is_complete_week`: whether the entire Monday-to-Sunday week falls inside observed source-date coverage. The first and final partial weeks remain in accounting but cannot be gold labels. The final source week starts 2011-12-05 and ends before Sunday.

Forecast revenue is candidate price times predicted gross units. It is not a forecast of net retained revenue after returns, nor of fulfilled demand after same-day cancellations. Costs, inventory caps, and markdown rules are scenario constraints supplied by the user.

### Modeling universe

The configured minimum is twenty positive-sales weeks and three distinct observed positive-sale weekly prices. Selection only reads rows before the supplied fit cutoff. Rejection reasons are ordered: too few sales weeks first, then too few prices. `artifacts/universe.parquet` lists every considered product and its reason. The measured table above is the final available-history audit; each backtest fold must recompute membership using its own fit history. A product first seen at or after the cutoff is absent from that fit universe.

### Derived groups

UCI supplies descriptions, not categories. The project assigns nine transparent keyword groups: seasonal, kitchen, lighting, bags, garden, stationery, decor, toys, and other. The first accepted positive-sale description sets the category permanently when that product first appears. Later descriptions never rewrite previous categories. This is a coarse, precedence-ordered taxonomy, not retailer merchandising metadata; mixed-purpose items and missing descriptions can be misclassified. Product display descriptions also use the earliest accepted observation.

## Point-in-time feature contract

`PointInTimeFrame` materializes only rows strictly before `as_of`. Asking it to extend its cutoff, or read a week at or after the cutoff, raises an exception. Training and serving share the ordered feature names and deterministic public calendar utility, but do not share feature aggregations: batch uses Polars expressions; serving uses an immutable Python index with Python arithmetic and cutoff-specific bounded caches.

A gold row with target week `T` uses `as_of = T - seven days`, and its latest available weekly input is `T - fourteen days`. This explicitly leaves a decision gap. Realized target-week units are only the label. The price feature is the most recently known weekly price; the realized future price is never substituted. Consequently the fitted price coefficient is a lagged-price forecasting association and cannot identify a causal response to an unannounced future price change.

The ordered features are:

| Features | Definition |
|:--|:--|
| price, relative_price, log_price | Proposed price; proposed price divided by the own trailing thirteen-week median; natural logarithm of proposed price. Batch proposes the latest known price. |
| lag1, lag2, lag4, lag52 | Gross units at one, two, four, and fifty-two weeks before the exclusive cutoff; absent prelaunch weeks use zero. |
| mean4, std4 | Mean and population standard deviation over available rows in the four weeks before cutoff, including observed zero weeks. |
| weeks_since_change, last_change | Weeks since the last known weekly-price change and its proportional magnitude; before any change, age and zero respectively. |
| category_mean | Mean of other products' trailing-four-week means in the derived group, leaving out the focal product. |
| week_sin, week_cos | Sine and cosine of the target ISO week over a calendar-year period. |
| holiday_distance | Days to the nearest observed England and Wales bank holiday, including the royal-wedding holiday in the source period. This is a UK-market approximation, not a regional holiday model. |
| age_weeks | Weeks since first observed product-week. |
| zero_fraction | Fraction of observed rows in the trailing thirteen weeks with zero gross units, an imperfect stock-out proxy. |
| trend | Target-week distance in weeks from the fixed epoch 2009-01-05. |

The calendar is intentionally scoped to this historical dataset. A future operational deployment must replace or update the calendar for exceptional holidays outside the source years. Trailing histories beyond the observed data remain stale; the historical demo must not be interpreted as current demand.

## Verification artifacts

`artifacts/verification_pairs.json` fixes the product/cutoff definitions. `artifacts/skew.json` and `artifacts/leakage.json` record the panel SHA-256, feature names, tolerance, and measured maxima. Sampling covers ten chronological cutoffs and cycles across derived categories, with fifty products at each cutoff for skew and twenty for leakage. The leakage check deletes all rows at or after each cutoff and rebuilds both independent paths. The skew verifier also deliberately rounds the serving relative-price feature and confirms that comparison rejects the corruption.

Reproduce those artifacts after `make data`:

```python
from pricepoint_data.verification import verify_panel

verify_panel("data/silver/panel.parquet", "artifacts")
```

Public package interfaces are `ingest(path) -> IngestResult`, `clean(frame, config) -> CleanResult`, `build_panel(cleaned) -> DataFrame`, `select_universe(panel, fit_before) -> UniverseResult`, `batch_features(panel, as_of) -> DataFrame`, `feature_vector(panel, product_id, price, as_of) -> dict`, `ServingFeatureStore(panel).vector(product_id, price, as_of) -> dict`, and `make_features(panel) -> DataFrame`. Result objects carry accepted rows, quarantine rows, and count dictionaries; downstream code must not discard quarantine evidence.
