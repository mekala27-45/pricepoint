"""Deterministic estimators with one ordered feature and serialization contract."""

from __future__ import annotations

import math
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
import statsmodels.api as sm
from lightgbm import LGBMRegressor
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
FEATURE_NAMES = (
    "price",
    "relative_price",
    "log_price",
    "lag1",
    "lag2",
    "lag4",
    "lag52",
    "mean4",
    "std4",
    "weeks_since_change",
    "last_change",
    "category_mean",
    "week_sin",
    "week_cos",
    "holiday_distance",
    "age_weeks",
    "zero_fraction",
    "trend",
)
CONTRACT_VERSION = "1"


def feature_contract() -> dict[str, Any]:
    """Return a fresh schema, preserving order and physical types."""
    return {
        "version": CONTRACT_VERSION,
        "features": [{"name": name, "dtype": "float64"} for name in FEATURE_NAMES],
    }


def matrix(frame: pl.DataFrame, names: tuple[str, ...] = FEATURE_NAMES) -> FloatArray:
    """Reject incomplete or nonfinite input instead of silently imputing at serving."""
    missing = set(names) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing features: {sorted(missing)}")
    result = np.asarray(frame.select(names).to_numpy(), dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError("Features must be finite")
    return result


def targets(frame: pl.DataFrame) -> FloatArray:
    result = np.asarray(frame["units"].to_numpy(), dtype=np.float64)
    if len(result) == 0 or not np.all(np.isfinite(result)) or np.any(result < 0):
        raise ValueError("Training labels must be nonempty, finite, and nonnegative")
    return result


class DemandModel(ABC):
    """Shared adapter used by batch evaluation, serving, and the registry."""

    name: str
    version: str
    feature_contract: dict[str, Any]

    def __init__(self, name: str) -> None:
        self.name = name
        self.version = "unregistered"
        self.feature_contract = feature_contract()

    @abstractmethod
    def fit(self, frame: pl.DataFrame) -> DemandModel:
        """Fit only caller-supplied historical rows."""

    @abstractmethod
    def predict(self, frame: pl.DataFrame) -> FloatArray:
        """Return expected nonnegative units in row order."""

    def dump(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pickle.dumps(self, protocol=pickle.HIGHEST_PROTOCOL))


def load_model(path: Path | str) -> DemandModel:
    """Load a trusted, checksum-verified local artifact, never user-uploaded bytes."""
    result = pickle.loads(Path(path).read_bytes())
    if not isinstance(result, DemandModel):
        raise ValueError("Artifact does not implement the demand model contract")
    if result.feature_contract != feature_contract():
        raise ValueError("Model feature schema does not match the serving contract")
    return result


class BaselineModel(DemandModel):
    """Persistence, seasonal persistence, trailing mean, or global log-log OLS."""

    def __init__(self, kind: Literal["B0", "B1", "B2", "B3"] = "B2") -> None:
        super().__init__(kind)
        self.kind = kind
        self.coefficients = np.zeros(2, dtype=np.float64)
        self.smearing = 1.0
        self.fitted = False

    def fit(self, frame: pl.DataFrame) -> BaselineModel:
        y = targets(frame)
        if self.kind == "B3":
            design = np.column_stack((np.ones(frame.height), matrix(frame, ("log_price",))))
            fitted = sm.OLS(np.log1p(y), design).fit(cov_type="HC3")
            self.coefficients = np.asarray(fitted.params, dtype=np.float64)
            self.smearing = float(np.mean(np.exp(np.clip(fitted.resid, -20, 20))))
        self.fitted = True
        return self

    def predict(self, frame: pl.DataFrame) -> FloatArray:
        if not self.fitted:
            raise ValueError("Baseline must be fitted before prediction")
        if self.kind == "B3":
            log_price = matrix(frame, ("log_price",))[:, 0]
            log_units = self.coefficients[0] + self.coefficients[1] * log_price
            return np.asarray(
                np.maximum(0.0, np.exp(np.clip(log_units, -20, 20)) * self.smearing - 1),
                dtype=np.float64,
            )
        column = {"B0": "lag1", "B1": "lag52", "B2": "mean4"}[self.kind]
        return np.maximum(0.0, matrix(frame, (column,))[:, 0])


CONTROLS = ("log_price", "week_sin", "week_cos", "trend", "zero_fraction")


class CategoryElasticityModel(DemandModel):
    """Category OLS with product fixed effects and clustered standard errors.

    The outcome is log(1 + units), preserving zero-sale weeks. The reported
    log-price coefficient is therefore a log1p-demand association, approximating
    a units elasticity only when demand is appreciably greater than zero.
    Within-product demeaning absorbs the fixed effects without a dense dummy
    matrix. Seasonality, linear trend, and zero-sale frequency are controls.
    """

    def __init__(self) -> None:
        super().__init__("C1")
        self.models: dict[str, dict[str, Any]] = {}
        self.report: list[dict[str, Any]] = []
        self.fallback = BaselineModel("B3")

    def fit(self, frame: pl.DataFrame) -> CategoryElasticityModel:
        self.fallback.fit(frame)
        self.models = {}
        self.report = []
        for (category,), subset in frame.partition_by("category", as_dict=True).items():
            category_name = str(category)
            y = np.log1p(targets(subset))
            x = matrix(subset, CONTROLS)
            groups = np.asarray(subset["product_id"].to_list(), dtype=str)
            products = sorted(set(groups.tolist()))
            if len(y) < len(CONTROLS) + 3 or np.std(x[:, 0]) < 1e-10:
                self.report.append(
                    {"category": category_name, "status": "insufficient_variation", "rows": len(y)}
                )
                continue
            covariance: dict[str, Any] = (
                {"cov_type": "cluster", "cov_kwds": {"groups": groups, "use_correction": True}}
                if len(products) > 1
                else {"cov_type": "HC3"}
            )
            before = sm.OLS(y, np.column_stack((np.ones(len(y)), x[:, 0]))).fit(**covariance)
            centered_x = x.copy()
            centered_y = y.copy()
            means: dict[str, tuple[FloatArray, float]] = {}
            for product in products:
                mask = groups == product
                xmean = np.asarray(x[mask].mean(axis=0), dtype=np.float64)
                ymean = float(y[mask].mean())
                centered_x[mask] -= xmean
                centered_y[mask] -= ymean
                means[product] = (xmean, ymean)
            if np.std(centered_x[:, 0]) < 1e-10:
                self.report.append(
                    {
                        "category": category_name,
                        "status": "no_within_product_price_variation",
                        "rows": len(y),
                    }
                )
                continue
            after = sm.OLS(centered_y, centered_x).fit(**covariance)
            slopes = np.asarray(after.params, dtype=np.float64)
            intercepts = {
                product: ymean - float(xmean @ slopes) for product, (xmean, ymean) in means.items()
            }
            fitted_y = x @ slopes + np.array([intercepts[product] for product in groups])
            smear = float(np.mean(np.exp(np.clip(y - fitted_y, -20, 20))))
            self.models[category_name] = {
                "coefficients": slopes,
                "intercepts": intercepts,
                "default_intercept": float(np.mean(list(intercepts.values()))),
                "smearing": smear,
            }
            before_ci = np.asarray(before.conf_int(alpha=0.05), dtype=np.float64)[1]
            after_ci = np.asarray(after.conf_int(alpha=0.05), dtype=np.float64)[0]
            # With few product clusters, normal-reference intervals are approximate.
            self.report.append(
                {
                    "category": category_name,
                    "status": "estimated",
                    "rows": len(y),
                    "products": len(products),
                    "before": float(before.params[1]),
                    "before_se": float(before.bse[1]),
                    "before_low": float(before_ci[0]),
                    "before_high": float(before_ci[1]),
                    "after": float(slopes[0]),
                    "after_se": float(after.bse[0]),
                    "after_low": float(after_ci[0]),
                    "after_high": float(after_ci[1]),
                    "covariance": "product_cluster" if len(products) > 1 else "HC3",
                    "controls": [
                        "product_fixed_effects",
                        "week_sin",
                        "week_cos",
                        "trend",
                        "zero_fraction",
                    ],
                    "outcome": "log1p(units)",
                    "interpretation": (
                        "Lagged historical-price association with log1p gross units; "
                        "not contemporaneous or causal elasticity"
                    ),
                }
            )
        return self

    def predict(self, frame: pl.DataFrame) -> FloatArray:
        prediction = self.fallback.predict(frame)
        x = matrix(frame, CONTROLS)
        for index, row in enumerate(frame.select("product_id", "category").iter_rows(named=True)):
            coefficients = self.models.get(str(row["category"]))
            if coefficients is None:
                continue
            intercept = coefficients["intercepts"].get(
                str(row["product_id"]), coefficients["default_intercept"]
            )
            log_units = float(x[index] @ coefficients["coefficients"]) + float(intercept)
            prediction[index] = max(
                0.0, math.exp(max(-20, min(20, log_units))) * float(coefficients["smearing"]) - 1
            )
        return prediction


class LightGBMDemandModel(DemandModel):
    """Fixed, deterministic Tweedie model with optional held-out quantile comparison."""

    def __init__(
        self, *, n_estimators: int = 100, quantiles: bool = True, nominal: float = 0.9
    ) -> None:
        super().__init__("C2")
        if not 0 < nominal < 1:
            raise ValueError("Nominal coverage must lie in (0, 1)")
        self.n_estimators = n_estimators
        self.quantiles = quantiles
        self.nominal = nominal
        self.estimator: Any = None
        self.lower_estimator: Any = None
        self.upper_estimator: Any = None

    def _new(self, objective: str, alpha: float | None = None) -> Any:
        parameters: dict[str, Any] = {
            "objective": objective,
            "n_estimators": self.n_estimators,
            "num_leaves": 15,
            "learning_rate": 0.05,
            "min_child_samples": 30,
            "reg_lambda": 2.0,
            "random_state": 42,
            "n_jobs": 1,
            "deterministic": True,
            "force_col_wise": True,
            "verbosity": -1,
        }
        if objective == "tweedie":
            parameters["tweedie_variance_power"] = 1.5
        if alpha is not None:
            parameters["alpha"] = alpha
        return LGBMRegressor(**parameters)

    def fit(self, frame: pl.DataFrame) -> LightGBMDemandModel:
        x, y = matrix(frame), targets(frame)
        if not np.any(y > 0):
            raise ValueError("Tweedie demand model requires at least one positive label")
        self.estimator = self._new("tweedie")
        self.estimator.fit(x, y)
        if self.quantiles:
            alpha = (1 - self.nominal) / 2
            self.lower_estimator = self._new("quantile", alpha)
            self.upper_estimator = self._new("quantile", 1 - alpha)
            self.lower_estimator.fit(x, y)
            self.upper_estimator.fit(x, y)
        return self

    def predict(self, frame: pl.DataFrame) -> FloatArray:
        if self.estimator is None:
            raise ValueError("Demand model must be fitted before prediction")
        return np.maximum(0.0, np.asarray(self.estimator.predict(matrix(frame)), dtype=np.float64))

    def predict_quantiles(self, frame: pl.DataFrame) -> tuple[FloatArray, FloatArray]:
        if self.lower_estimator is None or self.upper_estimator is None:
            raise ValueError("Quantile comparison was not fitted")
        x = matrix(frame)
        left = np.maximum(0.0, np.asarray(self.lower_estimator.predict(x), dtype=np.float64))
        right = np.maximum(0.0, np.asarray(self.upper_estimator.predict(x), dtype=np.float64))
        return np.minimum(left, right), np.maximum(left, right)


def conformal_radius(residuals: FloatArray, nominal: float = 0.9) -> float:
    """Finite-sample split conformal absolute residual order statistic.

    A temporal calibration set is deliberately held out; serial dependence means
    the exchangeability assumption is approximate and measured test coverage wins.
    """
    if len(residuals) == 0 or not 0 < nominal < 1:
        raise ValueError("Calibration requires residuals and nominal coverage in (0, 1)")
    if not np.all(np.isfinite(residuals)) or np.any(residuals < 0):
        raise ValueError("Calibration residuals must be finite and nonnegative")
    rank = math.ceil((len(residuals) + 1) * nominal)
    if rank > len(residuals):
        raise ValueError("Insufficient calibration observations for finite conformal interval")
    return float(np.sort(residuals)[rank - 1])


class CalibratedModel(DemandModel):
    """Frozen point estimator with a separate chronological calibration sample."""

    def __init__(self, base: DemandModel, radius: float, nominal: float = 0.9) -> None:
        super().__init__(base.name)
        if radius < 0 or not math.isfinite(radius):
            raise ValueError("Conformal radius must be finite and nonnegative")
        self.base = base
        self.radius = radius
        self.nominal = nominal

    @classmethod
    def calibrate(
        cls, base: DemandModel, calibration: pl.DataFrame, nominal: float = 0.9
    ) -> CalibratedModel:
        residuals = np.abs(targets(calibration) - base.predict(calibration))
        return cls(base, conformal_radius(residuals, nominal), nominal)

    def fit(self, frame: pl.DataFrame) -> CalibratedModel:
        raise ValueError(
            "Refitting invalidates calibration; fit the base then recalibrate explicitly"
        )

    def predict(self, frame: pl.DataFrame) -> FloatArray:
        return self.base.predict(frame)

    def predict_interval(self, frame: pl.DataFrame) -> tuple[FloatArray, FloatArray, FloatArray]:
        point = self.predict(frame)
        return point, np.maximum(0.0, point - self.radius), point + self.radius

    def predict_quantiles(self, frame: pl.DataFrame) -> tuple[FloatArray, FloatArray]:
        if not isinstance(self.base, LightGBMDemandModel):
            raise ValueError("Only the fitted demand model has quantile comparison intervals")
        return self.base.predict_quantiles(frame)
