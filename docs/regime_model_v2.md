# Regime Model v2 — Multi-Factor Inputs (QA-012)

**Status: research-stage, NOT in production.** The production regime cycle
(`workflow/regime_cycle.py`) and every published snapshot artifact still use
the v1 classifier exclusively. v2 lives in `core/regime_model_v2.py` as a pure
module and is evaluated through the QA-014 calibration harness behind an
explicit `model_version` flag (`v1` remains the default everywhere). Nothing
in QA-001..QA-014 is weakened: the v1 calibration report schema, the snapshot
envelope (`produced_at`, `fresh_until`, `schema_version`, `producer_id`,
`data_is_real`), and all fail-closed rules are unchanged.

## Why v2 — v1 weaknesses measured by the QA-014 harness

v1 classifies from two inputs only: a trailing 20-session return (trend) and
the VIX level (volatility). On the deterministic calibration fixture this
showed three concrete weaknesses:

1. **Boundary label lag.** The 20-session return is the slowest possible
   trend signal: BULL persisted 10 sessions into a flat market, and BEAR was
   recognised only 10 sessions into a decline.
2. **No drawdown awareness.** A crash with VIX below ~32.5 (volatility_score
   < 0.7) can never reach HIGH_VOLATILITY in v1, no matter how deep the
   drawdown.
3. **Confidence is a rescaled raw score**, not a margin from the decision
   threshold, so a barely-BULL day and a strongly-BULL day are hard to
   distinguish.

## v1 vs v2

| | v1 (production) | v2 (research) |
| --- | --- | --- |
| Inputs | trend, volatility | trend, volatility, drawdown, MA gap, momentum |
| Trend signal | 20-session return only | composite: 0.45·trend + 0.30·ma_gap + 0.25·momentum |
| HIGH_VOLATILITY | vol > 0.7 | vol > 0.7 **or** vol ≥ 0.55 with drawdown ≥ 0.6 |
| BULL | trend > 0.5 | composite > 0.5 |
| BEAR | trend < −0.5 | composite < −0.35 **or** drawdown ≥ 0.7 with composite < 0 |
| SIDEWAYS | otherwise | otherwise |

## Factors

All factors are computed from the **same trailing 21-close window** the
production reader fetches; trend and volatility reuse the production math by
import (never copied), so they cannot drift.

| Factor | Range | Definition |
| --- | --- | --- |
| `trend_score` | [−1, 1] | production 20-session SPY+QQQ return, 10% → 1.0 |
| `volatility_score` | [0, 1] | production VIX mapping, 15 → 0.0, 40 → 1.0 |
| `drawdown_score` | [0, 1] | decline from window peak, 15% → 1.0 |
| `ma_gap_score` | [−1, 1] | last close vs 10-session MA, ±2.5% → ±1 |
| `momentum_score` | [−1, 1] | (up days − down days) / sessions, last 10 |

The two short-window factors are what remove the boundary lag: when a trend
stalls, the price-vs-MA gap and the up-day balance decay within ~5 sessions
while the 20-session return still reflects the old regime.

## Calibration evidence (QA-014 fixture, deterministic)

130-bar fixture: bull → flat → bear → vol spike. Same harness, same windows,
both models (`tests/test_calibration_v1_v2.py` asserts these properties):

| Metric | v1 | v2 |
| --- | --- | --- |
| Last (stale) BULL label in flat phase | 2024-02-20 (10 sessions late) | 2024-02-14 (4 sessions late) |
| First BEAR label in decline | 2024-03-20 (10 sessions in) | 2024-03-14 (4 sessions in) |
| BULL directional hit rate (5-session fwd) | 0.613 | **0.760** |
| BEAR directional hit rate | 1.0 | 1.0 |
| Transitions / persistence | 3 / 0.972 | 3 / 0.972 (no flicker added) |
| Vol-spike phase | HIGH_VOLATILITY | identical |

v2 reacts ~6 sessions faster at both boundaries without adding a single extra
transition, and agrees with v1 everywhere v1 is right (steady phases, spike).

## Known limitations

- Thresholds and weights are calibrated against the synthetic fixture and
  first-principles scale arguments — **not yet against real multi-year
  history**. Promotion requires a calibration run on real SPY/QQQ/VIX data.
- The drawdown escalation rule (elevated vol + severe drawdown) is exercised
  by unit tests, not by the fixture; real crash data should validate it.
- The fixture has no volume/dispersion data, so those factors were left out
  rather than faked (fixture-safe rule).
- v2 confidence keeps v1's `int()` truncation idiom for comparability; it is
  margin-flavored but not a calibrated probability.

## Promotion path (deliberately not done here)

Wiring v2 into the production cycle requires, in order:
1. A v2 calibration run on real historical data with results reviewed.
2. A result-snapshot schema bump (`regime_result.v3`) adding a
   `model_version` field, so consumers can always see which model produced a
   decision — silent model swaps are a truth-gap of exactly the kind the QA
   audits exist to prevent.
3. Reader support for passing full close windows to the model, kept behind a
   default-off flag in `run_regime_cycle`.

## How to evaluate (and how to validate future threshold changes)

```powershell
# v1 baseline vs v2, same fixture or any local history CSV
.\.venv\Scripts\python.exe -m tools.run_calibration --csv tests\fixtures\calibration_history.csv --model v1
.\.venv\Scripts\python.exe -m tools.run_calibration --csv tests\fixtures\calibration_history.csv --model v2
```

Any future threshold or weight change must repeat this comparison and show,
on the same data: (a) directional hit rates do not regress, (b) transition
count / persistence do not degrade (no flicker), (c) the vol-spike phase
still classifies HIGH_VOLATILITY, and (d) the v1-vs-v2 calibration tests in
`tests/test_calibration_v1_v2.py` still pass. The harness is the gate:
changes that cannot demonstrate improvement there do not get promoted.
