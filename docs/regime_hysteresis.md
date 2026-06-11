# Regime Hysteresis / Dwell Time (QA-013)

**Status: research-stage, NOT in production.** The filter lives in
`core/regime_hysteresis.py` as a pure module and is applied only inside the
QA-014 calibration harness behind an explicit flag (`--hysteresis`, default
off). `workflow/regime_cycle.py`, the snapshot envelope, and all published
artifacts are untouched; v1 remains the production model and QA-001..QA-014
behavior is unchanged.

## What hysteresis is

A threshold classifier re-labels every time a score crosses a boundary. When
an input oscillates around a threshold (e.g. VIX around 32.5, the vol-score
0.7 boundary), the raw regime flips every bar. A consumer that re-positions
on each regime change would churn pointlessly.

The hysteresis filter sits *after* classification and decides what regime to
**publish**. Three rules:

1. **Dwell confirmation** — a candidate regime that differs from the
   published one must appear `min_dwell` consecutive times (default 3) with
   confidence ≥ `switch_confidence_min` (default 60) before the published
   regime switches. Alternating noise never accumulates confirmations; a
   low-confidence blip of the same candidate pauses, but does not reset, the
   count.
2. **Asymmetric HIGH_VOLATILITY handling** — entry is immediate (1
   observation, confidence ≥ 70): a risk-off signal is never delayed by
   smoothing. Exit requires 5 consecutive confirmations: calm must prove
   itself.
3. **Fail-closed wins instantly** — a raw UNKNOWN, an invalid
   regime/confidence, or observation metadata whose `data_is_real` /
   `is_fresh` is not exactly `True` forces published UNKNOWN immediately,
   with no dwell delay. Hysteresis must never hold a stale regime against a
   fail-closed signal. Recovery from UNKNOWN takes one qualified observation.

The filter starts at published UNKNOWN (warm-up) and seeds on the first
qualified observation.

## Measured effect (QA-014 harness, deterministic)

**Noisy series** (flat prices, VIX alternating 31↔34 across the
HIGH_VOLATILITY boundary, 60 classified bars):

| Metric | raw v1 | v1 + hysteresis |
| --- | --- | --- |
| Transitions | 59 (flips every bar) | **1** |
| Persistence rate | 0.0 | 0.983 |
| HIGH_VOLATILITY entry | 2024-01-22 | 2024-01-22 (same bar) |

**Clean QA-014 fixture** (bull → flat → bear → vol spike — no noise, so
hysteresis can only cost here):

| Metric | raw v1 | v1 + hysteresis |
| --- | --- | --- |
| Transitions / persistence | 3 / 0.972 | 3 / 0.972 |
| Last stale BULL label | 2024-02-20 | 2024-02-25 (+5 sessions) |
| First BEAR label | 2024-03-20 | 2024-03-24 (+4 sessions) |
| BULL directional hit rate | 0.613 | 0.528 |
| BEAR hit rate / HIGH_VOLATILITY entry | 1.0 / 2024-04-10 | 1.0 / 2024-04-10 (no delay) |

## When it helps, and the risk of too much dwell

Hysteresis pays off exactly when inputs sit near a threshold: it converts
boundary chatter into one decisive switch. On clean trending data it can only
add lag — every extra dwell observation is another session of publishing the
old regime after the world changed. The clean-fixture numbers above are that
cost made visible: ~4–5 extra sessions of stale labels and a lower BULL hit
rate, with risk-off entry deliberately exempted.

Rules of thumb:
- `min_dwell` should stay well below the typical regime duration you care
  about; 3–5 sessions against multi-month regimes is cheap insurance.
- Never gate HIGH_VOLATILITY entry behind a long dwell — that delays the one
  signal whose lateness is most expensive. The asymmetric defaults encode
  this.
- A high `switch_confidence_min` interacts with the classifier's confidence
  shape: v1's SIDEWAYS confidence is low near boundaries, so a high gate
  lengthens BULL→SIDEWAYS lag beyond `min_dwell` alone.

## How to calibrate with the QA-014 harness

```powershell
# Baseline vs filtered, same data — compare transition_count,
# persistence_rate, directional hit rates, and first/last label dates.
.\.venv\Scripts\python.exe -m tools.run_calibration --csv path\to\history.csv
.\.venv\Scripts\python.exe -m tools.run_calibration --csv path\to\history.csv --hysteresis
```

Custom configs go through the API
(`build_calibration_report(..., hysteresis_config=HysteresisConfig(...))`).
A config change is acceptable when, on representative history: (a) transition
count drops materially on noisy stretches, (b) directional hit rates do not
regress beyond the documented dwell cost, (c) HIGH_VOLATILITY entry dates are
unchanged, and (d) the QA-013 tests (`tests/test_regime_hysteresis.py`,
`tests/test_calibration_hysteresis.py`) still pass.

## Output shape

With `--hysteresis`, report records keep their normal shape; `market_regime`
and `confidence` become the *published* values, and each record gains a
`hysteresis` object (`raw_regime`, `raw_confidence`, `pending_regime`,
`pending_count`, `switched`, `fail_closed`). `parameters.hysteresis` carries
the active config. Default reports (flag off) are byte-identical to QA-014.

## Promotion path (deliberately not done here)

Production wiring would follow the same gate as Model v2: real-history
calibration first, then a `regime_result.v3` snapshot schema bump exposing
both `model_version` and the hysteresis state (raw vs published regime), so
consumers can always distinguish a smoothed decision from a raw one.
