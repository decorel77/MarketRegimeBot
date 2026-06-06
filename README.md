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

The cycle writes only `data/system/result_snapshot.json` inside this project.

## Validation

```powershell
python -m unittest discover tests
python -m tools.regime_autocycle --once
```

