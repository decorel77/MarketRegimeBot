"""Regime hysteresis / dwell-time filter (QA-013).

RESEARCH-STAGE UTILITY. Not wired into the production regime cycle:
``workflow/regime_cycle.py`` and the published snapshot artifacts are
untouched. The filter is evaluated through the QA-014 calibration harness
behind an explicit flag (``--hysteresis``) and may be promoted later behind a
default-off config switch.

Problem: a threshold classifier flips its label every time a score crosses a
boundary, so an input oscillating around a threshold (e.g. VIX around 32.5)
produces a different regime every bar. Consumers that re-position on each
regime change would churn.

The filter publishes a smoothed regime with three rules:

  1. Dwell confirmation — a candidate regime different from the published one
     must be observed ``min_dwell`` consecutive times with confidence at or
     above ``switch_confidence_min`` before the published regime switches.
     Noise that alternates candidates never accumulates confirmations.
  2. Asymmetric HIGH_VOLATILITY handling — switching INTO HIGH_VOLATILITY is
     fast (``high_vol_entry_dwell``, default 1 observation, but at a higher
     confidence bar): a risk-off signal must never be delayed by smoothing.
     Switching OUT is slow (``high_vol_exit_dwell``): calm must prove itself.
  3. Fail-closed wins instantly — a raw UNKNOWN input, an invalid
     regime/confidence, or metadata whose ``data_is_real`` / ``is_fresh`` is
     not exactly ``True`` forces the published regime to UNKNOWN immediately,
     with no dwell delay. Hysteresis must never hold a stale regime against a
     fail-closed signal. Recovery from UNKNOWN re-seeds after a single
     qualified observation.

Pure module: no IO, no network, no broker access, deterministic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from core.regime_contracts import VALID_REGIMES


@dataclass(frozen=True)
class HysteresisConfig:
    min_dwell: int = 3                       # confirmations for a normal switch
    switch_confidence_min: int = 60          # confidence gate for a confirmation
    high_vol_entry_dwell: int = 1            # fast risk-off entry …
    high_vol_entry_confidence_min: int = 70  # … but at a higher confidence bar
    high_vol_exit_dwell: int = 5             # calm must prove itself
    high_vol_exit_confidence_min: int = 60

    def validate(self) -> None:
        dwells = {
            "min_dwell": self.min_dwell,
            "high_vol_entry_dwell": self.high_vol_entry_dwell,
            "high_vol_exit_dwell": self.high_vol_exit_dwell,
        }
        for name, value in dwells.items():
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be an int >= 1, got {value!r}")
        confidences = {
            "switch_confidence_min": self.switch_confidence_min,
            "high_vol_entry_confidence_min": self.high_vol_entry_confidence_min,
            "high_vol_exit_confidence_min": self.high_vol_exit_confidence_min,
        }
        for name, value in confidences.items():
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError(f"{name} must be an int in [0, 100], got {value!r}")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class RegimeHysteresisFilter:
    """Stateful smoothing filter over a sequence of raw regime decisions.

    Starts at published UNKNOWN (warm-up) and is fed one observation per bar
    via :meth:`observe`. Every call returns a full decision record, so a
    replayed sequence is exactly reproducible.
    """

    def __init__(self, config: HysteresisConfig | None = None) -> None:
        self.config = config if config is not None else HysteresisConfig()
        self.config.validate()
        self._published = "UNKNOWN"
        self._published_confidence = 0
        self._pending: str | None = None
        self._pending_count = 0

    # --- Internal helpers ---------------------------------------------------------

    def _fail_closed_reason(
        self,
        market_regime: Any,
        confidence: Any,
        metadata: Mapping[str, Any] | None,
    ) -> str | None:
        if not isinstance(market_regime, str) or market_regime not in VALID_REGIMES:
            return f"invalid raw regime {market_regime!r}"
        if type(confidence) is not int or not 0 <= confidence <= 100:
            return f"invalid raw confidence {confidence!r}"
        if metadata is not None:
            if not isinstance(metadata, Mapping):
                return f"metadata must be a mapping, got {type(metadata).__name__}"
            for flag in ("data_is_real", "is_fresh"):
                if flag in metadata and metadata[flag] is not True:
                    return f"metadata {flag}={metadata[flag]!r} is not True"
        return None

    def _switch_requirements(self, candidate: str) -> tuple[int, int]:
        """(required_dwell, required_confidence) for switching to ``candidate``."""
        cfg = self.config
        if candidate == "HIGH_VOLATILITY":
            return cfg.high_vol_entry_dwell, cfg.high_vol_entry_confidence_min
        if self._published == "UNKNOWN":
            # Recovery from fail-closed/warm-up: one qualified observation.
            return 1, cfg.switch_confidence_min
        if self._published == "HIGH_VOLATILITY":
            return cfg.high_vol_exit_dwell, cfg.high_vol_exit_confidence_min
        return cfg.min_dwell, cfg.switch_confidence_min

    def _force_unknown(
        self, raw_regime: Any, raw_confidence: Any, reason: str, fail_closed: bool
    ) -> dict[str, Any]:
        switched = self._published != "UNKNOWN"
        self._published = "UNKNOWN"
        self._published_confidence = 0
        self._pending = None
        self._pending_count = 0
        return self._record(
            raw_regime=raw_regime if isinstance(raw_regime, str) else "INVALID",
            raw_confidence=raw_confidence if type(raw_confidence) is int else 0,
            switched=switched,
            fail_closed=fail_closed,
            reason=reason,
        )

    def _record(
        self,
        *,
        raw_regime: str,
        raw_confidence: int,
        switched: bool,
        fail_closed: bool,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "published_regime": self._published,
            "published_confidence": self._published_confidence,
            "raw_regime": raw_regime,
            "raw_confidence": raw_confidence,
            "pending_regime": self._pending,
            "pending_count": self._pending_count,
            "switched": switched,
            "fail_closed": fail_closed,
            "reason": reason,
        }

    # --- Public API ------------------------------------------------------------------

    def observe(
        self,
        market_regime: str,
        confidence: int,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Feed one raw decision; return the published (smoothed) decision."""
        fail_reason = self._fail_closed_reason(market_regime, confidence, metadata)
        if fail_reason is not None:
            return self._force_unknown(
                market_regime,
                confidence,
                f"Fail closed immediately: {fail_reason}",
                fail_closed=True,
            )

        if market_regime == "UNKNOWN":
            return self._force_unknown(
                market_regime,
                confidence,
                "Raw UNKNOWN adopted immediately (fail-closed propagation)",
                fail_closed=True,
            )

        if market_regime == self._published:
            self._published_confidence = confidence
            self._pending = None
            self._pending_count = 0
            return self._record(
                raw_regime=market_regime,
                raw_confidence=confidence,
                switched=False,
                fail_closed=False,
                reason="Raw regime agrees with published regime",
            )

        required_dwell, required_confidence = self._switch_requirements(market_regime)
        if market_regime != self._pending:
            self._pending = market_regime
            self._pending_count = 0
        if confidence >= required_confidence:
            self._pending_count += 1

        if self._pending_count >= required_dwell:
            previous = self._published
            self._published = market_regime
            self._published_confidence = confidence
            self._pending = None
            self._pending_count = 0
            return self._record(
                raw_regime=market_regime,
                raw_confidence=confidence,
                switched=True,
                fail_closed=False,
                reason=(
                    f"Switched {previous} -> {market_regime} after "
                    f"{required_dwell} qualified confirmation(s) "
                    f"(confidence >= {required_confidence})"
                ),
            )

        return self._record(
            raw_regime=market_regime,
            raw_confidence=confidence,
            switched=False,
            fail_closed=False,
            reason=(
                f"Holding {self._published}: candidate {market_regime} has "
                f"{self._pending_count}/{required_dwell} qualified "
                f"confirmation(s) (needs confidence >= {required_confidence})"
            ),
        )


def apply_hysteresis(
    observations: Iterable[Mapping[str, Any]],
    config: HysteresisConfig | None = None,
) -> list[dict[str, Any]]:
    """Replay a sequence of raw decisions through a fresh filter.

    Each observation is a mapping with ``market_regime`` and ``confidence``
    (and optionally ``metadata``). Returns one published decision record per
    observation."""
    regime_filter = RegimeHysteresisFilter(config)
    return [
        regime_filter.observe(
            observation.get("market_regime"),
            observation.get("confidence"),
            metadata=observation.get("metadata"),
        )
        for observation in observations
    ]
