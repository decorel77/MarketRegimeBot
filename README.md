# MarketRegimeBot

MarketRegimeBot is the NOVA ecosystem **advisory market-regime classifier**. It
classifies broad market conditions from live index/volatility data and publishes
the result as a read-only snapshot for advisory consumers. It is **ADVISORY_ONLY**:
it does not trade, place orders, connect to brokers, move money, or write to any
other NOVA repository. Its output steers no trade today — it is wired for
*observability*, not *control*.

Regime labels it can emit:

- BULL
- BEAR
- SIDEWAYS
- HIGH_VOLATILITY
- RISK_ON
- RISK_OFF
- UNKNOWN (fail-closed; published whenever inputs are not trusted live data)

## Current Behavior

The one-shot cycle classifies the current regime and writes a safe advisory
snapshot:

```powershell
python -m tools.regime_autocycle --once
```

What the cycle does (`workflow/regime_cycle.py` → `core/market_data_reader.py`):

1. Downloads SPY/QQQ/VIX OHLCV via `yfinance` and derives a `trend_score`
   (20-session SPY/QQQ return, normalised to [-1, 1]) and a `volatility_score`
   (VIX mapped from [15..40] to [0..1]).
2. Classifies those scores into a regime (`core/regime_classifier.py`,
   `core/volatility_classifier.py`).
3. **Fails closed** (QA-002 / REPAIR-005): only live `yfinance` data — or
   explicit test inputs — may be classified. Any download error, missing/bad
   data, snapshot-derived fallback, or synthetic input (`yfinance_error`,
   `synthetic_fallback`) is published as `UNKNOWN` / `confidence 0`, with the raw
   scores preserved only under `fallback_inputs` for diagnostics. A
   plausible-but-fake regime can never be published.

Provenance: every decision carries `input_source` and `data_is_real`.
`data_is_real` is **true only for live `yfinance` data**; consumers (Allocation,
Tactic, Bridge, Dashboard) must reject a regime whose `data_is_real` is false.

Output shape (live-data example — values vary with the market):

```json
{
  "status": "SAFE_DRY_RUN_REGIME",
  "dry_run": true,
  "regime": "BULL",
  "confidence": 0.7
}
```

Fail-closed shape (no/untrusted data — e.g. `yfinance` unavailable):

```json
{
  "status": "SAFE_DRY_RUN_REGIME",
  "dry_run": true,
  "regime": "UNKNOWN",
  "confidence": 0
}
```

`status` stays `SAFE_DRY_RUN_REGIME` and `dry_run` stays `true` in both cases:
the bot is advisory and never executes — `dry_run` reflects "no broker action",
not "no classification".

The cycle writes `data/system/result_snapshot.json` as the authoritative regime
snapshot and derives `data/system/regime_export.json` (v1) from it for
consumers. Both files stay inside this project.

### Consumers (read-only)

`regime_export.json` / `result_snapshot.json` are read by NovaAllocationBot
(diagnostic input only; authoritative allocation stays 90/10, REPAIR-007),
NovaTacticBot, NovaBridge, and NovaDashboard. They are **not** read by the live
stock bot or the options bot — NovaBotV2 uses its own separate internal regime
system. See the 2026-06-28 program audit for the full dataflow.

## Validation

```powershell
# Canonical runner (broker-free .venv with pandas + the pytest conftest sandbox):
.venv\Scripts\python.exe -m pytest -q tests
python -m tools.regime_autocycle --once
```

> `python -m unittest discover` is **not** the canonical runner (`-S` drops
> pandas → RED; see `docs/SAFE_TEST_GATE.md`). Since MRB-UNITTEST-GUARD-001
> a stray unittest run is at least harmless: `tests/__init__.py` sandboxes
> all production artifact writes, pinned by `tests/test__artifact_sandbox.py`.

## Research: calibration / walk-forward harness

A research-only harness (QA-014) replays the production classifier across
historical data and reports regime distribution, persistence, forward-return
alignment, and walk-forward stability. It is offline, fail-closed, and never
used for live trading:

```powershell
.\.venv\Scripts\python.exe -m tools.run_calibration --csv tests\fixtures\calibration_history.csv
```

See `docs/research/calibration_harness.md`.

A research-stage multi-factor Regime Model v2 (QA-012) can be evaluated with
`--model v2`; production keeps using v1. See `docs/regime_model_v2.md`.

A research-stage hysteresis/dwell-time filter (QA-013) can be applied with
`--hysteresis` to reduce regime flip-flopping; default off. See
`docs/regime_hysteresis.md`.
