from datetime import date
from uuid import UUID

import pytest
from pricepoint_core.metrics import metric_stat, wape
from pricepoint_core.schemas import CurveRequest, MetricStat, OptimizeRequest, PredictRequest, uuid7
from pydantic import ValidationError


def test_strict_requests() -> None:
    request = PredictRequest.model_validate(
        {"product_id": "A", "price": 3.0, "as_of": "2011-01-03"}
    )
    assert request.as_of == date(2011, 1, 3)
    for price in ["3", -1, float("nan")]:
        with pytest.raises(ValidationError):
            PredictRequest.model_validate(
                {"product_id": "A", "price": price, "as_of": "2011-01-03"}
            )
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(
            {"product_id": "A", "price": 3.0, "as_of": "2011-01-03", "oops": 1}
        )
    with pytest.raises(ValidationError):
        CurveRequest(product_id="A", price_grid=[1.0, float("inf")], as_of=date.today())
    with pytest.raises(ValidationError):
        OptimizeRequest(
            product_id="A", current_price=2.0, cost_floor=1.0, min_markdown=0.8, max_markdown=0.2
        )


def test_metrics_do_not_hide_undefined_cases() -> None:
    assert wape([0, 10], [2, 8]) == 0.4
    with pytest.raises(ValueError):
        wape([0], [2])
    with pytest.raises(ValueError):
        wape([1], [1, 2])
    assert metric_stat([1.0, 3.0]).std == pytest.approx(2**0.5)
    with pytest.raises(ValidationError):
        MetricStat(mean=1.0, n=1)


def test_uuid_is_monotonic_version_seven() -> None:
    ids = [uuid7() for _ in range(1000)]
    assert ids == sorted(set(ids))
    assert all(UUID(value).version == 7 for value in ids)
