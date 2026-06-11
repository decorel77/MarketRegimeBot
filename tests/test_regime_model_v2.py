"""QA-012 unit tests: multi-factor Regime Model v2 (research-stage, pure).

Production behavior is untouched — these tests cover only the new
core/regime_model_v2.py module: factor math, fail-closed validation, every
classification branch, and determinism.
"""

from __future__ import annotations

import pytest

from core import regime_model_v2 as v2
from core.regime_contracts import VALID_REGIMES, VALID_RISK_LEVELS


def _inputs(
    trend: float = 0.0,
    vol: float = 0.0,
    drawdown: float = 0.0,
    ma_gap: float = 0.0,
    momentum: float = 0.0,
) -> v2.RegimeInputV2:
    return v2.RegimeInputV2(
        trend_score=trend,
        volatility_score=vol,
        drawdown_score=drawdown,
        ma_gap_score=ma_gap,
        momentum_score=momentum,
    )


# --- Factor computation ------------------------------------------------------------


def test_drawdown_score_from_peak():
    # Peak 100, last 90 → 10% drawdown → 0.10 / 0.15 normalise = 0.6667.
    closes = [100.0] * 11 + [95.0, 90.0]
    assert v2._drawdown_score(closes) == pytest.approx(0.6667, abs=1e-4)


def test_drawdown_score_clamped_to_one():
    closes = [100.0] * 11 + [50.0]  # 50% drawdown >> 15% normalise
    assert v2._drawdown_score(closes) == 1.0


def test_ma_gap_score_zero_on_flat_series():
    assert v2._ma_gap_score([100.0] * 15) == 0.0


def test_ma_gap_score_sign_follows_price_vs_average():
    rising = [100.0 + i for i in range(15)]
    falling = [100.0 - i for i in range(15)]
    assert v2._ma_gap_score(rising) > 0.0
    assert v2._ma_gap_score(falling) < 0.0


def test_momentum_score_extremes_and_balance():
    ups = [100.0 + i for i in range(12)]
    downs = [100.0 - i for i in range(12)]
    flat = [100.0] * 12
    assert v2._momentum_score(ups) == 1.0
    assert v2._momentum_score(downs) == -1.0
    assert v2._momentum_score(flat) == 0.0


def test_compute_v2_inputs_on_simple_series():
    spy = [100.0 * 1.005**i for i in range(21)]
    qqq = [300.0 * 1.006**i for i in range(21)]
    inputs = v2.compute_v2_inputs(spy, qqq, vix_close=14.0)
    assert inputs is not None
    assert inputs.trend_score == 1.0          # ~11% avg return, clamped
    assert inputs.volatility_score == 0.0     # VIX 14 below the low bound
    assert inputs.drawdown_score == 0.0       # monotone rise, no drawdown
    assert inputs.ma_gap_score > 0.5
    assert inputs.momentum_score == 1.0


def test_compute_v2_inputs_fails_closed_on_short_series():
    short = [100.0] * v2.SHORT_WINDOW  # one bar short of SHORT_WINDOW + 1
    assert v2.compute_v2_inputs(short, short, vix_close=20.0) is None


def test_compute_v2_inputs_fails_closed_on_bad_prices():
    good = [100.0] * 21
    bad = [100.0] * 20 + [0.0]
    assert v2.compute_v2_inputs(bad, good, vix_close=20.0) is None
    assert v2.compute_v2_inputs(good, good, vix_close=0.0) is None
    nan_series = [100.0] * 20 + [float("nan")]
    assert v2.compute_v2_inputs(good, nan_series, vix_close=20.0) is None


# --- Input validation (fail-closed) ---------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("trend", 1.5),
        ("trend", -1.5),
        ("vol", -0.1),
        ("vol", 1.1),
        ("drawdown", -0.1),
        ("drawdown", 1.1),
        ("ma_gap", 2.0),
        ("momentum", -2.0),
    ],
)
def test_out_of_range_inputs_raise(field, value):
    with pytest.raises(ValueError):
        v2.classify_regime_v2(_inputs(**{field: value}))


def test_non_finite_inputs_raise():
    with pytest.raises(ValueError):
        v2.classify_regime_v2(_inputs(trend=float("nan")))


# --- Classification branches -----------------------------------------------------------


def test_high_volatility_direct_matches_v1_trigger():
    result = v2.classify_regime_v2(_inputs(trend=0.9, vol=0.8, momentum=1.0))
    assert result.market_regime == "HIGH_VOLATILITY"
    assert result.risk_level == "HIGH"
    assert result.confidence == 80


def test_high_volatility_escalation_on_drawdown():
    # v1 cannot reach HIGH_VOLATILITY below vol 0.7; v2 escalates when an
    # elevated vol coincides with a severe drawdown (crash with VIX ~30).
    result = v2.classify_regime_v2(_inputs(trend=-0.3, vol=0.6, drawdown=0.7))
    assert result.market_regime == "HIGH_VOLATILITY"
    # (0.6 + 0.7) / 2 = 0.649999… in float; int() truncates like v1 does.
    assert result.confidence == 64


def test_no_escalation_without_severe_drawdown():
    result = v2.classify_regime_v2(_inputs(trend=-0.2, vol=0.6, drawdown=0.3))
    assert result.market_regime != "HIGH_VOLATILITY"


def test_bull_on_strong_composite():
    result = v2.classify_regime_v2(
        _inputs(trend=0.9, vol=0.1, ma_gap=0.8, momentum=0.9)
    )
    # composite = 0.45*0.9 + 0.30*0.8 + 0.25*0.9 = 0.87 → BULL, HIGH risk band
    assert result.market_regime == "BULL"
    assert result.risk_level == "HIGH"
    assert result.confidence == 87


def test_moderate_bull_is_normal_risk():
    result = v2.classify_regime_v2(
        _inputs(trend=0.6, vol=0.2, ma_gap=0.5, momentum=0.4)
    )
    # composite = 0.27 + 0.15 + 0.10 = 0.52 → BULL just above threshold
    assert result.market_regime == "BULL"
    assert result.risk_level == "NORMAL"


def test_bear_on_negative_composite():
    result = v2.classify_regime_v2(
        _inputs(trend=-0.6, vol=0.3, ma_gap=-0.5, momentum=-0.5)
    )
    # composite = -0.27 - 0.15 - 0.125 = -0.545 → BEAR
    assert result.market_regime == "BEAR"
    assert result.risk_level == "HIGH"


def test_drawdown_qualified_bear():
    # Composite only mildly negative, but the deep drawdown qualifies BEAR —
    # this is the v2 answer to slow trailing-return bear recognition.
    result = v2.classify_regime_v2(_inputs(trend=-0.1, vol=0.4, drawdown=0.75))
    assert result.market_regime == "BEAR"
    assert result.confidence == 75  # max(|composite|, drawdown) = 0.75


def test_mild_negative_without_drawdown_is_sideways():
    result = v2.classify_regime_v2(_inputs(trend=-0.1, vol=0.4, drawdown=0.2))
    assert result.market_regime == "SIDEWAYS"
    assert result.risk_level == "LOW"


def test_sideways_on_flat_inputs():
    result = v2.classify_regime_v2(_inputs(vol=0.12))
    assert result.market_regime == "SIDEWAYS"
    assert result.confidence == 88  # (1 - 0 - 0.12) * 100, mirrors v1 scale


def test_reason_includes_factor_breakdown():
    result = v2.classify_regime_v2(_inputs(trend=0.9, vol=0.1, ma_gap=0.8, momentum=0.9))
    assert any("composite" in reason for reason in result.reason)
    assert any("drawdown" in reason for reason in result.reason)


# --- Contract and determinism --------------------------------------------------------------


def test_grid_sweep_stays_within_contract():
    steps = [-1.0, -0.6, -0.2, 0.0, 0.2, 0.6, 1.0]
    unit_steps = [0.0, 0.3, 0.6, 0.8, 1.0]
    for trend in steps:
        for vol in unit_steps:
            for drawdown in unit_steps:
                for momentum in steps:
                    result = v2.classify_regime_v2(
                        _inputs(
                            trend=trend,
                            vol=vol,
                            drawdown=drawdown,
                            ma_gap=trend,
                            momentum=momentum,
                        )
                    )
                    assert result.market_regime in VALID_REGIMES
                    assert result.risk_level in VALID_RISK_LEVELS
                    assert 0 <= result.confidence <= 100


def test_classification_is_deterministic():
    inputs = _inputs(trend=0.4, vol=0.3, drawdown=0.2, ma_gap=0.3, momentum=0.5)
    assert v2.classify_regime_v2(inputs) == v2.classify_regime_v2(inputs)


def test_parameters_exposes_all_thresholds():
    params = v2.parameters()
    assert params["composite_bull_threshold"] == v2.COMPOSITE_BULL_THRESHOLD
    assert params["composite_bear_threshold"] == v2.COMPOSITE_BEAR_THRESHOLD
    assert params["weight_trend"] + params["weight_ma_gap"] + params[
        "weight_momentum"
    ] == pytest.approx(1.0)
