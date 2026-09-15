"""Temporal demand models, calibrated intervals, and promotion controls."""

from pricepoint_models.backtest import BacktestResult, rolling_origin_splits, run_backtest
from pricepoint_models.estimators import (
    FEATURE_NAMES,
    BaselineModel,
    CalibratedModel,
    CategoryElasticityModel,
    DemandModel,
    LightGBMDemandModel,
    feature_contract,
    load_model,
)
from pricepoint_models.gates import GateEvidence, GateResult, evaluate_gates
from pricepoint_models.optimizer import optimize
from pricepoint_models.registry import Registry

__all__ = [
    "FEATURE_NAMES",
    "BacktestResult",
    "BaselineModel",
    "CalibratedModel",
    "CategoryElasticityModel",
    "DemandModel",
    "GateEvidence",
    "GateResult",
    "LightGBMDemandModel",
    "Registry",
    "evaluate_gates",
    "feature_contract",
    "load_model",
    "optimize",
    "rolling_origin_splits",
    "run_backtest",
]
