# MarketRegimeBot

MarketRegimeBot is the NOVA ecosystem skeleton bot for market regime detection.

Future phases may classify conditions such as:

- BULL
- BEAR
- SIDEWAYS
- HIGH_VOLATILITY
- RISK_ON
- RISK_OFF

Current phase is skeleton only. It does not trade, place orders, connect to
brokers, move money, export allocations, or write to other NOVA repositories.

## Current Behavior

The one-shot cycle emits a safe dry-run regime result:

```powershell
python -m tools.regime_autocycle --once
```

Output shape:

```json
{
  "status": "SAFE_DRY_RUN_REGIME",
  "dry_run": true,
  "regime": "UNKNOWN",
  "confidence": 0
}
```

The cycle writes `data/system/result_snapshot.json` as the authoritative regime
snapshot and derives `data/system/regime_export.json` from it for v1 consumers.
Both files stay inside this project.

## Validation

```powershell
python -m unittest discover tests
python -m tools.regime_autocycle --once
```

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
