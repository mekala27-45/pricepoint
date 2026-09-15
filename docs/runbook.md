# Operating the historical service

Use this runbook to reproduce an artifact, diagnose startup or request failures, review a candidate, or restore a previously saved incumbent. All commands run from the repository root. This is a historical public-data demonstration; do not treat its frozen dates as current retail evidence.

## Start and inspect

Install the locked workspace and inspect the available interface:

```sh
uv sync --locked --all-packages --all-groups
uv run pricepoint --help
uv run pricepoint models
uv run pricepoint predict 85099B 2.08 --as-of 2011-12-05
uv run pricepoint optimize 85099B 2.08 1.50 --inventory 100 --max-markdown 0.20 --objective margin
uv run pricepoint serve --host 127.0.0.1 --port 8000
```

The example product and date are present in the committed historical bundle. `GET /healthz` returns the loaded model version. `GET /v1/models` returns manifests and recorded gate results. `GET /metrics` exposes request counts and request-duration histograms. Interactive API documentation is available at `/docs` while the service runs.

Settings are read from environment variables, not automatically from an `.env` file. `PRICEPOINT_REGISTRY` selects the registry directory, `PRICEPOINT_PANEL` selects the aggregated panel, and `PRICEPOINT_SHADOW` enables candidate scoring when set to `true`. The defaults use committed artifacts. Bind a public interface only within an appropriately managed deployment; this service has no authentication layer.

## Startup fails

1. Read the startup exception before changing any artifacts. A missing registry, missing panel, missing incumbent, checksum mismatch, or feature-contract mismatch is intended to stop startup.
2. Confirm the working directory and the resolved registry/panel environment settings. Inspect the incumbent pointer and its referenced manifest together.
3. Run the offline verification command below. If a model checksum differs, recover the exact matching artifact from the reviewed release or rebuild the entire candidate. Do not edit the expected checksum to bless unexplained bytes.
4. For schema incompatibility, compare ordered feature names, dtypes, and contract version. Rebuild both batch and serving artifacts using the same contract, then run the real-data skew job. Restart the process after a reviewed artifact update; loaded models are not refreshed per request.

```sh
uv run python -m scripts.verify_artifacts
uv run python -m scripts.check_published_numbers
```

Model pickle files are trusted build outputs only. A matching checksum does not authorize loading an arbitrary external pickle.

## Requests fail or recommendations look wrong

| Symptom | Inspect and resolve |
|:--|:--|
| Unknown product | Check the served support map and the product's training-only eligibility. Use a product from the model's fitted universe. |
| Invalid decision date | Use an ISO-week Monday within the loaded artifact's availability window. A historical artifact cannot answer current-date requests. |
| Infeasible optimization | Check the intersection of the requested markdown interval, cost floor, fitted price support, and positive penny prices. The service raises a validation error when the intersection is empty. |
| Boundary warning | The optimum touches fitted support. Review support and confounding rather than expanding the search beyond the model's evidence. |
| Flat demand curve | Check the incumbent model version. The B2 trailing-mean baseline does not learn a price response; the displayed revenue curve still changes arithmetically with price. |
| Large shadow disagreement | Inspect product, price, cutoff, incumbent version, and candidate version together. Grid disagreement is descriptive and does not justify promotion on its own. |

Forecast units are gross positive quantities before credit notes. Inventory is a user-supplied cap, not an observed feed. For an optimization result, expected units can be capped by that inventory. Net retained revenue after returns is not the forecast target.

## Rebuild and backfill

The supported backfill is a complete deterministic rebuild of this pinned historical source. There is no incremental cursor pretending to track a live feed.

Before starting, save the existing incumbent pointer and retain its referenced model directory:

```sh
uv run python -c "from pathlib import Path; import shutil; Path('.cache').mkdir(exist_ok=True); shutil.copyfile('artifacts/registry/incumbent.json', '.cache/incumbent.before-package.json')"
```

Then run the rebuild and explicit packaging sequence:

```sh
uv run pricepoint data
uv run pricepoint train
uv run pricepoint monitor
uv run python -c "from pricepoint_data.verification import verify_panel; verify_panel('data/silver/panel.parquet', 'artifacts')"
uv run python -m scripts.package_artifacts
uv run python -m scripts.loadtest --seconds 30 --concurrency 4 --output artifacts/loadtest-inprocess.json
uv run python -m scripts.publish_results
uv run pricepoint check
```

The data command verifies the public download, ingests both sheets, preserves quarantines, rebuilds the accounting panel, and excludes incomplete source weeks from gold labels. Review `artifacts/data_report.json` and `artifacts/universe.parquet` before trusting changed evaluation outputs. The training command writes held-out predictions, final-fit features, model intermediates, and a local MLflow run. It does not publish a service.

Packaging is an explicit operation that can assess and change the local incumbent pointer when all promotion rules pass. The backup above must therefore be saved before packaging. Repeating training creates another local experiment record and refreshes measurement timestamps. Repeated packaging reuses an existing matching model identity instead of silently overwriting its model bytes; assessments are retained separately. A changed dataset, model configuration, code identity, or feature contract requires a different model identity. Review the generated version and manifest instead of treating identical filenames as proof of reproducibility.

Raw inputs and intermediate transaction data remain ignored. Commit only the intended aggregate/model evidence and regenerated static bundle. Rebuild the static site after changing its bundle. GitHub Pages publication is a separate repository workflow, and the monitoring command never deploys it.

## Review promotion evidence

Read `artifacts/promotion.json`, the candidate manifest and assessments, [RESULTS](../RESULTS.md), and the CI evidence together. The promotion implementation requires all of the following:

- Relative WAPE improvement over the incumbent, using comparable held-out evaluation.
- No category beyond the permitted relative degradation.
- Measured warm single-candidate latency below the configured limit.
- Held-out conformal coverage within tolerance of nominal.
- Exact ordered serving feature contract.
- Independent training-serving feature agreement across the required sample.

Missing or incompatible evidence fails closed. A promotion failure is a valid outcome and must not be fixed by deleting an inconvenient gate. The current published bundle keeps B2 responses while C2 runs in shadow when temporally eligible. Changing that relationship requires a reviewed assessment, not a demo preference.

## Restore a saved incumbent

Stop or drain the process before changing its artifacts. Keep the current pointer as an additional incident record. The registry's normal promotion path writes a temporary JSON pointer then uses `os.replace`; restoration should use the same atomic replacement pattern after validating the saved version.

Run this Python block in the locked repository environment after the backup command above has created its source file:

```python
import json
import os
from pathlib import Path

from pricepoint_models.registry import Registry

registry = Registry(Path("artifacts/registry"))
saved = json.loads(Path(".cache/incumbent.before-package.json").read_text(encoding="utf-8"))
registry.load(saved["version"])
pointer = registry.root / "incumbent.json"
Path(".cache/incumbent.before-rollback.json").write_bytes(pointer.read_bytes())
temporary = registry.root / "incumbent.rollback.tmp"
temporary.write_text(json.dumps(saved, indent=2), encoding="utf-8")
os.replace(temporary, pointer)
```

Restart, check `/healthz`, inspect `/v1/models`, and repeat a known prediction. Restoration changes the service pointer; it does not rewrite a static bundle already published on Pages. Restore or regenerate the matching bundle and redeploy the reviewed site separately when necessary. Record the reason, old and restored versions, and the verification outcome with the release or incident notes.

## Drift and delayed refits

`pricepoint monitor` performs a chronological replay. It observes a completed week, evaluates PSI and recent WAPE, respects cooldown, and schedules a refit for a later decision cutoff. The timeline distinguishes a trigger from a completed refit. A boundary trigger may remain pending because the dataset has no subsequent decision week.

`RetrainingTrigger` supports a persisted state file and explicit `manual=True` override. Repeated evaluation of a handled week returns its stored decision; earlier out-of-order dates fail. Manual override bypasses a cooldown for the chosen observation and is recorded as overridden. It requests retraining, not registry promotion or deployment.

Investigate changes in source coverage, availability proxies, product mix, and calendar features before treating PSI as evidence that retraining will help. The monitoring replay uses C2 on its documented historical universe; it is not a report of live B2 production traffic.

## Latency diagnosis

Compare like with like. `latency-gate.json` measures the warm isolated candidate path. `loadtest-inprocess.json` measures full ASGI requests with enabled shadow work. The container CI artifact measures TCP HTTP against the built image, and records resolved image identities alongside the result. A passing isolated gate cannot be substituted for full HTTP latency.

Use the in-repo load generator with the same duration, concurrency, payload population, shadow setting, and transport as the measurement being investigated. Retain raw samples and errors. If latency or errors regress, first inspect logs, whether caches are cold, process resource contention, candidate shadow work, and changes in the feature or model path. Stop publishing new numbers until their artifacts and methodology agree.
