.PHONY: setup data train evaluate package monitor test lint check serve web
setup:
	uv sync --frozen
data:
	uv run pricepoint data
train:
	uv run pricepoint train
evaluate: train
package:
	uv run python -m scripts.package_artifacts
monitor:
	uv run pricepoint monitor
test:
	uv run pytest --cov --cov-report=term-missing --cov-report=xml
lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages
	uv run python scripts/check_no_em_dash.py
check: lint test
	uv run python -m scripts.verify_artifacts
	uv run python scripts/check_published_numbers.py
serve:
	uv run pricepoint serve
web:
	cd web && npm ci && npm run build
