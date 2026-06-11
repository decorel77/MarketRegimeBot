"""QA-014 tests: research-only calibration / walk-forward harness.

Proves the harness is deterministic, offline, hermetic (never touches
production artifacts), fail-closed on bad data, and schema-stable.
"""

from __future__ import annotations

import inspect
import json
import socket
from datetime import date, timedelta
from pathlib import Path

import pytest

from research import calibration_harness as ch
from tests.conftest import _system_dir_state
from tools import run_calibration

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "calibration_history.csv"
FIXED_GENERATED_AT = "2026-06-11T00:00:00+00:00"

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "producer",
    "research_only",
    "not_for_live_trading",
    "data_is_real",
    "input_source",
    "generated_at",
    "parameters",
    "history",
    "calibration",
    "walk_forward",
    "records",
}
EXPECTED_SUMMARY_KEYS = {
    "records_classified",
    "first_date",
    "last_date",
    "regime_counts",
    "regime_distribution",
    "mean_confidence_by_regime",
    "transition_count",
    "persistence_rate",
    "forward_horizon",
    "forward_return_by_regime",
    "directional_hit_rate",
}
EXPECTED_RECORD_KEYS = {
    "bar_index",
    "date",
    "trend_score",
    "volatility_score",
    "market_regime",
    "confidence",
    "risk_level",
    "volatility_env",
}
EXPECTED_FOLD_KEYS = {
    "fold",
    "train_start_date",
    "train_end_date",
    "test_start_date",
    "test_end_date",
    "summary",
}


def _fixture_day(d: int) -> str:
    """Fixture dates are consecutive calendar days starting 2024-01-01."""
    return (date(2024, 1, 1) + timedelta(days=d)).isoformat()


def _fixture_report() -> dict:
    return ch.build_calibration_report(
        ch.load_history_csv(FIXTURE),
        source_label="fixture",
        generated_at=FIXED_GENERATED_AT,
    )


def _make_rows(n: int) -> list[dict[str, str]]:
    """Minimal valid synthetic rows for loader/validation tests."""
    return [
        {
            "date": _fixture_day(d),
            "spy_close": f"{100.0 + d:.4f}",
            "qqq_close": f"{300.0 + d:.4f}",
            "vix_close": "18.0",
        }
        for d in range(n)
    ]


# --- Determinism and fixture calibration --------------------------------------------


def test_fixture_calibration_is_deterministic():
    report_a = _fixture_report()
    report_b = _fixture_report()
    assert json.dumps(report_a, sort_keys=True) == json.dumps(report_b, sort_keys=True)


def test_fixture_phases_classify_as_expected():
    records = ch.run_rolling_classification(ch.load_history_csv(FIXTURE))
    by_date = {record["date"]: record for record in records}
    # Mid-bull: full 20-session window inside the +0.5%/day phase.
    assert by_date[_fixture_day(25)]["market_regime"] == "BULL"
    # End of sideways: window fully inside the flat phase.
    assert by_date[_fixture_day(69)]["market_regime"] == "SIDEWAYS"
    assert by_date[_fixture_day(69)]["trend_score"] == 0.0
    # End of bear: window fully inside the -0.5%/day phase.
    assert by_date[_fixture_day(99)]["market_regime"] == "BEAR"
    # Vol spike: VIX 45 maps to volatility_score 1.0 and dominates the trend.
    assert by_date[_fixture_day(129)]["market_regime"] == "HIGH_VOLATILITY"
    assert by_date[_fixture_day(129)]["volatility_env"] == "HIGH_VOL"


def test_directional_hit_rates_on_fixture_are_sane():
    report = _fixture_report()
    hits = report["calibration"]["directional_hit_rate"]
    # BULL labels lag into the flat phase (the trailing return window still
    # holds bull-phase closes) where forward returns are exactly zero, so the
    # fixture's BULL hit rate is a majority, not near-perfect — that label lag
    # is exactly what the calibration is meant to expose. BEAR labels appear
    # only deep inside declining phases, so they must be near-perfect.
    assert hits["BULL"] is not None and hits["BULL"] > 0.55
    assert hits["BEAR"] is not None and hits["BEAR"] > 0.9


# --- Output schema stability ----------------------------------------------------------


def test_report_schema_is_stable():
    report = _fixture_report()
    assert set(report) == EXPECTED_TOP_LEVEL_KEYS
    assert report["schema_version"] == "calibration_report.v1"
    assert report["producer"] == "MarketRegimeBot.research.calibration_harness"
    assert report["research_only"] is True
    assert report["not_for_live_trading"] is True
    assert report["data_is_real"] is False
    assert set(report["calibration"]) == EXPECTED_SUMMARY_KEYS
    assert all(set(r) == EXPECTED_RECORD_KEYS for r in report["records"])
    for fold in report["walk_forward"]["folds"]:
        assert set(fold) == EXPECTED_FOLD_KEYS
        assert set(fold["summary"]) == EXPECTED_SUMMARY_KEYS


# --- No network dependency -------------------------------------------------------------


def test_harness_runs_with_network_disabled(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("harness attempted network access")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    report = _fixture_report()
    assert report["calibration"]["records_classified"] > 0


def test_harness_source_has_no_network_or_broker_imports():
    source = inspect.getsource(ch)
    for banned in ("yfinance", "requests", "urllib", "ib_insync", "socket"):
        assert banned not in source, f"banned dependency in harness source: {banned}"


# --- No production artifact mutation ----------------------------------------------------


def test_full_harness_run_leaves_production_artifacts_untouched(tmp_path):
    before = _system_dir_state()
    report = _fixture_report()
    ch.write_calibration_report(report, tmp_path / "calibration_report.json")
    assert _system_dir_state() == before


def test_write_guard_refuses_production_system_dir():
    report = _fixture_report()
    target = ch.PRODUCTION_SYSTEM_DIR / "calibration_report.json"
    with pytest.raises(ch.CalibrationWriteGuardError):
        ch.write_calibration_report(report, target)
    assert not target.exists()


def test_write_guard_refuses_stripped_research_markers(tmp_path):
    report = _fixture_report()
    report["research_only"] = False
    with pytest.raises(ch.CalibrationWriteGuardError):
        ch.write_calibration_report(report, tmp_path / "report.json")
    report = _fixture_report()
    report["data_is_real"] = True
    with pytest.raises(ch.CalibrationWriteGuardError):
        ch.write_calibration_report(report, tmp_path / "report.json")


# --- Fail-closed on missing/invalid data -------------------------------------------------


def test_missing_csv_fails_closed(tmp_path):
    with pytest.raises(ch.CalibrationDataError):
        ch.load_history_csv(tmp_path / "missing.csv")


def test_csv_missing_column_fails_closed(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("date,spy_close,qqq_close\n2024-01-01,100.0,300.0\n", encoding="utf-8")
    with pytest.raises(ch.CalibrationDataError):
        ch.load_history_csv(bad)


def test_non_numeric_price_fails_closed():
    rows = _make_rows(25)
    rows[3]["spy_close"] = "not-a-price"
    with pytest.raises(ch.CalibrationDataError):
        ch.History.from_rows(rows)


def test_non_positive_price_fails_closed():
    rows = _make_rows(25)
    rows[10]["vix_close"] = "0.0"
    with pytest.raises(ch.CalibrationDataError):
        ch.History.from_rows(rows)


def test_short_history_fails_closed():
    with pytest.raises(ch.CalibrationDataError):
        ch.History.from_rows(_make_rows(ch.MIN_BARS - 1))


def test_non_increasing_dates_fail_closed():
    rows = _make_rows(25)
    rows[5]["date"] = rows[4]["date"]
    with pytest.raises(ch.CalibrationDataError):
        ch.History.from_rows(rows)


def test_bad_date_format_fails_closed():
    rows = _make_rows(25)
    rows[0]["date"] = "01/05/2024"
    with pytest.raises(ch.CalibrationDataError):
        ch.History.from_rows(rows)


def test_json_loader_requires_list_of_rows(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"date": "2024-01-01"}', encoding="utf-8")
    with pytest.raises(ch.CalibrationDataError):
        ch.load_history_json(bad)


def test_walk_forward_too_short_history_fails_closed():
    history = ch.History.from_rows(_make_rows(30))
    with pytest.raises(ch.CalibrationDataError):
        ch.run_walk_forward(history, train_size=40, test_size=20)


# --- Walk-forward structure ---------------------------------------------------------------


def test_walk_forward_folds_tile_sequentially():
    history = ch.load_history_csv(FIXTURE)
    walk_forward = ch.run_walk_forward(history, train_size=40, test_size=20)
    folds = walk_forward["folds"]
    # 130 bars, burn-in 40, test 20 → out-of-sample windows at bars 40..119.
    assert walk_forward["fold_count"] == 4
    assert [fold["fold"] for fold in folds] == [0, 1, 2, 3]
    assert folds[0]["test_start_date"] == _fixture_day(40)
    assert folds[0]["test_end_date"] == _fixture_day(59)
    assert folds[1]["test_start_date"] == _fixture_day(60)
    assert folds[-1]["test_end_date"] == _fixture_day(119)
    assert 0.0 <= walk_forward["max_distribution_drift"] <= 1.0


# --- CLI -----------------------------------------------------------------------------------


def test_cli_runs_on_fixture_and_writes_report(tmp_path, capsys):
    out = tmp_path / "calibration_report.json"
    exit_code = run_calibration.main(["--csv", str(FIXTURE), "--out", str(out)])
    assert exit_code == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["research_only"] is True
    assert written["schema_version"] == "calibration_report.v1"
    confirmation = json.loads(capsys.readouterr().out)
    assert confirmation["written_to"] == str(out.resolve())
    assert confirmation["research_only"] is True


def test_cli_fails_closed_on_missing_file(tmp_path, capsys):
    exit_code = run_calibration.main(["--csv", str(tmp_path / "missing.csv")])
    assert exit_code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "calibration_failed_closed"
