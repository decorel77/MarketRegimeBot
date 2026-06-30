"""Hard-stop mis-classification sensitivity study (REGIME-TRUST-002).

RESEARCH / REPORTING ONLY. No live trading, no real broker data, no production
behaviour change, no threshold change.

REGIME-TRUST-001 showed the production classifier is directionally wired on
constructed structure. This follow-up quantifies a different, safety-critical
question: **how sensitive is the downstream hard-stop to mis-classification?**

The downstream consumer (NovaBotV2) halts new buys when the regime export sets
``MaxNewPositions=0`` (``core/nova_koopbot.py`` hard-stop). That export is keyed on
the regime label; the two HIGH-risk regimes the production classifier emits —
``HIGH_VOLATILITY`` and ``BEAR`` — are the defensive states that map to a
hard-stop. This study models the hard-stop decision **at the classifier output**
(it does not re-implement, wire, or change the downstream translation) and asks:

* **false-hard-stop rate** — P(a benign true state is mis-measured into a
  hard-stop regime): an *unnecessary* trading halt (opportunity cost, not unsafe);
* **missed-hard-stop rate** — P(a true hard-stop state is mis-measured into a
  trading regime): the *dangerous* error — the bot keeps buying into a real
  bear / high-vol market.

Method (deterministic, synthetic): for each true ``(trend, volatility)`` state on
a grid, perturb the inputs by every offset on a fixed lattice (a noise model),
clamp to the classifier's valid domain, re-classify with the **production**
``classify_regime``, and count how often the hard-stop flips. No RNG: the result
is a pure function of the grid + lattice, so the report is byte-reproducible.

Imports only the pure production classifier (``core.regime_classifier``) + stdlib;
no pandas, no broker, no network, no runtime read/write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from core.regime_classifier import (
    _TREND_BEAR_THRESHOLD,
    _TREND_BULL_THRESHOLD,
    _VOLATILITY_HIGH_THRESHOLD,
    RegimeInput,
    classify_regime,
)

# The HIGH-risk regimes that map to a downstream defensive hard-stop
# (MaxNewPositions=0). Documented, not wired: this study only models the decision.
HARD_STOP_REGIMES = frozenset({"HIGH_VOLATILITY", "BEAR"})

PRODUCER = "MarketRegimeBot.research.regime_hard_stop_sensitivity"
REPORT_SCHEMA_VERSION = "regime_hard_stop_sensitivity.v1"


def triggers_hard_stop(regime: str) -> bool:
    """True if ``regime`` maps to a downstream MaxNewPositions=0 hard-stop."""
    return regime in HARD_STOP_REGIMES


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def classify_state(trend: float, volatility: float) -> str:
    """Return the production ``market_regime`` for a (clamped) input state."""
    inputs = RegimeInput(
        trend_score=_clamp(float(trend), -1.0, 1.0),
        volatility_score=_clamp(float(volatility), 0.0, 1.0),
    )
    return classify_regime(inputs).market_regime


def lattice_offsets(radius_steps: int, step: float) -> list[tuple[float, float]]:
    """Deterministic square lattice of (d_trend, d_vol) offsets.

    ``radius_steps`` rings out from 0; ``step`` is the spacing. The centre
    (0, 0) — the no-noise case — is always included.
    """
    if radius_steps < 0:
        raise ValueError("radius_steps must be >= 0")
    if step <= 0:
        raise ValueError("step must be > 0")
    offsets: list[tuple[float, float]] = []
    for i in range(-radius_steps, radius_steps + 1):
        for j in range(-radius_steps, radius_steps + 1):
            offsets.append((round(i * step, 6), round(j * step, 6)))
    return offsets


@dataclass(frozen=True)
class StateSensitivity:
    trend: float
    volatility: float
    true_regime: str
    true_hard_stop: bool
    samples: int
    hard_stop_samples: int
    flipped_samples: int  # observed hard-stop != true hard-stop

    @property
    def flip_rate(self) -> float:
        return self.flipped_samples / self.samples if self.samples else 0.0


def sensitivity_at_state(
    trend: float, volatility: float, offsets: Sequence[tuple[float, float]]
) -> StateSensitivity:
    """Measure how often perturbing one true state flips the hard-stop decision."""
    true_regime = classify_state(trend, volatility)
    true_stop = triggers_hard_stop(true_regime)
    n = 0
    stop_n = 0
    flipped = 0
    for d_trend, d_vol in offsets:
        obs_regime = classify_state(trend + d_trend, volatility + d_vol)
        obs_stop = triggers_hard_stop(obs_regime)
        n += 1
        if obs_stop:
            stop_n += 1
        if obs_stop != true_stop:
            flipped += 1
    return StateSensitivity(
        trend=round(float(trend), 6),
        volatility=round(float(volatility), 6),
        true_regime=true_regime,
        true_hard_stop=true_stop,
        samples=n,
        hard_stop_samples=stop_n,
        flipped_samples=flipped,
    )


def run_sensitivity_study(
    *,
    trend_grid: Sequence[float],
    vol_grid: Sequence[float],
    noise_levels: Sequence[float],
    radius_steps: int = 2,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Aggregate false- and missed-hard-stop rates across a grid × noise sweep.

    For each ``noise_level`` (the lattice ``step``), every true grid state is
    perturbed across the lattice and the two error rates are pooled over all
    benign / hard-stop true states respectively.
    """
    if not trend_grid or not vol_grid or not noise_levels:
        raise ValueError("trend_grid, vol_grid and noise_levels must be non-empty")

    by_noise: list[dict[str, Any]] = []
    for level in noise_levels:
        offsets = lattice_offsets(radius_steps, level) if level > 0 else [(0.0, 0.0)]
        # benign-state pool (true NOT hard-stop) -> false hard stops
        benign_samples = benign_false = 0
        # hard-stop-state pool (true IS hard-stop) -> missed hard stops
        stop_samples = stop_missed = 0
        per_state: list[dict[str, Any]] = []
        for t in trend_grid:
            for v in vol_grid:
                s = sensitivity_at_state(t, v, offsets)
                per_state.append(
                    {
                        "trend": s.trend,
                        "volatility": s.volatility,
                        "true_regime": s.true_regime,
                        "true_hard_stop": s.true_hard_stop,
                        "samples": s.samples,
                        "hard_stop_samples": s.hard_stop_samples,
                        "flip_rate": round(s.flip_rate, 6),
                    }
                )
                if s.true_hard_stop:
                    stop_samples += s.samples
                    stop_missed += s.samples - s.hard_stop_samples
                else:
                    benign_samples += s.samples
                    benign_false += s.hard_stop_samples
        by_noise.append(
            {
                "noise_level": round(float(level), 6),
                "lattice_points": len(offsets),
                "benign_samples": benign_samples,
                "false_hard_stop_rate": round(benign_false / benign_samples, 6)
                if benign_samples
                else None,
                "hard_stop_samples": stop_samples,
                "missed_hard_stop_rate": round(stop_missed / stop_samples, 6)
                if stop_samples
                else None,
                "per_state": per_state,
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
        "grid": {
            "trend_grid": [round(float(t), 6) for t in trend_grid],
            "vol_grid": [round(float(v), 6) for v in vol_grid],
            "noise_levels": [round(float(n), 6) for n in noise_levels],
            "radius_steps": radius_steps,
        },
        "by_noise_level": by_noise,
    }
