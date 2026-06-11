"""Historical calibration and walk-forward harness for MarketRegimeBot (QA-014).

RESEARCH / REPORTING ONLY.

This module replays the production regime classification across historical
OHLCV-like data (local CSV/JSON files or injected rows) and produces a
calibration report: regime distribution, confidence, persistence, forward
return alignment, and walk-forward fold stability.

Guarantees:
  * It never changes production classifier behavior — it imports the exact
    production scoring and classification functions, so calibration results
    describe the real classifier rather than a research copy that could drift.
  * It performs no live market data downloads and has no broker integration.
    Inputs are local files or injected in-memory rows only.
  * It fails closed: missing or invalid data raises ``CalibrationDataError``
    instead of producing a plausible-but-fake report.
  * It never writes into the production artifact directory ``data/system/``
    (``CalibrationWriteGuardError``), and every report it does write carries
    ``research_only`` / ``not_for_live_trading`` / ``data_is_real=False``
    markers so no consumer can mistake it for a live regime decision.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

# Private production helpers are imported deliberately: the harness must score
# history with byte-identical math to the production reader and classifier.
# Duplicating the formulas here would let research results silently drift away
# from what the bot actually does.
from core.market_data_reader import (
    _RETURN_NORMALISE,
    _RETURN_WINDOW,
    _VIX_HIGH,
    _VIX_LOW,
    _compute_trend_score,
    _compute_volatility_score,
)
from core.regime_classifier import (
    _TREND_BEAR_THRESHOLD,
    _TREND_BULL_THRESHOLD,
    _VOLATILITY_HIGH_THRESHOLD,
    RegimeInput,
    classify_regime,
)
from core.volatility_classifier import classify_volatility

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SYSTEM_DIR = PROJECT_ROOT / "data" / "system"
# Suggested (gitignored) output location for research reports.
RESEARCH_OUTPUT_DIR = PROJECT_ROOT / "data" / "research"

REPORT_SCHEMA_VERSION = "calibration_report.v1"
PRODUCER = "MarketRegimeBot.research.calibration_harness"

REQUIRED_COLUMNS = ("date", "spy_close", "qqq_close", "vix_close")
MIN_BARS = _RETURN_WINDOW + 1  # one full production return window


class CalibrationDataError(ValueError):
    """Fail-closed: raised instead of producing a plausible-but-fake report."""


class CalibrationWriteGuardError(RuntimeError):
    """Raised when a research write would masquerade as a production artifact."""


def _r(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


# --- History container ------------------------------------------------------------


@dataclass(frozen=True)
class History:
    """Validated historical close series for SPY, QQQ and VIX."""

    dates: tuple[str, ...]
    spy_close: tuple[float, ...]
    qqq_close: tuple[float, ...]
    vix_close: tuple[float, ...]

    def validate(self) -> None:
        n = len(self.dates)
        series = {
            "spy_close": self.spy_close,
            "qqq_close": self.qqq_close,
            "vix_close": self.vix_close,
        }
        for name, values in series.items():
            if len(values) != n:
                raise CalibrationDataError(
                    f"{name} has {len(values)} values for {n} dates"
                )
        if n < MIN_BARS:
            raise CalibrationDataError(
                f"history too short: {n} bars, need at least {MIN_BARS} "
                f"(one full {_RETURN_WINDOW}-session return window)"
            )
        previous: date | None = None
        for value in self.dates:
            try:
                parsed = date.fromisoformat(str(value))
            except ValueError as exc:
                raise CalibrationDataError(
                    f"dates must be ISO-8601 (YYYY-MM-DD), got: {value!r}"
                ) from exc
            if previous is not None and parsed <= previous:
                raise CalibrationDataError(
                    f"dates must be strictly increasing, got {value!r} "
                    f"after {previous.isoformat()!r}"
                )
            previous = parsed
        for name, values in series.items():
            for value in values:
                if not math.isfinite(value) or value <= 0.0:
                    raise CalibrationDataError(
                        f"{name} contains a non-finite or non-positive price: {value!r}"
                    )

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> "History":
        """Build a validated History from row mappings (CSV rows, JSON objects,
        or injected test data). Fails closed on any malformed row."""
        dates: list[str] = []
        spy: list[float] = []
        qqq: list[float] = []
        vix: list[float] = []
        for line_no, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise CalibrationDataError(f"row {line_no} is not a mapping: {row!r}")
            missing = [
                column
                for column in REQUIRED_COLUMNS
                if column not in row or row[column] in (None, "")
            ]
            if missing:
                raise CalibrationDataError(
                    f"row {line_no} is missing required columns: {missing}"
                )
            try:
                spy.append(float(row["spy_close"]))
                qqq.append(float(row["qqq_close"]))
                vix.append(float(row["vix_close"]))
            except (TypeError, ValueError) as exc:
                raise CalibrationDataError(
                    f"row {line_no} has a non-numeric price value"
                ) from exc
            dates.append(str(row["date"]))
        history = cls(
            dates=tuple(dates),
            spy_close=tuple(spy),
            qqq_close=tuple(qqq),
            vix_close=tuple(vix),
        )
        history.validate()
        return history


# --- Loaders (local files only — never the network) --------------------------------


def load_history_csv(path: Path | str) -> History:
    """Load history from a local CSV with columns date,spy_close,qqq_close,vix_close."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CalibrationDataError(f"{path}: empty CSV, no header row")
            missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
            if missing:
                raise CalibrationDataError(f"{path}: missing CSV columns: {missing}")
            rows = list(reader)
    except OSError as exc:
        raise CalibrationDataError(f"cannot read history CSV {path}: {exc}") from exc
    return History.from_rows(rows)


def load_history_json(path: Path | str) -> History:
    """Load history from a local JSON file holding a list of row objects."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CalibrationDataError(f"cannot read history JSON {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CalibrationDataError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise CalibrationDataError(
            f"{path}: expected a JSON list of row objects, got {type(payload).__name__}"
        )
    return History.from_rows(payload)


# --- Rolling classification ---------------------------------------------------------


def run_rolling_classification(history: History) -> list[dict[str, Any]]:
    """Classify every bar that has a full production lookback window behind it.

    Each bar ``i >= _RETURN_WINDOW`` is scored from the trailing
    ``_RETURN_WINDOW + 1`` closes — exactly the window the production reader
    uses — then classified with the production regime and volatility
    classifiers.
    """
    history.validate()
    records: list[dict[str, Any]] = []
    for i in range(_RETURN_WINDOW, len(history.dates)):
        start = i - _RETURN_WINDOW
        trend_score = _compute_trend_score(
            {
                "SPY": list(history.spy_close[start : i + 1]),
                "QQQ": list(history.qqq_close[start : i + 1]),
            }
        )
        if trend_score is None:
            raise CalibrationDataError(f"could not compute trend score at bar {i}")
        volatility_score = _compute_volatility_score(history.vix_close[i])
        inputs = RegimeInput(
            trend_score=trend_score, volatility_score=volatility_score
        )
        result = classify_regime(inputs)
        vol_result = classify_volatility(volatility_score)
        records.append(
            {
                "bar_index": i,
                "date": history.dates[i],
                "trend_score": trend_score,
                "volatility_score": volatility_score,
                "market_regime": result.market_regime,
                "confidence": result.confidence,
                "risk_level": result.risk_level,
                "volatility_env": vol_result.volatility_env,
            }
        )
    return records


# --- Calibration summary ------------------------------------------------------------


def summarize_records(
    records: list[dict[str, Any]],
    history: History,
    *,
    forward_horizon: int = 5,
) -> dict[str, Any]:
    """Summarize classified records: distribution, persistence, and how regime
    labels align with realized forward SPY returns over ``forward_horizon``
    sessions. Bars too close to the end of history are excluded from the
    forward-return metrics (never extrapolated)."""
    if not records:
        raise CalibrationDataError("no classified records to summarize")
    if forward_horizon < 1:
        raise CalibrationDataError("forward_horizon must be >= 1")

    counts: dict[str, int] = {}
    confidence_sums: dict[str, int] = {}
    forward_returns: dict[str, list[float]] = {}
    transitions = 0
    previous_regime: str | None = None
    spy = history.spy_close

    for record in records:
        regime = record["market_regime"]
        counts[regime] = counts.get(regime, 0) + 1
        confidence_sums[regime] = confidence_sums.get(regime, 0) + record["confidence"]
        if previous_regime is not None and regime != previous_regime:
            transitions += 1
        previous_regime = regime
        i = record["bar_index"]
        j = i + forward_horizon
        if j < len(spy):
            forward_returns.setdefault(regime, []).append((spy[j] - spy[i]) / spy[i])

    n = len(records)
    persistence_rate = _r(1.0 - transitions / (n - 1)) if n > 1 else None
    forward_stats = {
        regime: {
            "count": len(returns),
            "mean": _r(sum(returns) / len(returns)),
            "min": _r(min(returns)),
            "max": _r(max(returns)),
        }
        for regime, returns in sorted(forward_returns.items())
    }
    # Directional sanity: BULL labels should precede positive forward returns,
    # BEAR labels negative ones.
    directional_hit_rate: dict[str, float | None] = {}
    for regime, is_hit in (("BULL", lambda r: r > 0), ("BEAR", lambda r: r < 0)):
        returns = forward_returns.get(regime)
        directional_hit_rate[regime] = (
            _r(sum(1 for r in returns if is_hit(r)) / len(returns)) if returns else None
        )

    return {
        "records_classified": n,
        "first_date": records[0]["date"],
        "last_date": records[-1]["date"],
        "regime_counts": dict(sorted(counts.items())),
        "regime_distribution": {k: _r(v / n) for k, v in sorted(counts.items())},
        "mean_confidence_by_regime": {
            k: round(confidence_sums[k] / counts[k], 2) for k in sorted(counts)
        },
        "transition_count": transitions,
        "persistence_rate": persistence_rate,
        "forward_horizon": forward_horizon,
        "forward_return_by_regime": forward_stats,
        "directional_hit_rate": directional_hit_rate,
    }


# --- Walk-forward evaluation ---------------------------------------------------------


def _walk_forward_from_records(
    records: list[dict[str, Any]],
    history: History,
    *,
    train_size: int,
    test_size: int,
    forward_horizon: int,
) -> dict[str, Any]:
    if train_size < _RETURN_WINDOW:
        raise CalibrationDataError(
            f"train_size must be >= {_RETURN_WINDOW} so every test bar has a "
            "full production lookback window"
        )
    if test_size < 1:
        raise CalibrationDataError("test_size must be >= 1")

    by_index = {record["bar_index"]: record for record in records}
    n_bars = len(history.dates)
    folds: list[dict[str, Any]] = []
    start = train_size
    while start + test_size <= n_bars:
        test_records = [by_index[i] for i in range(start, start + test_size)]
        folds.append(
            {
                "fold": len(folds),
                "train_start_date": history.dates[start - train_size],
                "train_end_date": history.dates[start - 1],
                "test_start_date": history.dates[start],
                "test_end_date": history.dates[start + test_size - 1],
                "summary": summarize_records(
                    test_records, history, forward_horizon=forward_horizon
                ),
            }
        )
        start += test_size
    if not folds:
        raise CalibrationDataError(
            f"history too short for walk-forward: need at least "
            f"{train_size + test_size} bars, got {n_bars}"
        )

    # Distribution drift between consecutive out-of-sample folds (total
    # variation distance): high drift means the classifier paints very
    # different regime pictures from one period to the next.
    drifts: list[float] = []
    for left, right in zip(folds, folds[1:]):
        dist_left = left["summary"]["regime_distribution"]
        dist_right = right["summary"]["regime_distribution"]
        regimes = set(dist_left) | set(dist_right)
        drifts.append(
            _r(
                0.5
                * sum(
                    abs(dist_left.get(k, 0.0) - dist_right.get(k, 0.0))
                    for k in regimes
                )
            )
        )
    persistence_rates = [
        fold["summary"]["persistence_rate"]
        for fold in folds
        if fold["summary"]["persistence_rate"] is not None
    ]
    return {
        "fold_count": len(folds),
        "train_size": train_size,
        "test_size": test_size,
        "folds": folds,
        "max_distribution_drift": max(drifts) if drifts else 0.0,
        "mean_persistence_rate": (
            _r(sum(persistence_rates) / len(persistence_rates))
            if persistence_rates
            else None
        ),
    }


def run_walk_forward(
    history: History,
    *,
    train_size: int = 40,
    test_size: int = 20,
    forward_horizon: int = 5,
) -> dict[str, Any]:
    """Walk-forward evaluation: sequential, non-overlapping out-of-sample test
    windows of ``test_size`` bars, each preceded by ``train_size`` bars of
    burn-in/lookback context. The classifier has no fitted parameters, so the
    train window provides lookback history only — every test window is scored
    out-of-sample with unmodified production behavior."""
    records = run_rolling_classification(history)
    return _walk_forward_from_records(
        records,
        history,
        train_size=train_size,
        test_size=test_size,
        forward_horizon=forward_horizon,
    )


# --- Full report ----------------------------------------------------------------------


def build_calibration_report(
    history: History,
    *,
    source_label: str,
    forward_horizon: int = 5,
    train_size: int = 40,
    test_size: int = 20,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the full research-only calibration report.

    ``generated_at`` is injectable (deterministic tests); defaults to the
    current UTC time. Everything else in the report is a pure function of the
    input history and parameters."""
    history.validate()
    records = run_rolling_classification(history)
    calibration = summarize_records(records, history, forward_horizon=forward_horizon)
    walk_forward = _walk_forward_from_records(
        records,
        history,
        train_size=train_size,
        test_size=test_size,
        forward_horizon=forward_horizon,
    )
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "producer": PRODUCER,
        "research_only": True,
        "not_for_live_trading": True,
        "data_is_real": False,
        "input_source": source_label,
        "generated_at": generated_at,
        "parameters": {
            "forward_horizon": forward_horizon,
            "train_size": train_size,
            "test_size": test_size,
            "return_window": _RETURN_WINDOW,
            "return_normalise": _RETURN_NORMALISE,
            "vix_low": _VIX_LOW,
            "vix_high": _VIX_HIGH,
            "volatility_high_threshold": _VOLATILITY_HIGH_THRESHOLD,
            "trend_bull_threshold": _TREND_BULL_THRESHOLD,
            "trend_bear_threshold": _TREND_BEAR_THRESHOLD,
        },
        "history": {
            "bars": len(history.dates),
            "start_date": history.dates[0],
            "end_date": history.dates[-1],
            "first_classified_date": records[0]["date"],
        },
        "calibration": calibration,
        "walk_forward": walk_forward,
        "records": records,
    }


def write_calibration_report(report: Mapping[str, Any], path: Path | str) -> Path:
    """Write a calibration report as JSON, guarded against production overlap.

    Refuses to write into ``data/system/`` (production artifacts) and refuses
    any report whose research-only markers have been stripped."""
    if (
        report.get("research_only") is not True
        or report.get("not_for_live_trading") is not True
    ):
        raise CalibrationWriteGuardError(
            "refusing to write a report without research-only markers"
        )
    if report.get("data_is_real") is not False:
        raise CalibrationWriteGuardError(
            "research reports must carry data_is_real=False"
        )
    resolved = Path(path).resolve()
    system_dir = PRODUCTION_SYSTEM_DIR.resolve()
    if resolved == system_dir or system_dir in resolved.parents:
        raise CalibrationWriteGuardError(
            "refusing to write research output into the production artifact "
            "directory data/system/"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return resolved
