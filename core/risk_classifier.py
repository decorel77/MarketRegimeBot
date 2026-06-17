"""REGIME-PHASE-004 — pure risk-on / risk-off classifier.

Maps already-computed, in-memory regime + volatility signals to a
``RISK_ON`` / ``RISK_OFF`` / ``UNKNOWN`` label. It performs **no I/O** and
connects to nothing — exactly the ``core/volatility_classifier.py`` pattern.

Safety (mirrors ``docs/REGIME_PHASE_004_synthetic_plan.md`` and the repo lock):

  * synthetic-only / offline — no market reads, no ``yfinance``, no network,
    no broker, no scheduler. Reads no ``data/system`` / ``data/history`` path.
  * advisory / diagnostic-only — the output carries **no** order intent,
    allocation weight, position size, risk/capital, or execution-eligibility
    field. It cannot reach a broker or move money.
  * fail-closed — missing / invalid / stale / not-real inputs yield a safe,
    non-actionable ``UNKNOWN`` (never a guess). The function never raises.
  * provenance-honest — ``data_is_real`` is propagated verbatim and is never
    upgraded to ``True``; below the confidence floor the label is ``UNKNOWN`` /
    ``INSUFFICIENT`` and no confidence number is published as trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from core.regime_contracts import FRESHNESS_WINDOW, VALID_REGIMES
from core.volatility_classifier import VALID_VOL_ENVS

SCHEMA_VERSION = "risk_classifier.v1"

# Labels (RISK_ON / RISK_OFF already exist in core/regime_contracts.VALID_REGIMES).
RISK_ON, RISK_OFF, UNKNOWN = "RISK_ON", "RISK_OFF", "UNKNOWN"

# Statuses.
OK, INSUFFICIENT, STALE, MISSING, INVALID, NOT_REAL = (
    "OK", "INSUFFICIENT", "STALE", "MISSING", "INVALID", "NOT_REAL",
)

# Required input fields; absence of any one fails closed to MISSING.
REQUIRED_FIELDS = ("regime", "regime_confidence", "volatility_class", "data_is_real", "is_fresh")

# Documented confidence floor: below this the signal is non-actionable.
CONFIDENCE_FLOOR = 0.50

# Risk direction contributed by each regime / volatility class. +1 leans
# risk-on, -1 leans risk-off, 0 is neutral. UNKNOWN regime is handled as
# INSUFFICIENT before scoring.
_REGIME_DIRECTION = {
    "BULL": 1, "RISK_ON": 1,
    "BEAR": -1, "RISK_OFF": -1, "HIGH_VOLATILITY": -1,
    "SIDEWAYS": 0,
}
_VOL_DIRECTION = {"LOW_VOL": 1, "HIGH_VOL": -1, "NORMAL": 0, "UNKNOWN": 0}


@dataclass(frozen=True)
class RiskResult:
    label: str               # RISK_ON | RISK_OFF | UNKNOWN
    status: str              # OK | INSUFFICIENT | STALE | MISSING | INVALID | NOT_REAL
    confidence: float | None  # withheld (None) unless status is OK
    data_is_real: bool       # propagated verbatim, never invented/upgraded
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "status": self.status,
            "confidence": self.confidence,
            "data_is_real": self.data_is_real,
            "notes": list(self.notes),
            "schema_version": SCHEMA_VERSION,
        }


def _unknown(status: str, note: str, *, data_is_real: bool) -> RiskResult:
    return RiskResult(
        label=UNKNOWN, status=status, confidence=None,
        data_is_real=bool(data_is_real), notes=(note,),
    )


def _is_real_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _combine_realness(value: Any) -> tuple[bool | None, bool]:
    """Return (combined_realness, valid). A list of per-signal flags is reduced
    with ``all`` so mixed provenance fails closed to untrusted."""
    if isinstance(value, bool):
        return value, True
    if isinstance(value, (list, tuple)) and value and all(isinstance(x, bool) for x in value):
        return all(value), True
    return None, False


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def classify_risk(signals: Mapping[str, Any] | None, *, now: str | None = None) -> RiskResult:
    """Classify already-computed regime/volatility signals into a RiskResult.

    Deterministic: freshness is evaluated against the injected ``now`` (ISO
    string); the scoring itself uses no clock or RNG. Never raises.
    """
    if not isinstance(signals, Mapping):
        return _unknown(MISSING, "No signals provided", data_is_real=False)

    missing = [f for f in REQUIRED_FIELDS if f not in signals]
    if missing:
        return _unknown(MISSING, f"Missing required field(s): {sorted(missing)}", data_is_real=False)

    regime = signals.get("regime")
    regime_confidence = signals.get("regime_confidence")
    volatility_class = signals.get("volatility_class")
    is_fresh = signals.get("is_fresh")
    produced_at = signals.get("produced_at")

    # --- INVALID: wrong types / out-of-range before any realness/freshness use.
    if not isinstance(regime, str) or regime not in VALID_REGIMES:
        return _unknown(INVALID, f"Invalid regime: {regime!r}", data_is_real=False)
    if not _is_real_number(regime_confidence) or not 0.0 <= float(regime_confidence) <= 1.0:
        return _unknown(INVALID, f"regime_confidence out of [0,1]: {regime_confidence!r}", data_is_real=False)
    if not isinstance(volatility_class, str) or volatility_class not in VALID_VOL_ENVS:
        return _unknown(INVALID, f"Invalid volatility_class: {volatility_class!r}", data_is_real=False)
    if not isinstance(is_fresh, bool):
        return _unknown(INVALID, f"is_fresh must be a bool: {is_fresh!r}", data_is_real=False)
    combined_real, real_valid = _combine_realness(signals.get("data_is_real"))
    if not real_valid:
        return _unknown(INVALID, "data_is_real must be a bool or list of bools", data_is_real=False)
    produced_dt = None
    if produced_at is not None:
        produced_dt = _parse_iso(produced_at)
        if produced_dt is None:
            return _unknown(INVALID, f"produced_at is not ISO-8601: {produced_at!r}", data_is_real=False)

    # --- NOT_REAL: never trust (and never upgrade) a non-real / mixed source.
    if combined_real is not True:
        return _unknown(NOT_REAL, "data_is_real is not True — fail closed to untrusted", data_is_real=False)

    # --- STALE: stale flag or expired freshness window is non-actionable.
    if is_fresh is not True:
        return _unknown(STALE, "is_fresh is not True — non-actionable", data_is_real=True)
    if produced_dt is not None:
        current = _parse_iso(now) or datetime.now(timezone.utc)
        if current >= produced_dt + FRESHNESS_WINDOW:
            return _unknown(STALE, "produced_at older than freshness window — non-actionable", data_is_real=True)

    # --- INSUFFICIENT: unknown regime, low confidence, or conflicting signals.
    conf = float(regime_confidence)
    if regime == UNKNOWN:
        return _unknown(INSUFFICIENT, "Regime is UNKNOWN — no directional signal", data_is_real=True)
    if conf < CONFIDENCE_FLOOR:
        return _unknown(INSUFFICIENT, f"regime_confidence {conf} below floor {CONFIDENCE_FLOOR}", data_is_real=True)

    direction = _REGIME_DIRECTION.get(regime, 0) + _VOL_DIRECTION.get(volatility_class, 0)
    if direction == 0:
        return _unknown(INSUFFICIENT, "Conflicting/neutral regime and volatility signals", data_is_real=True)

    # --- OK: actionable advisory label.
    label = RISK_ON if direction > 0 else RISK_OFF
    return RiskResult(
        label=label,
        status=OK,
        confidence=round(conf, 4),
        data_is_real=True,
        notes=(f"{label} from regime={regime}, volatility={volatility_class} (direction {direction:+d})",),
    )
