"""A stateful retraining policy with persisted cooldown and idempotency."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class TriggerDecision:
    week: str
    fired: bool
    reason: str
    overridden: bool


class RetrainingTrigger:
    def __init__(self, cooldown_days: int = 14, state_path: Path | None = None) -> None:
        if cooldown_days < 1:
            raise ValueError("Cooldown must be positive")
        self.cooldown_days = cooldown_days
        self.state_path = state_path
        self.last_fired: date | None = None
        self.last_checked: date | None = None
        self.decisions: dict[str, TriggerDecision] = {}
        if state_path is not None and state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.last_fired = (
                date.fromisoformat(state["last_fired"]) if state["last_fired"] else None
            )
            self.last_checked = (
                date.fromisoformat(state["last_checked"]) if state["last_checked"] else None
            )
            self.decisions = {
                key: TriggerDecision(**value) for key, value in state["decisions"].items()
            }

    def evaluate(
        self,
        week: date,
        feature_psi: dict[str, float],
        recent_wape: list[float],
        baseline_wape: float,
        manual: bool = False,
    ) -> TriggerDecision:
        if not math.isfinite(baseline_wape) or baseline_wape <= 0:
            raise ValueError("Baseline WAPE must be finite and positive")
        values = list(feature_psi.values()) + recent_wape
        if not all(math.isfinite(v) and v >= 0 for v in values):
            raise ValueError("Monitoring evidence must be finite and nonnegative")
        key = week.isoformat()
        if key in self.decisions and (not manual or self.decisions[key].overridden):
            return self.decisions[key]
        if self.last_checked is not None and week < self.last_checked:
            raise ValueError("Monitoring dates must be chronological")
        drifted = sorted(name for name, value in feature_psi.items() if value > 0.25)
        degraded = len(recent_wape) >= 4 and sum(recent_wape[-4:]) / 4 > baseline_wape * 1.1
        cooling = self.last_fired is not None and (week - self.last_fired).days < self.cooldown_days
        reasons = []
        if drifted:
            reasons.append("PSI above threshold: " + ", ".join(drifted))
        if degraded:
            reasons.append("Four-week WAPE degraded relative to training validation")
        if manual:
            fired, reason = True, "Manual override"
        elif cooling and reasons:
            fired, reason = False, "Cooldown: " + "; ".join(reasons)
        elif reasons:
            fired, reason = True, "; ".join(reasons)
        else:
            fired, reason = False, "Within monitoring thresholds"
        result = TriggerDecision(key, fired, reason, manual)
        self.decisions[key] = result
        self.last_checked = week
        if fired:
            self.last_fired = week
        self._save()
        return result

    def _save(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "last_fired": self.last_fired.isoformat() if self.last_fired else None,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "decisions": {key: asdict(value) for key, value in self.decisions.items()},
        }
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(body, indent=2), encoding="utf-8")
        os.replace(temporary, self.state_path)
