"""QA-012 calibration tests: v1 vs v2 on the deterministic QA-014 fixture.

Two claims are proven here:
  1. The v1 calibration path is untouched by the QA-012 changes — the default
     report keeps the QA-014 ``calibration_report.v1`` schema with no extra
     record fields.
  2. The v2 model measurably improves the weaknesses QA-014 exposed (BULL
     label lag, late BEAR recognition) without flickering, while agreeing
     with v1 where v1 is right (vol spike, steady phases).

The fixture phases (consecutive days from 2024-01-01):
  bars 0-39 bull, 40-69 sideways (flat), 70-99 bear, 100-129 vol spike.
"""

from __future__ import annotations

import json
import socket
from datetime import date, timedelta
from pathlib import Path

import pytest

from research import calibration_harness as ch
from tools import run_calibration

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "calibration_history.csv"
FIXED_GENERATED_AT = "2026-06-11T00:00:00+00:00"


def _fixture_day(d: int) -> str:
    return (date(2024, 1, 1) + timedelta(days=d)).isoformat()


def _report(model_version: str) -> dict:
    return ch.build_calibration_report(
        ch.load_history_csv(FIXTURE),
        source_label="fixture",
        generated_at=FIXED_GENERATED_AT,
        model_version=model_version,
    )


def _records(model_version: str) -> list[dict]:
    return ch.run_rolling_classification(
        ch.load_history_csv(FIXTURE), model_version=model_version
    )


def _dates_with_regime(records: list[dict], regime: str) -> list[str]:
    return [r["date"] for r in records if r["market_regime"] == regime]


# --- v1 path unchanged (QA-014 not weakened) -------------------------------------------


def test_default_report_is_still_v1_schema():
    report = _report("v1")
    default_report = ch.build_calibration_report(
        ch.load_history_csv(FIXTURE),
        source_label="fixture",
        generated_at=FIXED_GENERATED_AT,
    )
    assert default_report["schema_version"] == "calibration_report.v1"
    assert json.dumps(default_report, sort_keys=True) == json.dumps(
        report, sort_keys=True
    )


def test_v1_records_carry_no_factor_fields():
    for record in _records("v1"):
        assert "factors" not in record


def test_invalid_model_version_fails_closed():
    history = ch.load_history_csv(FIXTURE)
    with pytest.raises(ch.CalibrationDataError):
        ch.run_rolling_classification(history, model_version="v3")


# --- v2 report schema --------------------------------------------------------------------


def test_v2_report_schema():
    report = _report("v2")
    assert report["schema_version"] == "calibration_report.v2"
    assert report["research_only"] is True
    assert report["not_for_live_trading"] is True
    assert report["data_is_real"] is False
    assert report["parameters"]["model_version"] == "v2"
    assert "composite_bull_threshold" in report["parameters"]
    for record in report["records"]:
        assert set(record["factors"]) == {
            "drawdown_score",
            "ma_gap_score",
            "momentum_score",
            "composite_score",
        }


def test_v2_calibration_is_deterministic():
    assert json.dumps(_report("v2"), sort_keys=True) == json.dumps(
        _report("v2"), sort_keys=True
    )


def test_v2_runs_with_network_disabled(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("v2 harness attempted network access")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    assert _report("v2")["calibration"]["records_classified"] > 0


# --- Behavioral comparison: v2 fixes v1's boundary lag --------------------------------------


def test_v2_exits_stale_bull_earlier_than_v1():
    # v1 keeps the BULL label ~10 sessions into the flat phase because its
    # only trend input is the trailing 20-session return. v2's short-window
    # factors decay faster, so the stale label ends sooner.
    last_bull_v1 = max(_dates_with_regime(_records("v1"), "BULL"))
    last_bull_v2 = max(_dates_with_regime(_records("v2"), "BULL"))
    assert last_bull_v2 < last_bull_v1
    # Both still agree BULL is correct deep inside the bull phase.
    assert _fixture_day(25) in _dates_with_regime(_records("v2"), "BULL")


def test_v2_recognises_bear_earlier_than_v1():
    first_bear_v1 = min(_dates_with_regime(_records("v1"), "BEAR"))
    first_bear_v2 = min(_dates_with_regime(_records("v2"), "BEAR"))
    assert first_bear_v2 < first_bear_v1
    # And not absurdly early: never before the bear phase actually starts.
    assert first_bear_v2 >= _fixture_day(70)


def test_v2_improves_bull_directional_hit_rate():
    hits_v1 = _report("v1")["calibration"]["directional_hit_rate"]
    hits_v2 = _report("v2")["calibration"]["directional_hit_rate"]
    assert hits_v2["BULL"] > hits_v1["BULL"]
    assert hits_v2["BEAR"] is not None and hits_v2["BEAR"] >= 0.9


def test_v2_does_not_flicker():
    summary = _report("v2")["calibration"]
    # Three phase boundaries in the fixture → a stable model produces a small
    # number of transitions, not boundary chatter.
    assert summary["transition_count"] <= 5
    assert summary["persistence_rate"] >= 0.95


def test_models_agree_on_vol_spike_and_steady_phases():
    records_v1 = {r["date"]: r["market_regime"] for r in _records("v1")}
    records_v2 = {r["date"]: r["market_regime"] for r in _records("v2")}
    # Vol spike phase: VIX 45 dominates in both models.
    for d in range(100, 130):
        assert records_v1[_fixture_day(d)] == "HIGH_VOLATILITY"
        assert records_v2[_fixture_day(d)] == "HIGH_VOLATILITY"
    # Deep inside the bull phase both say BULL; late sideways both SIDEWAYS.
    assert records_v1[_fixture_day(25)] == records_v2[_fixture_day(25)] == "BULL"
    assert records_v1[_fixture_day(65)] == records_v2[_fixture_day(65)] == "SIDEWAYS"


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_model_v2_writes_v2_report(tmp_path, capsys):
    out = tmp_path / "calibration_report_v2.json"
    exit_code = run_calibration.main(
        ["--csv", str(FIXTURE), "--model", "v2", "--out", str(out)]
    )
    assert exit_code == 0
    confirmation = json.loads(capsys.readouterr().out)
    assert confirmation["model_version"] == "v2"
    assert confirmation["schema_version"] == "calibration_report.v2"
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["parameters"]["model_version"] == "v2"
    assert written["research_only"] is True
