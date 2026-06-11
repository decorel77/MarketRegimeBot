# Calibration / Walk-Forward Harness (QA-014)

**RESEARCH AND REPORTING ONLY.** This harness is never used for live trading.
It has no broker integration, makes no network calls, reads no scheduler or
live-trading state, and does not change production classifier behavior in any
way. Its only job is to describe how the existing MarketRegimeBot classifier
behaves on historical data.

## What it does

`research/calibration_harness.py` replays the **exact production scoring and
classification math** (imported from `core/market_data_reader.py`,
`core/regime_classifier.py`, and `core/volatility_classifier.py` — never
copied) across a historical close-price series:

1. **Rolling classification** — every bar with a full 20-session lookback
   window behind it is scored (trend from SPY+QQQ 20-session returns, volatility
   from the VIX close) and classified, exactly as the production cycle would
   have classified it on that day.
2. **Calibration summary** — regime distribution, mean confidence per regime,
   regime persistence, and how regime labels align with *realized forward SPY
   returns* (does BULL actually precede positive returns?).
3. **Walk-forward evaluation** — sequential, non-overlapping out-of-sample test
   windows, each preceded by a burn-in/lookback window. The classifier has no
   fitted parameters, so "train" provides lookback context only; the metric of
   interest is **stability**: does the regime picture drift wildly between
   adjacent out-of-sample periods?

## Input data

Local files or injected rows only — the harness never downloads anything.

CSV (header required):

```csv
date,spy_close,qqq_close,vix_close
2024-01-01,100.0000,300.0000,14.0
```

JSON: a list of row objects with the same four keys. In code you can also
build `History.from_rows([...])` directly with injected data.

Validation is fail-closed: missing files, missing columns, non-numeric or
non-positive prices, non-ISO or non-increasing dates, or fewer than 21 bars
raise `CalibrationDataError` instead of producing a plausible-but-fake report.

## How to run

From the MarketRegimeBot repo root, using the repo-local venv only:

```powershell
# Print the full report to stdout
.\.venv\Scripts\python.exe -m tools.run_calibration --csv tests\fixtures\calibration_history.csv

# Write the report to the (gitignored) research output folder
.\.venv\Scripts\python.exe -m tools.run_calibration --csv path\to\history.csv --out data\research\calibration_report.json

# Options
#   --forward-horizon N   sessions ahead for forward-return alignment (default 5)
#   --train-size N        burn-in/lookback bars per fold (default 40, min 20)
#   --test-size N         out-of-sample bars per fold (default 20)
#   --model v1|v2         model to evaluate (default v1 = production; v2 is the
#                         QA-012 research model, see docs/regime_model_v2.md)
#   --hysteresis          apply the QA-013 dwell-time filter (default config,
#                         default off; see docs/regime_hysteresis.md)
```

Model selection (QA-012): `--model v1` (default) replays the production
classifier and emits the stable `calibration_report.v1` schema. `--model v2`
evaluates the research-stage multi-factor model under
`calibration_report.v2` — identical top-level shape, but each record gains a
`factors` object (`drawdown_score`, `ma_gap_score`, `momentum_score`,
`composite_score`) and `parameters` gains the v2 thresholds.

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

## What the outputs mean

Top-level report (`schema_version: calibration_report.v1`):

| Key | Meaning |
| --- | --- |
| `research_only`, `not_for_live_trading` | Always `true`. The write guard refuses to persist a report without them. |
| `data_is_real` | Always `false` — historical/fixture input, never a live regime decision. Consumers gating on `data_is_real` will reject these reports by construction. |
| `parameters` | The production thresholds and windows in force when the report was built (return window, VIX mapping, regime thresholds) plus harness parameters. |
| `calibration` | Summary over all classified bars (see below). |
| `walk_forward` | Per-fold summaries plus stability metrics. |
| `records` | One row per classified bar (date, scores, regime, confidence, risk level, volatility env) for full traceability. |

Calibration summary fields:

- `regime_distribution` / `regime_counts` — how often each regime was assigned.
- `mean_confidence_by_regime` — average classifier confidence per regime.
- `transition_count` / `persistence_rate` — how often the regime label changes
  day-to-day. A persistence rate near 1.0 means stable labels; a low rate means
  the classifier flickers.
- `forward_return_by_regime` — realized SPY return `forward_horizon` sessions
  after each label (count/mean/min/max). Bars too close to the end of the
  history are excluded, never extrapolated.
- `directional_hit_rate` — fraction of BULL labels followed by a positive
  forward return and BEAR labels followed by a negative one. Values near 0.5
  mean the label carries no directional information at that horizon.

Walk-forward fields:

- `folds[*].summary` — the same calibration summary, restricted to that fold's
  out-of-sample window.
- `max_distribution_drift` — largest total-variation distance between the
  regime distributions of adjacent folds (0 = identical regime mix, 1 =
  completely different). Large values on stable market data suggest threshold
  sensitivity.
- `mean_persistence_rate` — average label stability across folds.

## Guardrails

- The harness **cannot** write into `data/system/` (production artifacts) —
  `write_calibration_report` raises `CalibrationWriteGuardError`. Use
  `data/research/` (gitignored) for outputs.
- The QA-003 hermeticity guard in `tests/conftest.py` additionally proves the
  test suite leaves `data/system/` byte-identical.
- `tests/test_calibration_harness.py` proves: deterministic fixture output,
  no network dependency (sockets blocked), fail-closed data validation, and a
  stable report schema.
