"""Regime Model v2 — multi-factor regime scoring (QA-012).

RESEARCH-STAGE MODEL. v2 is NOT wired into the production regime cycle:
``workflow/regime_cycle.py`` and the published snapshot artifacts still use
the v1 classifier exclusively. v2 is evaluated through the QA-014 calibration
harness (``--model v2``) and is only promoted to production after calibration
on real history justifies it — which also requires a result-snapshot schema
bump so consumers can see which model produced a decision.

Why v2 exists (weaknesses QA-014 exposed in v1):
  * v1's only trend input is a trailing 20-session return, so regime labels
    lag ~10 sessions behind boundaries (BULL persists deep into a flat market,
    BEAR is recognised late).
  * v1 has no drawdown awareness: a crash with VIX below 32.5 cannot reach
    HIGH_VOLATILITY no matter how deep the drawdown.
  * v1 confidence is a rescaled raw score, not a margin from the decision
    threshold.

v2 factors (all computed from the same trailing close window production uses):
  trend_score     [-1, 1]  identical production 20-session return math (reused,
                           never copied, from core.market_data_reader)
  volatility_score [0, 1]  identical production VIX mapping
  drawdown_score   [0, 1]  decline from the window peak, 15% drawdown → 1.0
  ma_gap_score    [-1, 1]  last close vs 10-session moving average, ±2.5% → ±1
  momentum_score  [-1, 1]  (up days − down days) / sessions over the last 10

The short-window factors (ma_gap, momentum) react within ~5 sessions at
regime boundaries where the 20-session return still reflects the old regime.

Pure module: no IO, no network, no broker access. Fail-closed: factor
computation returns ``None`` on insufficient/invalid data and classification
raises ``ValueError`` on out-of-range inputs — never a plausible fake regime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Reuse the exact production scoring math so v2's trend/volatility factors can
# never drift from what the production reader computes.
from core.market_data_reader import _compute_trend_score, _compute_volatility_score
from core.regime_classifier import RegimeResult

MODEL_VERSION = "v2"

# Calibration constants live in core/regime_calibration.py (HWL-005). They are
# re-exported here unchanged so the model's public surface (e.g.
# ``regime_model_v2.VOL_HIGH_THRESHOLD``) and every reason-string interpolation
# stay byte-identical. Tuning a value is a model change — edit it in the
# calibration module, where the golden test (test_regime_calibration_golden.py)
# guards it.
from core.regime_calibration import (  # noqa: F401  (re-exported public constants)
    SHORT_WINDOW,
    DRAWDOWN_NORMALISE,
    MA_GAP_NORMALISE,
    WEIGHT_TREND,
    WEIGHT_MA_GAP,
    WEIGHT_MOMENTUM,
    VOL_HIGH_THRESHOLD,
    VOL_ELEVATED_THRESHOLD,
    DRAWDOWN_SEVERE_THRESHOLD,
    COMPOSITE_BULL_THRESHOLD,
    COMPOSITE_BEAR_THRESHOLD,
    BEAR_DRAWDOWN_QUALIFIER,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _is_real_number(value: object) -> bool:
    """True only for a real int/float (bool excluded — True is not a price)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# --- Inputs -----------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeInputV2:
    trend_score: float       # [-1, 1]  production 20-session return factor
    volatility_score: float  # [0, 1]   production VIX factor
    drawdown_score: float    # [0, 1]   decline from window peak
    ma_gap_score: float      # [-1, 1]  price vs short moving average
    momentum_score: float    # [-1, 1]  up/down-day balance

    def validate(self) -> None:
        bounds = {
            "trend_score": (self.trend_score, -1.0, 1.0),
            "volatility_score": (self.volatility_score, 0.0, 1.0),
            "drawdown_score": (self.drawdown_score, 0.0, 1.0),
            "ma_gap_score": (self.ma_gap_score, -1.0, 1.0),
            "momentum_score": (self.momentum_score, -1.0, 1.0),
        }
        for name, (value, low, high) in bounds.items():
            # Reject bool (an int subclass — True must not slip through as 1.0),
            # consistent with the v1 RegimeInput.validate hardening.
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number, got {value!r}")
            if not low <= value <= high:
                raise ValueError(f"{name} must be in [{low}, {high}], got {value}")


# --- Factor computation -------------------------------------------------------------------


def _drawdown_score(closes: list[float]) -> float:
    peak = max(closes)
    drawdown = (peak - closes[-1]) / peak
    return _clamp(round(drawdown / DRAWDOWN_NORMALISE, 4), 0.0, 1.0)


def _ma_gap_score(closes: list[float]) -> float:
    window = closes[-SHORT_WINDOW:]
    moving_average = sum(window) / len(window)
    gap = closes[-1] / moving_average - 1.0
    return _clamp(round(gap / MA_GAP_NORMALISE, 4), -1.0, 1.0)


def _momentum_score(closes: list[float]) -> float:
    steps = min(SHORT_WINDOW, len(closes) - 1)
    deltas = [closes[-k] - closes[-k - 1] for k in range(1, steps + 1)]
    ups = sum(1 for d in deltas if d > 0)
    downs = sum(1 for d in deltas if d < 0)
    return round((ups - downs) / steps, 4)


def compute_v2_inputs(
    spy_closes: list[float],
    qqq_closes: list[float],
    vix_close: float,
) -> RegimeInputV2 | None:
    """Compute all v2 factors from trailing close windows.

    Returns ``None`` (fail-closed, mirroring the production reader) when any
    series is too short or contains non-finite/non-positive prices. Each
    ticker-level factor is averaged across SPY and QQQ, like the production
    trend score.
    """
    series = {"SPY": spy_closes, "QQQ": qqq_closes}
    for closes in series.values():
        # Fail closed (return None) on a malformed container or element instead
        # of crashing: a non-sequence has no len(), and math.isfinite raises on a
        # non-numeric / bool element. The docstring promises None on bad data.
        if not isinstance(closes, (list, tuple)) or len(closes) < SHORT_WINDOW + 1:
            return None
        if any(not _is_real_number(c) or not math.isfinite(c) or c <= 0.0 for c in closes):
            return None
    if not _is_real_number(vix_close) or not math.isfinite(vix_close) or vix_close <= 0.0:
        return None

    trend_score = _compute_trend_score(series)
    if trend_score is None:
        return None
    volatility_score = _compute_volatility_score(vix_close)

    def _averaged(factor) -> float:
        return round(sum(factor(c) for c in series.values()) / len(series), 4)

    inputs = RegimeInputV2(
        trend_score=trend_score,
        volatility_score=volatility_score,
        drawdown_score=_averaged(_drawdown_score),
        ma_gap_score=_averaged(_ma_gap_score),
        momentum_score=_averaged(_momentum_score),
    )
    inputs.validate()
    return inputs


def composite_score(inputs: RegimeInputV2) -> float:
    """Weighted directional composite of the trend-family factors."""
    return round(
        WEIGHT_TREND * inputs.trend_score
        + WEIGHT_MA_GAP * inputs.ma_gap_score
        + WEIGHT_MOMENTUM * inputs.momentum_score,
        4,
    )


# --- Classifier --------------------------------------------------------------------------


def classify_regime_v2(inputs: RegimeInputV2) -> RegimeResult:
    """Classify a RegimeInputV2 into the same regime vocabulary as v1.

    Priority: HIGH_VOLATILITY (direct or drawdown escalation) → BULL → BEAR
    (composite or drawdown-qualified) → SIDEWAYS. Raises ``ValueError`` on
    out-of-range inputs (fail-closed) — never invents a regime.
    """
    inputs.validate()
    v = inputs.volatility_score
    dd = inputs.drawdown_score
    composite = composite_score(inputs)
    factors_reason = (
        f"model v2 composite {composite:.2f} (trend {inputs.trend_score:.2f}, "
        f"ma_gap {inputs.ma_gap_score:.2f}, momentum {inputs.momentum_score:.2f}); "
        f"drawdown {dd:.2f}, volatility {v:.2f}"
    )

    if v > VOL_HIGH_THRESHOLD:
        return RegimeResult(
            market_regime="HIGH_VOLATILITY",
            confidence=min(100, int(v * 100)),
            risk_level="HIGH",
            reason=(
                f"Volatility score {v:.2f} exceeds high-volatility threshold "
                f"{VOL_HIGH_THRESHOLD}",
                factors_reason,
            ),
        )

    if v >= VOL_ELEVATED_THRESHOLD and dd >= DRAWDOWN_SEVERE_THRESHOLD:
        return RegimeResult(
            market_regime="HIGH_VOLATILITY",
            confidence=min(100, int(((v + dd) / 2) * 100)),
            risk_level="HIGH",
            reason=(
                f"Elevated volatility {v:.2f} with severe drawdown {dd:.2f} "
                "escalated to HIGH_VOLATILITY (v2 escalation rule)",
                factors_reason,
            ),
        )

    if composite > COMPOSITE_BULL_THRESHOLD:
        return RegimeResult(
            market_regime="BULL",
            confidence=min(100, int(composite * 100)),
            risk_level="NORMAL" if composite < 0.85 else "HIGH",
            reason=(
                f"Composite trend {composite:.2f} above bull threshold "
                f"{COMPOSITE_BULL_THRESHOLD}",
                factors_reason,
            ),
        )

    if composite < COMPOSITE_BEAR_THRESHOLD or (
        dd >= BEAR_DRAWDOWN_QUALIFIER and composite < 0.0
    ):
        if composite < COMPOSITE_BEAR_THRESHOLD:
            trigger = (
                f"Composite trend {composite:.2f} below bear threshold "
                f"{COMPOSITE_BEAR_THRESHOLD}"
            )
        else:
            trigger = (
                f"Deep drawdown {dd:.2f} with non-positive composite "
                f"{composite:.2f} (v2 drawdown-qualified bear)"
            )
        return RegimeResult(
            market_regime="BEAR",
            confidence=min(100, int(max(abs(composite), dd) * 100)),
            risk_level="HIGH",
            reason=(trigger, factors_reason),
        )

    return RegimeResult(
        market_regime="SIDEWAYS",
        confidence=max(0, min(100, int((1.0 - abs(composite) - v) * 100))),
        risk_level="LOW",
        reason=(
            f"Composite trend {composite:.2f} and volatility {v:.2f} indicate "
            "range-bound conditions",
            factors_reason,
        ),
    )


def parameters() -> dict[str, Any]:
    """v2 model parameters for calibration-report traceability."""
    return {
        "short_window": SHORT_WINDOW,
        "drawdown_normalise": DRAWDOWN_NORMALISE,
        "ma_gap_normalise": MA_GAP_NORMALISE,
        "weight_trend": WEIGHT_TREND,
        "weight_ma_gap": WEIGHT_MA_GAP,
        "weight_momentum": WEIGHT_MOMENTUM,
        "vol_high_threshold": VOL_HIGH_THRESHOLD,
        "vol_elevated_threshold": VOL_ELEVATED_THRESHOLD,
        "drawdown_severe_threshold": DRAWDOWN_SEVERE_THRESHOLD,
        "composite_bull_threshold": COMPOSITE_BULL_THRESHOLD,
        "composite_bear_threshold": COMPOSITE_BEAR_THRESHOLD,
        "bear_drawdown_qualifier": BEAR_DRAWDOWN_QUALIFIER,
    }
