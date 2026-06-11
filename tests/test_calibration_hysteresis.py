"""QA-013 calibration tests: hysteresis filter inside the QA-014 harness.

Proves three things:
  1. Default harness output (no hysteresis) is unchanged for v1 and v2 —
     QA-014/QA-012 behavior is not weakened.
  2. On a deterministic noisy series that makes the raw classifier flip every
     bar, the filter collapses the flip-flopping to a single transition while
     never delaying the HIGH_VOLATILITY entry.
  3. On the clean QA-014 fixture the filter keeps the same three regime
     phases, with the documented dwell lag as the only difference.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.regime_hysteresis import HysteresisConfig
from research import calibration_harness as ch
from tools import run_calibration

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "calibration_history.csv"
FIXED_GENERATED_AT = "2026-06-11T00:00:00+00:00"

EXPECTED_HYSTERESIS_RECORD_KEYS = {
    "raw_regime",
    "raw_confidence",
    "pending_regime",
    "pending_count",
    "switched",
    "fail_closed",
}


def _fixture_day(d: int) -> str:
    return (date(2024, 1, 1) + timedelta(days=d)).isoformat()


def _report(model_version: str = "v1", hysteresis: bool = False) -> dict:
    return ch.build_calibration_report(
        ch.load_history_csv(FIXTURE),
        source_label="fixture",
        generated_at=FIXED_GENERATED_AT,
        model_version=model_version,
        hysteresis_config=HysteresisConfig() if hysteresis else None,
    )


def _noisy_history() -> ch.History:
    """80 bars of flat prices with VIX oscillating across the 0.7 vol
    threshold (31 ↔ 34) — the raw classifier flips SIDEWAYS/HIGH_VOLATILITY
    every single bar."""
    rows = [
        {
            "date": _fixture_day(d),
            "spy_close": "100.0",
            "qqq_close": "300.0",
            "vix_close": "31.0" if d % 2 == 0 else "34.0",
        }
        for d in range(80)
    ]
    return ch.History.from_rows(rows)


# --- Default behavior unchanged (QA-012/QA-014 not weakened) ------------------------------


@pytest.mark.parametrize("model_version", ["v1", "v2"])
def test_default_report_identical_without_hysteresis_argument(model_version):
    explicit_none = _report(model_version, hysteresis=False)
    omitted = ch.build_calibration_report(
        ch.load_history_csv(FIXTURE),
        source_label="fixture",
        generated_at=FIXED_GENERATED_AT,
        model_version=model_version,
    )
    assert json.dumps(explicit_none, sort_keys=True) == json.dumps(
        omitted, sort_keys=True
    )
    assert "hysteresis" not in explicit_none["parameters"]
    for record in explicit_none["records"]:
        assert "hysteresis" not in record


def test_invalid_hysteresis_config_fails_closed():
    history = ch.load_history_csv(FIXTURE)
    with pytest.raises(ch.CalibrationDataError):
        ch.build_calibration_report(
            history,
            source_label="fixture",
            hysteresis_config={"min_dwell": 3},  # plain dict is rejected
        )


# --- Noisy series: flip-flop collapse --------------------------------------------------------


def test_hysteresis_collapses_flip_flopping_on_noisy_series():
    history = _noisy_history()
    raw = ch.build_calibration_report(
        history, source_label="noisy", generated_at=FIXED_GENERATED_AT
    )
    smoothed = ch.build_calibration_report(
        history,
        source_label="noisy",
        generated_at=FIXED_GENERATED_AT,
        hysteresis_config=HysteresisConfig(),
    )
    # Raw classifier flips every bar: 59 transitions across 60 records.
    assert raw["calibration"]["transition_count"] >= 50
    # The filter enters HIGH_VOLATILITY once and holds: warm-up UNKNOWN →
    # HIGH_VOLATILITY is the only transition.
    assert smoothed["calibration"]["transition_count"] == 1
    assert smoothed["calibration"]["persistence_rate"] >= 0.98
    regimes = {r["market_regime"] for r in smoothed["records"]}
    assert regimes == {"UNKNOWN", "HIGH_VOLATILITY"}


def test_high_volatility_entry_not_delayed_on_noisy_series():
    smoothed_records = ch.apply_hysteresis_to_records(
        ch.run_rolling_classification(_noisy_history()), HysteresisConfig()
    )
    # First raw HIGH_VOLATILITY observation must be published the same bar —
    # smoothing never delays the risk-off signal.
    first_raw_high_vol = next(
        r for r in smoothed_records if r["hysteresis"]["raw_regime"] == "HIGH_VOLATILITY"
    )
    assert first_raw_high_vol["market_regime"] == "HIGH_VOLATILITY"
    assert first_raw_high_vol["hysteresis"]["switched"] is True


# --- Clean fixture: same phases, documented dwell lag only -----------------------------------


def test_hysteresis_on_clean_fixture_keeps_three_transitions():
    raw = _report("v1", hysteresis=False)
    smoothed = _report("v1", hysteresis=True)
    assert raw["calibration"]["transition_count"] == 3
    assert smoothed["calibration"]["transition_count"] == 3
    by_date = {r["date"]: r["market_regime"] for r in smoothed["records"]}
    # Deep inside each phase the published regime matches the raw one.
    assert by_date[_fixture_day(25)] == "BULL"
    assert by_date[_fixture_day(65)] == "SIDEWAYS"
    assert by_date[_fixture_day(95)] == "BEAR"
    assert by_date[_fixture_day(110)] == "HIGH_VOLATILITY"


def test_hysteresis_delays_normal_switches_but_not_risk_off():
    raw_records = ch.run_rolling_classification(ch.load_history_csv(FIXTURE))
    smoothed_records = ch.apply_hysteresis_to_records(raw_records, HysteresisConfig())

    def first_date(records, regime):
        return min(r["date"] for r in records if r["market_regime"] == regime)

    # BEAR (a normal switch) is published later than the raw classifier saw
    # it — that is the dwell cost, bounded by the qualification+dwell window.
    assert first_date(smoothed_records, "BEAR") > first_date(raw_records, "BEAR")
    assert first_date(smoothed_records, "BEAR") <= _fixture_day(90)
    # HIGH_VOLATILITY (risk-off) is published the same day raw saw it.
    assert first_date(smoothed_records, "HIGH_VOLATILITY") == first_date(
        raw_records, "HIGH_VOLATILITY"
    )


def test_hysteresis_records_and_parameters_schema():
    report = _report("v1", hysteresis=True)
    assert report["parameters"]["hysteresis"] == HysteresisConfig().to_dict()
    base_keys = {
        "bar_index",
        "date",
        "trend_score",
        "volatility_score",
        "market_regime",
        "confidence",
        "risk_level",
        "volatility_env",
        "hysteresis",
    }
    for record in report["records"]:
        assert set(record) == base_keys
        assert set(record["hysteresis"]) == EXPECTED_HYSTERESIS_RECORD_KEYS


def test_hysteresis_composes_with_model_v2():
    report = _report("v2", hysteresis=True)
    assert report["schema_version"] == "calibration_report.v2"
    assert report["parameters"]["model_version"] == "v2"
    assert report["parameters"]["hysteresis"] == HysteresisConfig().to_dict()
    assert report["calibration"]["transition_count"] == 3
    for record in report["records"]:
        assert "factors" in record
        assert "hysteresis" in record


def test_hysteresis_report_is_deterministic():
    assert json.dumps(_report("v1", hysteresis=True), sort_keys=True) == json.dumps(
        _report("v1", hysteresis=True), sort_keys=True
    )


def test_walk_forward_with_hysteresis_still_tiles():
    walk_forward = ch.run_walk_forward(
        ch.load_history_csv(FIXTURE),
        train_size=40,
        test_size=20,
        hysteresis_config=HysteresisConfig(),
    )
    assert walk_forward["fold_count"] == 4
    assert walk_forward["folds"][0]["test_start_date"] == _fixture_day(40)


# --- CLI -------------------------------------------------------------------------------------


def test_cli_hysteresis_flag(tmp_path, capsys):
    out = tmp_path / "calibration_report_hyst.json"
    exit_code = run_calibration.main(
        ["--csv", str(FIXTURE), "--hysteresis", "--out", str(out)]
    )
    assert exit_code == 0
    confirmation = json.loads(capsys.readouterr().out)
    assert confirmation["hysteresis"] is True
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["parameters"]["hysteresis"] == HysteresisConfig().to_dict()
    assert written["research_only"] is True
