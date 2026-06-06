"""Typed dry-run contracts for market regime detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALID_REGIMES = {
    "UNKNOWN",
    "BULL",
    "BEAR",
    "SIDEWAYS",
    "HIGH_VOLATILITY",
    "RISK_ON",
    "RISK_OFF",
}

VALID_RISK_LEVELS = {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}


class RegimeValidationError(ValueError):
    """Raised when a regime result violates safety or contract rules."""


@dataclass(frozen=True)
class RegimeSafetyState:
    dry_run: bool = True
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    live_trading_enabled: bool = False
    money_movement_enabled: bool = False
    writes_to_other_projects_enabled: bool = False
    allocation_export_enabled: bool = False

    def validate(self) -> None:
        if not self.dry_run:
            raise RegimeValidationError("MarketRegimeBot must remain dry-run.")
        unsafe_flags = {
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "money_movement_enabled": self.money_movement_enabled,
            "writes_to_other_projects_enabled": self.writes_to_other_projects_enabled,
            "allocation_export_enabled": self.allocation_export_enabled,
        }
        enabled = [name for name, value in unsafe_flags.items() if value]
        if enabled:
            raise RegimeValidationError(
                "Unsafe regime flags enabled: " + ", ".join(enabled)
            )


@dataclass(frozen=True)
class RegimeDecision:
    project: str
    status: str
    market_regime: str
    confidence: int
    risk_level: str
    safety: RegimeSafetyState

    def validate(self) -> None:
        self.safety.validate()
        if self.status != "SAFE_DRY_RUN_REGIME":
            raise RegimeValidationError("Unexpected regime status.")
        if self.market_regime not in VALID_REGIMES:
            raise RegimeValidationError("Unknown market regime.")
        if self.risk_level not in VALID_RISK_LEVELS:
            raise RegimeValidationError("Unknown risk level.")
        if not 0 <= self.confidence <= 100:
            raise RegimeValidationError("Confidence must be between 0 and 100.")

    @property
    def dry_run(self) -> bool:
        return self.safety.dry_run

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        safety = payload.pop("safety")
        payload.update(safety)
        return payload


def build_unknown_regime_decision() -> RegimeDecision:
    decision = RegimeDecision(
        project="MarketRegimeBot",
        status="SAFE_DRY_RUN_REGIME",
        market_regime="UNKNOWN",
        confidence=0,
        risk_level="UNKNOWN",
        safety=RegimeSafetyState(),
    )
    decision.validate()
    return decision

