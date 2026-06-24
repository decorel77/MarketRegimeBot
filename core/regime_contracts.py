"""Typed dry-run contracts for market regime detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


# QA-001 result snapshot envelope: every serialized RegimeDecision carries a
# freshness envelope so consumers (NovaBridge, NovaAllocationBot) can gate on
# snapshot age instead of trusting a once-real regime forever.
RESULT_SCHEMA_VERSION = "regime_result.v2"
PRODUCER_ID = "MarketRegimeBot"
FRESHNESS_WINDOW = timedelta(hours=24)


VALID_REGIMES = {
    "UNKNOWN",
    "BULL",
    "BEAR",
    "SIDEWAYS",
    "HIGH_VOLATILITY",
    "RISK_ON",
    "RISK_OFF",
}

VALID_RISK_LEVELS = {"UNKNOWN", "LOW", "NORMAL", "MEDIUM", "HIGH"}


class RegimeValidationError(ValueError):
    """Raised when a regime result violates safety or contract rules."""


def _parse_produced_at(produced_at: str) -> datetime:
    """Parse an injected ISO-8601 timestamp; naive values are assumed UTC."""
    try:
        parsed = datetime.fromisoformat(produced_at.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RegimeValidationError(
            f"produced_at must be an ISO-8601 timestamp, got: {produced_at!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_snapshot_envelope(produced_at: str | None = None) -> dict[str, Any]:
    """Build the QA-001 freshness envelope for result snapshot serialization.

    ``produced_at`` is injectable (tests, deterministic cycles); defaults to
    the current UTC time. ``fresh_until`` is ``produced_at`` + 24h.

    ``public_safe`` is an unconditional True: the regime snapshot carries only
    public-safe fields (regime label, confidence, risk level, reason, vol env,
    safety flags) — no account/order ids, secrets, or machine paths. It is a
    static dashboard-consumption marker and is NOT a realness claim; the
    fail-closed realness field stays ``data_is_real`` on the decision.
    """
    if produced_at is None:
        produced = datetime.now(timezone.utc)
    else:
        produced = _parse_produced_at(produced_at)
    return {
        "produced_at": produced.isoformat(),
        "fresh_until": (produced + FRESHNESS_WINDOW).isoformat(),
        "schema_version": RESULT_SCHEMA_VERSION,
        "producer_id": PRODUCER_ID,
        "public_safe": True,
    }


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


VALID_VOL_ENVS = {"LOW_VOL", "NORMAL", "HIGH_VOL", "UNKNOWN"}


@dataclass(frozen=True)
class RegimeDecision:
    project: str
    status: str
    market_regime: str
    confidence: int
    risk_level: str
    safety: RegimeSafetyState
    reason: tuple[str, ...] = ()
    volatility_env: str = "UNKNOWN"
    input_source: str = "unknown"
    # Realness flag (REPAIR-005 / canonical schema): True only when the decision
    # is derived from live market data (yfinance). Fixture/synthetic/snapshot-
    # derived inputs leave this False so downstream consumers reject the output.
    data_is_real: bool = False
    # Diagnostic only (QA-002): when a fallback source is forced to UNKNOWN,
    # the raw scores it would have classified are preserved here so the
    # plausible-but-fake value can never appear as the published regime.
    fallback_inputs: dict[str, Any] | None = None

    def validate(self) -> None:
        self.safety.validate()
        if self.status != "SAFE_DRY_RUN_REGIME":
            raise RegimeValidationError("Unexpected regime status.")
        if self.market_regime not in VALID_REGIMES:
            raise RegimeValidationError("Unknown market regime.")
        if self.risk_level not in VALID_RISK_LEVELS:
            raise RegimeValidationError("Unknown risk level.")
        # Fail closed on a malformed confidence *type* with a clear contract
        # error instead of accepting bool True as 1 or letting a string raise an
        # opaque TypeError in the range comparison below.
        conf = self.confidence
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            raise RegimeValidationError("Confidence must be a number between 0 and 100.")
        if conf != conf or conf in (float("inf"), float("-inf")):
            raise RegimeValidationError("Confidence must be a finite number between 0 and 100.")
        if not 0 <= conf <= 100:
            raise RegimeValidationError("Confidence must be between 0 and 100.")
        if self.volatility_env not in VALID_VOL_ENVS:
            raise RegimeValidationError(f"Unknown volatility_env: {self.volatility_env}")
        if not isinstance(self.data_is_real, bool):
            raise RegimeValidationError("data_is_real must be a boolean.")
        if self.fallback_inputs is not None and not isinstance(
            self.fallback_inputs, dict
        ):
            raise RegimeValidationError("fallback_inputs must be a dict or None.")

    @property
    def dry_run(self) -> bool:
        return self.safety.dry_run

    def to_dict(self, *, produced_at: str | None = None) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        safety = payload.pop("safety")
        payload.update(safety)
        payload["reason"] = list(payload.get("reason", []))
        payload.update(build_snapshot_envelope(produced_at))
        return payload


def build_unknown_regime_decision(
    input_source: str = "unknown",
    reason: tuple[str, ...] = (),
    fallback_inputs: dict[str, Any] | None = None,
) -> RegimeDecision:
    decision = RegimeDecision(
        project="MarketRegimeBot",
        status="SAFE_DRY_RUN_REGIME",
        market_regime="UNKNOWN",
        confidence=0,
        risk_level="UNKNOWN",
        safety=RegimeSafetyState(),
        reason=reason,
        input_source=input_source,
        fallback_inputs=fallback_inputs,
    )
    decision.validate()
    return decision

