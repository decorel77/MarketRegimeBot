"""Hard-stop persistence / recovery-lag study (REGIME-TRUST-003).

RESEARCH / REPORTING ONLY. No live trading, no real broker data, no production
behaviour change, no threshold change, no runtime write.

REGIME-TRUST-002 (`regime_hard_stop_sensitivity`) measured the *static* error
rates of the hard-stop decision under input noise — false-hard-stop and
missed-hard-stop. This follow-up looks at the *time* dimension of the same
hard-stop:

1. **Recovery lag** — once the underlying regime has genuinely normalised (the
   true trend crosses back above the bear threshold), how many steps does the
   *measured* hard-stop persist? The mechanism modelled is **indicator
   smoothing**: a trend score is in practice a smoothed/averaged series, so it
   lags a true recovery. We model that with an explicit, documented causal
   moving-average filter (NOT the production indicator internals — those read real
   data) over a synthetic step recovery, and count how long the smoothed regime
   stays in a hard-stop after the true transition. A persistent hard-stop after
   recovery is an *opportunity cost* (the bot keeps halting buys into a recovered
   market), the time-domain analog of REGIME-TRUST-002's false-hard-stop.

2. **Boundary false-hard-stop rate** — REGIME-TRUST-002 found mis-classifications
   cluster *just past the −0.5 bear threshold*. Here we quantify, for a benign
   series whose centre sits just above −0.5 but which oscillates across it, what
   fraction of points trip a (false) BEAR hard-stop. Report only.

Method is deterministic and synthetic (no RNG): every series is a pure function
of its parameters, so the report is byte-reproducible. The hard-stop decision is
re-used verbatim from the REGIME-TRUST-002 harness (`classify_state` /
`triggers_hard_stop`), which calls the **production** `classify_regime`; this
module never re-implements, wires, or changes the classifier or its thresholds.

Imports only the REGIME-TRUST-002 harness + the pure classifier thresholds +
stdlib; no pandas, no broker, no network, no runtime read/write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from core.regime_classifier import (
    _TREND_BEAR_THRESHOLD,
    _TREND_BULL_THRESHOLD,
    _VOLATILITY_HIGH_THRESHOLD,
)
from research.regime_hard_stop_sensitivity import (
    HARD_STOP_REGIMES,
    classify_state,
    triggers_hard_stop,
)

PRODUCER = "MarketRegimeBot.research.regime_hard_stop_persistence"
REPORT_SCHEMA_VERSION = "regime_hard_stop_persistence.v1"

# A benign volatility used for the trend-driven trajectories (well below the
# HIGH_VOLATILITY threshold), so the hard-stop is driven purely by the trend.
_BENIGN_VOL = 0.2


def causal_moving_average(series: Sequence[float], window: int) -> list[float]:
    """Deterministic causal SMA over ``series`` with window ``window``.

    Each point is the mean of up to ``window`` most-recent values (a partial
    window at the start). ``window == 1`` is the identity (no smoothing). This is
    a *documented modelling choice* for indicator lag — not the production
    indicator, which reads real market data.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float] = []
    for i in range(len(series)):
        lo = max(0, i - window + 1)
        chunk = series[lo : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def step_recovery_trend(
    *, bear_level: float, recovery_level: float, pre_steps: int, post_steps: int
) -> list[float]:
    """A step trajectory: ``pre_steps`` at ``bear_level`` then ``post_steps`` at ``recovery_level``."""
    if pre_steps < 1 or post_steps < 1:
        raise ValueError("pre_steps and post_steps must be >= 1")
    return [float(bear_level)] * pre_steps + [float(recovery_level)] * post_steps


@dataclass(frozen=True)
class RecoveryLagResult:
    window: int
    bear_level: float
    recovery_level: float
    pre_steps: int
    post_steps: int
    transition_index: int          # first step at which the TRUE regime is benign
    measured_recovery_index: int | None  # first step the MEASURED hard-stop clears
    recovery_lag_steps: int | None       # measured_recovery_index - transition_index
    persisted_to_end: bool         # hard-stop never cleared within the series

    @property
    def true_is_recovery(self) -> bool:
        return (
            self.bear_level < _TREND_BEAR_THRESHOLD
            and self.recovery_level >= _TREND_BEAR_THRESHOLD
        )


def measure_recovery_lag(
    *,
    bear_level: float = -0.8,
    recovery_level: float = -0.3,
    pre_steps: int = 10,
    post_steps: int = 20,
    window: int = 5,
    vol: float = _BENIGN_VOL,
) -> RecoveryLagResult:
    """Measure how long the smoothed hard-stop persists after a true recovery."""
    true_trend = step_recovery_trend(
        bear_level=bear_level, recovery_level=recovery_level,
        pre_steps=pre_steps, post_steps=post_steps,
    )
    smoothed = causal_moving_average(true_trend, window)
    hard = [triggers_hard_stop(classify_state(t, vol)) for t in smoothed]

    transition_index = pre_steps  # first index where the TRUE trend is benign
    measured_recovery_index: int | None = None
    for i in range(transition_index, len(hard)):
        if not hard[i]:
            measured_recovery_index = i
            break

    if measured_recovery_index is None:
        lag: int | None = None
        persisted = True
    else:
        lag = measured_recovery_index - transition_index
        persisted = False

    return RecoveryLagResult(
        window=window,
        bear_level=round(float(bear_level), 6),
        recovery_level=round(float(recovery_level), 6),
        pre_steps=pre_steps,
        post_steps=post_steps,
        transition_index=transition_index,
        measured_recovery_index=measured_recovery_index,
        recovery_lag_steps=lag,
        persisted_to_end=persisted,
    )


@dataclass(frozen=True)
class BoundaryFalseStopResult:
    center: float
    half_width: float
    points: int
    vol: float
    true_regime: str
    true_hard_stop: bool
    hard_stop_points: int
    false_hard_stop_rate: float | None  # None when the centre is itself a hard-stop


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    if n < 1:
        raise ValueError("points must be >= 1")
    if n == 1:
        return [(lo + hi) / 2.0]
    step = (hi - lo) / (n - 1)
    return [round(lo + step * i, 6) for i in range(n)]


def boundary_false_stop(
    *, center: float = -0.45, half_width: float = 0.1, points: int = 21,
    vol: float = _BENIGN_VOL,
) -> BoundaryFalseStopResult:
    """Fraction of a benign-centred oscillation across −0.5 that trips a hard-stop."""
    true_regime = classify_state(center, vol)
    true_stop = triggers_hard_stop(true_regime)
    trends = _linspace(center - half_width, center + half_width, points)
    hard_points = sum(1 for t in trends if triggers_hard_stop(classify_state(t, vol)))
    # Only meaningful as a FALSE rate when the centre (true state) is benign.
    rate = None if true_stop else round(hard_points / points, 6)
    return BoundaryFalseStopResult(
        center=round(float(center), 6),
        half_width=round(float(half_width), 6),
        points=points,
        vol=round(float(vol), 6),
        true_regime=true_regime,
        true_hard_stop=true_stop,
        hard_stop_points=hard_points,
        false_hard_stop_rate=rate,
    )


def run_persistence_study(
    *,
    windows: Sequence[int] = (1, 3, 5, 10),
    bear_level: float = -0.8,
    recovery_levels: Sequence[float] = (-0.3, 0.0, 0.3),
    pre_steps: int = 10,
    post_steps: int = 30,
    boundary_centers: Sequence[float] = (-0.45, -0.40, -0.30),
    boundary_half_widths: Sequence[float] = (0.05, 0.1, 0.2),
    boundary_points: int = 21,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Aggregate the recovery-lag sweep and the boundary false-stop sweep."""
    if not windows or not recovery_levels:
        raise ValueError("windows and recovery_levels must be non-empty")

    recovery_rows: list[dict[str, Any]] = []
    for window in windows:
        for rec in recovery_levels:
            r = measure_recovery_lag(
                bear_level=bear_level, recovery_level=rec,
                pre_steps=pre_steps, post_steps=post_steps, window=window,
            )
            recovery_rows.append(
                {
                    "window": r.window,
                    "recovery_level": r.recovery_level,
                    "recovery_lag_steps": r.recovery_lag_steps,
                    "persisted_to_end": r.persisted_to_end,
                    "true_is_recovery": r.true_is_recovery,
                }
            )

    boundary_rows: list[dict[str, Any]] = []
    for center in boundary_centers:
        for hw in boundary_half_widths:
            b = boundary_false_stop(center=center, half_width=hw, points=boundary_points)
            boundary_rows.append(
                {
                    "center": b.center,
                    "half_width": b.half_width,
                    "true_regime": b.true_regime,
                    "true_hard_stop": b.true_hard_stop,
                    "hard_stop_points": b.hard_stop_points,
                    "false_hard_stop_rate": b.false_hard_stop_rate,
                }
            )

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "producer": PRODUCER,
        "research_only": True,
        "not_for_live_trading": True,
        "data_is_real": False,
        "generated_at": generated_at,
        "hard_stop_regimes": sorted(HARD_STOP_REGIMES),
        "thresholds": {
            "trend_bull_threshold": _TREND_BULL_THRESHOLD,
            "trend_bear_threshold": _TREND_BEAR_THRESHOLD,
            "volatility_high_threshold": _VOLATILITY_HIGH_THRESHOLD,
        },
        "smoothing_model": "causal_simple_moving_average (documented; not the production indicator)",
        "recovery_lag": {
            "bear_level": round(float(bear_level), 6),
            "pre_steps": pre_steps,
            "post_steps": post_steps,
            "windows": list(windows),
            "recovery_levels": [round(float(r), 6) for r in recovery_levels],
            "rows": recovery_rows,
        },
        "boundary_false_stop": {
            "points": boundary_points,
            "rows": boundary_rows,
        },
    }
