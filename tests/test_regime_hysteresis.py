"""QA-013 unit tests: regime hysteresis / dwell-time filter (pure, stateful).

Covers: config fail-closed validation, dwell confirmation semantics, noise
immunity, fast HIGH_VOLATILITY entry vs slow exit, immediate fail-closed to
UNKNOWN, recovery, determinism, and output record schema stability.
"""

from __future__ import annotations

import pytest

from core.regime_hysteresis import (
    HysteresisConfig,
    RegimeHysteresisFilter,
    apply_hysteresis,
)

EXPECTED_RECORD_KEYS = {
    "published_regime",
    "published_confidence",
    "raw_regime",
    "raw_confidence",
    "pending_regime",
    "pending_count",
    "switched",
    "fail_closed",
    "reason",
}


def _seeded_filter(regime: str = "BULL", confidence: int = 90) -> RegimeHysteresisFilter:
    """Fresh filter seeded out of warm-up into ``regime``."""
    regime_filter = RegimeHysteresisFilter()
    decision = regime_filter.observe(regime, confidence)
    assert decision["published_regime"] == regime
    return regime_filter


# --- Config validation (fail-closed) ---------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_dwell": 0},
        {"min_dwell": -1},
        {"min_dwell": 2.5},
        {"min_dwell": True},
        {"high_vol_entry_dwell": 0},
        {"high_vol_exit_dwell": 0},
        {"switch_confidence_min": -1},
        {"switch_confidence_min": 101},
        {"high_vol_entry_confidence_min": 1000},
        {"high_vol_exit_confidence_min": "60"},
    ],
)
def test_invalid_config_fails_closed(kwargs):
    with pytest.raises(ValueError):
        RegimeHysteresisFilter(HysteresisConfig(**kwargs))


# --- Warm-up and seeding -----------------------------------------------------------------


def test_filter_starts_unknown_and_seeds_on_first_qualified_observation():
    regime_filter = RegimeHysteresisFilter()
    low = regime_filter.observe("SIDEWAYS", 30)  # below switch_confidence_min
    assert low["published_regime"] == "UNKNOWN"
    seeded = regime_filter.observe("BULL", 90)
    assert seeded["published_regime"] == "BULL"
    assert seeded["switched"] is True


# --- Noise immunity ------------------------------------------------------------------------


def test_no_flip_flop_on_noisy_alternating_inputs():
    regime_filter = _seeded_filter("BULL")
    for _ in range(10):
        a = regime_filter.observe("SIDEWAYS", 90)
        b = regime_filter.observe("BULL", 90)
        assert a["published_regime"] == "BULL"
        assert b["published_regime"] == "BULL"
        assert not a["switched"] and not b["switched"]


def test_alternating_candidates_never_accumulate():
    regime_filter = _seeded_filter("BULL")
    # Two different challengers alternating: each reset clears the other.
    for _ in range(10):
        assert regime_filter.observe("SIDEWAYS", 95)["published_regime"] == "BULL"
        assert regime_filter.observe("BEAR", 95)["published_regime"] == "BULL"


# --- Dwell confirmation ----------------------------------------------------------------------


def test_sustained_strong_signal_switches_in_exactly_min_dwell():
    regime_filter = _seeded_filter("BULL")
    decisions = [regime_filter.observe("SIDEWAYS", 80) for _ in range(3)]
    assert [d["published_regime"] for d in decisions] == ["BULL", "BULL", "SIDEWAYS"]
    assert decisions[2]["switched"] is True
    assert decisions[0]["pending_regime"] == "SIDEWAYS"
    assert decisions[0]["pending_count"] == 1


def test_sustained_low_confidence_signal_never_switches():
    regime_filter = _seeded_filter("BULL")
    for _ in range(10):
        decision = regime_filter.observe("SIDEWAYS", 50)
        assert decision["published_regime"] == "BULL"
        assert decision["pending_count"] == 0


def test_low_confidence_blip_pauses_but_does_not_reset_progress():
    regime_filter = _seeded_filter("BULL")
    assert regime_filter.observe("SIDEWAYS", 80)["pending_count"] == 1
    paused = regime_filter.observe("SIDEWAYS", 40)  # same candidate, low conf
    assert paused["pending_count"] == 1
    assert paused["published_regime"] == "BULL"
    assert regime_filter.observe("SIDEWAYS", 80)["pending_count"] == 2
    final = regime_filter.observe("SIDEWAYS", 80)
    assert final["published_regime"] == "SIDEWAYS"
    assert final["switched"] is True


def test_agreeing_observation_clears_pending_challenger():
    regime_filter = _seeded_filter("BULL")
    regime_filter.observe("SIDEWAYS", 80)
    regime_filter.observe("SIDEWAYS", 80)  # 2 of 3 confirmations
    agree = regime_filter.observe("BULL", 85)
    assert agree["pending_regime"] is None
    assert agree["pending_count"] == 0
    # Challenger must start over.
    assert regime_filter.observe("SIDEWAYS", 80)["pending_count"] == 1


# --- HIGH_VOLATILITY asymmetry ------------------------------------------------------------------


def test_high_volatility_entry_is_immediate_at_high_confidence():
    regime_filter = _seeded_filter("BULL")
    decision = regime_filter.observe("HIGH_VOLATILITY", 75)
    assert decision["published_regime"] == "HIGH_VOLATILITY"
    assert decision["switched"] is True


def test_high_volatility_entry_requires_strong_confidence():
    regime_filter = _seeded_filter("BULL")
    decision = regime_filter.observe("HIGH_VOLATILITY", 65)  # below 70 bar
    assert decision["published_regime"] == "BULL"


def test_high_volatility_exit_is_slow():
    regime_filter = _seeded_filter("HIGH_VOLATILITY", 90)
    decisions = [regime_filter.observe("SIDEWAYS", 80) for _ in range(5)]
    assert [d["published_regime"] for d in decisions[:4]] == ["HIGH_VOLATILITY"] * 4
    assert decisions[4]["published_regime"] == "SIDEWAYS"


def test_high_volatility_blip_restarts_exit_clock():
    regime_filter = _seeded_filter("HIGH_VOLATILITY", 90)
    for _ in range(4):
        regime_filter.observe("SIDEWAYS", 80)
    regime_filter.observe("HIGH_VOLATILITY", 90)  # raw agrees again → reset
    for _ in range(4):
        assert (
            regime_filter.observe("SIDEWAYS", 80)["published_regime"]
            == "HIGH_VOLATILITY"
        )
    assert regime_filter.observe("SIDEWAYS", 80)["published_regime"] == "SIDEWAYS"


# --- Fail-closed behavior ---------------------------------------------------------------------


def test_raw_unknown_adopts_immediately():
    regime_filter = _seeded_filter("BULL")
    decision = regime_filter.observe("UNKNOWN", 0)
    assert decision["published_regime"] == "UNKNOWN"
    assert decision["published_confidence"] == 0
    assert decision["fail_closed"] is True
    assert decision["switched"] is True


def test_unreal_data_fails_closed_immediately():
    regime_filter = _seeded_filter("BULL")
    decision = regime_filter.observe("BULL", 95, metadata={"data_is_real": False})
    assert decision["published_regime"] == "UNKNOWN"
    assert decision["fail_closed"] is True


def test_stale_data_fails_closed_immediately():
    regime_filter = _seeded_filter("BULL")
    decision = regime_filter.observe("BULL", 95, metadata={"is_fresh": False})
    assert decision["published_regime"] == "UNKNOWN"


def test_non_boolean_metadata_flags_fail_closed():
    regime_filter = _seeded_filter("BULL")
    # Truthy-but-not-True must not pass a safety gate.
    decision = regime_filter.observe("BULL", 95, metadata={"data_is_real": 1})
    assert decision["published_regime"] == "UNKNOWN"
    assert decision["fail_closed"] is True


def test_valid_metadata_flags_pass():
    regime_filter = _seeded_filter("BULL")
    decision = regime_filter.observe(
        "BULL", 95, metadata={"data_is_real": True, "is_fresh": True}
    )
    assert decision["published_regime"] == "BULL"
    assert decision["fail_closed"] is False


def test_invalid_regime_or_confidence_fails_closed():
    regime_filter = _seeded_filter("BULL")
    assert regime_filter.observe("BANANAS", 90)["published_regime"] == "UNKNOWN"
    regime_filter = _seeded_filter("BULL")
    assert regime_filter.observe("BULL", 150)["published_regime"] == "UNKNOWN"
    regime_filter = _seeded_filter("BULL")
    assert regime_filter.observe("BULL", True)["published_regime"] == "UNKNOWN"


def test_recovery_after_fail_closed_takes_one_qualified_observation():
    regime_filter = _seeded_filter("BULL")
    regime_filter.observe("UNKNOWN", 0)
    recovered = regime_filter.observe("SIDEWAYS", 80)
    assert recovered["published_regime"] == "SIDEWAYS"
    assert recovered["switched"] is True


# --- Determinism and schema ----------------------------------------------------------------------


def test_apply_hysteresis_is_deterministic_and_matches_stepwise():
    observations = (
        [{"market_regime": "BULL", "confidence": 90}] * 3
        + [{"market_regime": "SIDEWAYS", "confidence": 80}] * 4
        + [{"market_regime": "UNKNOWN", "confidence": 0}]
        + [{"market_regime": "BEAR", "confidence": 70}] * 2
    )
    first = apply_hysteresis(observations)
    second = apply_hysteresis(observations)
    assert first == second
    regime_filter = RegimeHysteresisFilter()
    stepwise = [
        regime_filter.observe(o["market_regime"], o["confidence"])
        for o in observations
    ]
    assert first == stepwise


def test_decision_record_schema_is_stable():
    regime_filter = RegimeHysteresisFilter()
    decisions = [
        regime_filter.observe("BULL", 90),
        regime_filter.observe("SIDEWAYS", 80),
        regime_filter.observe("UNKNOWN", 0),
    ]
    for decision in decisions:
        assert set(decision) == EXPECTED_RECORD_KEYS
