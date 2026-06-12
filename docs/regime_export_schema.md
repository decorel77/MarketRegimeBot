# MarketRegimeBot — Regime Export Schema v1.0

**Schema version:** `regime_export.v1`  
**Produced by:** `utils/regime_export_writer.py` → `data/system/regime_export.json`  
**Consumed by:** NovaTacticBot `adapters/market_regime_adapter.py` (MASTER-020)  
**TacticalEvent contract alignment:** v1.0

---

## Overview

`data/system/result_snapshot.json` is MarketRegimeBot's authoritative regime
artifact. It carries the `regime_result.v2` freshness envelope (`produced_at`,
`fresh_until`, `schema_version`, `producer_id`) and is the source of truth for
the current regime decision.

`regime_export.json` is a derived v1 compatibility/read artifact for
NovaTacticBot and any consumer still using the `regime_export.v1` shape. It must
be generated from the authoritative result snapshot payload, never maintained as
a second independent regime truth. If the authority payload is malformed, the
export fails closed to `UNKNOWN`, confidence `0`, and `data_is_real: false`.

---

## File location

```
C:\NovaGPT\Apps\MarketRegimeBot\data\system\regime_export.json
```

---

## Schema

```json
{
  "schema_version": "regime_export.v1",
  "project": "MarketRegimeBot",
  "generated_at": "<ISO-8601 UTC timestamp>",
  "market_regime": "<BULL | BEAR | SIDEWAYS | HIGH_VOLATILITY | RISK_ON | RISK_OFF | UNKNOWN>",
  "confidence": "<integer 0–100>",
  "risk_level": "<LOW | NORMAL | MEDIUM | HIGH | UNKNOWN>",
  "volatility_env": "<LOW_VOL | NORMAL | HIGH_VOL | UNKNOWN>",
  "input_source": "<yfinance | snapshot_adapter | synthetic_fallback | explicit | unknown>",
  "data_is_real": "<bool>",
  "reason": ["<string>", "..."],
  "dry_run": true,
  "read_only": true,
  "runtime_enabled": false,
  "derived_from": "data/system/result_snapshot.json",
  "source_schema_version": "regime_result.v2"
}
```

---

## Field definitions

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Always `"regime_export.v1"` |
| `project` | string | Always `"MarketRegimeBot"` |
| `generated_at` | ISO-8601 string | UTC timestamp of this export |
| `market_regime` | string | Primary regime classification (see below) |
| `confidence` | integer 0–100 | Classifier confidence in `market_regime` |
| `risk_level` | string | Risk assessment: LOW / NORMAL / MEDIUM / HIGH / UNKNOWN |
| `volatility_env` | string | Volatility environment: LOW_VOL / NORMAL / HIGH_VOL / UNKNOWN |
| `input_source` | string | Data source used for this classification (truthful: `yfinance` only when live market data was read) |
| `data_is_real` | bool | Realness flag (REPAIR-005). `true` **only** when derived from live market data (`input_source == "yfinance"`). Fixture/synthetic/snapshot-derived classifications are `false` so consumers (AllocationBot, TacticBot) must reject them. Matches the REPAIR-003 canonical `data_is_real` contract. |
| `reason` | string[] | Human-readable explanation of the classification decision |
| `dry_run` | bool | Always `true` — MarketRegimeBot never executes live |
| `read_only` | bool | Always `true` — this file is written by MarketRegimeBot only |
| `runtime_enabled` | bool | Always `false` — no runtime execution in this phase |

Additional authority metadata:

| Field | Type | Description |
|---|---|---|
| `derived_from` | string | Always `"data/system/result_snapshot.json"`; declares that this v1 export is derived from the authoritative v2 result snapshot |
| `source_schema_version` | string | Schema version of the authority payload, normally `"regime_result.v2"` |

---

## Regime values

| Value | Meaning |
|---|---|
| `BULL` | Strong positive trend (SPY/QQQ 20-day return > 5%) |
| `BEAR` | Strong negative trend (SPY/QQQ 20-day return < -5%) |
| `SIDEWAYS` | Low trend and low volatility — range-bound conditions |
| `HIGH_VOLATILITY` | VIX-derived volatility_score > 0.7 |
| `RISK_ON` | Future phase — not yet implemented |
| `RISK_OFF` | Future phase — not yet implemented |
| `UNKNOWN` | Classification failed or insufficient data |

---

## Volatility environment values

| Value | vol_score range | VIX equivalent |
|---|---|---|
| `LOW_VOL` | < 0.30 | VIX < ~22.5 |
| `NORMAL` | 0.30 – 0.60 | VIX ~22.5–30 |
| `HIGH_VOL` | ≥ 0.60 | VIX ≥ ~30 |
| `UNKNOWN` | invalid input | N/A |

---

## TacticalEvent mapping (for MASTER-020 adapter)

When NovaTacticBot reads this file, the adapter should produce a `TacticalEvent`:

| regime_export field | TacticalEvent field |
|---|---|
| `market_regime` | `regime` (via `Regime.*` constants) |
| `confidence / 100.0` | `score` (float 0–1) |
| `market_regime` | `strategy_id` = `"regime_{market_regime.lower()}"` |
| `"MarketRegimeBot"` | `source_bot` = `SourceBot.MARKET_REGIME_BOT` |
| `"REGIME_CHANGE"` | `event_type` |
| all export fields | `metadata` dict |

---

## Safety guarantees

- `dry_run` is always `true` and validated before write.
- `read_only` is always `true` — no downstream writes.
- `runtime_enabled` is always `false`.
- File is written only inside `MarketRegimeBot/data/system/`.
- No broker fields, no order fields, no credential fields.
- `result_snapshot.json` is the authority; `regime_export.json` must not be
  treated as an independent source of regime truth.
