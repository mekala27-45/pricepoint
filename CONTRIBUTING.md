# Contributing

Changes should keep the historical evidence reproducible and the serving contract explicit. Start with [the architecture](ARCHITECTURE.md), [data contract](docs/data.md), and [metric definitions](docs/metrics.md).

## Local setup

Use the Python and Node versions pinned by the workspace and CI. Install the committed dependency resolutions:

```sh
uv sync --locked --all-packages --all-groups
uv run pricepoint --help
```

From `web`, run:

```sh
npm ci
npm run test
npm run typecheck
npm run build
```

The static site and committed serving artifacts work without the raw workbook. A Docker daemon is not required for local development or Python tests. Container build, startup, and HTTP measurement run in CI. To reproduce the public-data evaluation, follow the full rebuild sequence in [the runbook](docs/runbook.md).

## Required checks

Run these from the repository root before submitting a change:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run python -m scripts.check_no_em_dash
uv run pytest --cov --cov-report=term-missing --cov-report=xml
uv run python -m scripts.verify_artifacts
uv run python -m scripts.check_published_numbers
```

On restricted Windows environments, pytest can use a writable local temporary directory:

```sh
uv run pytest --basetemp .cache/pytest-local
```

Run the complete suite before committing. A test that invokes an external executable must first probe availability and name the missing dependency in an explicit skip; CI must assert that dependency is installed so the same test cannot silently skip there. Prefer behavioral and property tests to assertions that merely copy an implementation.

## Evidence and contracts

- Never use random splits for this time series. New split logic must retain chronological fit, calibration, decision, and target boundaries.
- Preserve signed accounting and gross-demand semantics. A target change requires new evaluation, artifact identity, documentation, and publication evidence.
- Keep Polars batch features and Python serving features independent. A feature change must pass both deletion-based leakage checks and the real-panel skew comparison.
- A feature name, order, dtype, or meaning change is a contract change. Update the version deliberately and rebuild compatible artifacts.
- Every promotion rule needs a test that constructs a candidate violating that rule. Evidence must fail closed when missing or incompatible.
- Register published measurements before adding their rendered claims. Keep raw observations or a clearly stated reducible artifact, and regenerate report fragments with the publication script.
- Never commit raw transaction files, customer identifiers, credentials, or employer material. Retain aggregate public-data evidence required to audit the result.
- Avoid em dash characters in source, comments, generated text, and documentation. The repository gate checks that policy.

## Pull requests

Use a focused branch and a conventional commit message that names the changed behavior. Explain the problem, the resulting behavior, the relevant validation, and any limitation a reviewer needs to understand. If a change affects published numbers, include the regenerated evidence and explain the changed methodology rather than only replacing a table.

Inspect the web export in a narrow mobile viewport as well as desktop. Keep axes, uncertainty semantics, source labels, and keyboard interactions usable. Static and API modes must use the same response meaning.

## Model and deployment changes

Training, packaging, registry assessment, and deployment are separate operations. Inspect the candidate evidence and saved incumbent before packaging against a registry you want to preserve. Preserve immutable model bytes and append assessment evidence when repeating a review. Follow the [runbook](docs/runbook.md) for rollback.

CI verifies source quality, behavior, stored evidence, independent features, the container, and the static build. GitHub Pages publication deploys the reviewed static bundle. The monitoring simulation schedules historical refits; it does not authorize production deployment or business price changes.
