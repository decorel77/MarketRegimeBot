"""Regime trust / edge study on synthetic structured data (REGIME-TRUST-001).

RESEARCH / REPORTING ONLY.

Answers one question — *does the v1/v2 regime classifier add directional edge?* —
on **synthetic data with a KNOWN regime structure**. It builds a deterministic,
seeded price history containing an explicit bull → crash/high-vol → bear →
sideways arc, replays the production classifier over it via
``calibration_harness`` (byte-identical production scoring), and measures whether
the emitted regime labels align with the *sign* of realised forward returns and
whether a simple regime-conditioned long-only exposure would have improved
risk-adjusted outcome versus buy-and-hold.

**Honesty boundary (critical):** synthetic structure can only show the classifier
*responds correctly to structure that is there by construction*. It is **not** a
real-market edge proof — that needs real/approved OHLCV history and is
**HUMAN_GATED** (no real broker data here). Every artifact carries
``research_only`` / ``not_for_live_trading`` / ``data_is_real=False`` and the study
writes nothing into ``data/system/`` (it reuses the harness write-guard).

Hermeticity: imports only the stdlib + the in-repo research/production modules.
No network, no broker, no live import, deterministic for a fixed seed.
"""
from __future__ import annotations

import random
from typing import Any, Mapping

from research.calibration_harness import History, build_calibration_report

PRODUCER = "MarketRegimeBot.research.regime_trust_study"
STUDY_SCHEMA_VERSION = "regime_trust_study.v1"

# Long-only, risk-managed exposure per regime: full risk only when BULL, flat
# otherwise. Deliberately conservative (never short) so the comparison is a fair
# "did regime-awareness avoid drawdowns?" rather than a leveraged bet.
DEFAULT_EXPOSURE = {
    "BULL": 1.0,
    "SIDEWAYS": 0.0,
    "BEAR": 0.0,
    "HIGH_VOLATILITY": 0.0,
    "UNKNOWN": 0.0,
}


# --- Synthetic structured history -------------------------------------------------


def _segment(n: int, start: float, drift: float, noise: float, vix: float,
             seed: int) -> tuple[list[float], list[float]]:
    rng = random.Random(seed)
    price = start
    closes: list[float] = []
    vixes: list[float] = []
    for _ in range(n):
        price = max(price * (1.0 + drift) + rng.uniform(-noise, noise) * start, 1.0)
        closes.append(round(price, 2))
        vixes.append(round(max(9.0, vix + rng.uniform(-2.0, 2.0)), 2))
    return closes, vixes


# Each tuple: (bars, start_price, daily_drift, noise_frac, vix_centre, seed).
# bull (rising, calm) → crash (falling hard, high VIX) → bear (drifting down) →
# sideways (flat, moderate VIX).
STRUCTURED_SEGMENTS = (
    (60, 300.0, 0.004, 0.002, 14.0, 1),
    (30, 380.0, -0.012, 0.010, 34.0, 2),
    (40, 300.0, -0.004, 0.004, 24.0, 3),
    (50, 260.0, 0.000, 0.004, 18.0, 4),
)


def generate_structured_history(qqq_factor: float = 1.1) -> History:
    """Build the deterministic bull→crash→bear→sideways synthetic history."""
    import datetime as _dt

    spy: list[float] = []
    vix: list[float] = []
    for bars, start, drift, noise, vix_centre, seed in STRUCTURED_SEGMENTS:
        seg_spy, seg_vix = _segment(bars, start, drift, noise, vix_centre, seed)
        if spy:  # splice price level continuous across segment joins
            offset = spy[-1] / seg_spy[0]
            seg_spy = [round(x * offset, 2) for x in seg_spy]
        spy.extend(seg_spy)
        vix.extend(seg_vix)
    base = _dt.date(2025, 1, 1)
    dates = [(base + _dt.timedelta(days=i)).isoformat() for i in range(len(spy))]
    rows = [
        {"date": dates[i], "spy_close": spy[i],
         "qqq_close": round(spy[i] * qqq_factor, 2), "vix_close": vix[i]}
        for i in range(len(spy))
    ]
    return History.from_rows(rows)


# --- Regime-conditioned edge ------------------------------------------------------


def regime_conditioned_edge(
    records: list[Mapping[str, Any]],
    history: History,
    *,
    forward_horizon: int = 5,
    exposure: Mapping[str, float] = DEFAULT_EXPOSURE,
) -> dict[str, Any]:
    """Compare a regime-conditioned long-only exposure vs buy-and-hold.

    For each classified bar with a full forward window, the strategy return is
    ``exposure[regime] * forward_return`` and the baseline is the raw
    ``forward_return``. Reports mean per-bar return and a simple mean/abs-mean
    risk proxy for both, plus the edge (strategy − baseline)."""
    spy = history.spy_close
    strat: list[float] = []
    base: list[float] = []
    for record in records:
        i = record["bar_index"]
        j = i + forward_horizon
        if j >= len(spy):
            continue
        fwd = (spy[j] - spy[i]) / spy[i]
        base.append(fwd)
        strat.append(exposure.get(record["market_regime"], 0.0) * fwd)
    if not base:
        return {"comparable_bars": 0}

    def _mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 6)

    def _downside(xs: list[float]) -> float:
        negs = [x for x in xs if x < 0]
        return round(sum(negs) / len(xs), 6) if xs else 0.0

    strat_mean, base_mean = _mean(strat), _mean(base)
    return {
        "comparable_bars": len(base),
        "exposure_map": dict(exposure),
        "buy_hold_mean_forward": base_mean,
        "regime_conditioned_mean_forward": strat_mean,
        "buy_hold_mean_downside": _downside(base),
        "regime_conditioned_mean_downside": _downside(strat),
        "edge_mean_forward": round(strat_mean - base_mean, 6),
        "improves_mean": strat_mean >= base_mean,
        "reduces_downside": _downside(strat) >= _downside(base),  # less negative
    }


# --- Study report -----------------------------------------------------------------


def build_regime_trust_study(
    *,
    model_version: str = "v2",
    forward_horizon: int = 5,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the research-only regime trust/edge study over synthetic data."""
    history = generate_structured_history()
    report = build_calibration_report(
        history,
        source_label="synthetic_structured_bull_crash_bear_sideways",
        model_version=model_version,
        forward_horizon=forward_horizon,
        generated_at=generated_at,
    )
    edge = regime_conditioned_edge(
        report["records"], history, forward_horizon=forward_horizon
    )
    calibration = report["calibration"]
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "producer": PRODUCER,
        "research_only": True,
        "not_for_live_trading": True,
        "data_is_real": False,
        "honesty_note": (
            "Synthetic structured data only. Demonstrates the classifier responds "
            "correctly to constructed regime structure; it does NOT prove real-market "
            "edge. Real/approved-data validation is HUMAN_GATED."
        ),
        "model_version": model_version,
        "forward_horizon": forward_horizon,
        "history_bars": report["history"]["bars"],
        "regime_counts": calibration["regime_counts"],
        "forward_return_by_regime": calibration["forward_return_by_regime"],
        "directional_hit_rate": calibration["directional_hit_rate"],
        "persistence_rate": calibration["persistence_rate"],
        "walk_forward": {
            "fold_count": report["walk_forward"]["fold_count"],
            "max_distribution_drift": report["walk_forward"]["max_distribution_drift"],
            "mean_persistence_rate": report["walk_forward"]["mean_persistence_rate"],
        },
        "regime_conditioned_edge": edge,
    }
