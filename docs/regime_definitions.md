# MarketRegimeBot — Regime Definitions

## Classification

| Property | Value |
|---|---|
| Document type | Reference documentation — informational only |
| Authority | Advisory — no execution, no broker, no orders |
| Schema source | `data/system/regime_registry.json` v1.1.0 |
| Classifier source | `core/regime_classifier.py` |

---

## Purpose

This document is the human-readable companion to `data/system/regime_registry.json`.
It defines the full vocabulary of market regimes recognised by MarketRegimeBot,
documents scoring thresholds, indicator signals, and explicitly records the
naming alignment between the registry IDs and the runtime classifier IDs.

No code in this file. No execution. Documentation only.

---

## Naming Alignment — Known Mismatch

The registry and the runtime classifier use different ID conventions for three
regimes. This mismatch must be resolved in REGIME-PHASE-002B before live data
is wired to the registry. The `classifier_id` field in each registry entry
records the current classifier name for cross-reference.

| Registry ID | Classifier ID | Aligned? | Notes |
|---|---|---|---|
| `BULL_MARKET` | `BULL` | NO | Rename classifier → `BULL_MARKET` in Phase 2B |
| `BEAR_MARKET` | `BEAR` | NO | Rename classifier → `BEAR_MARKET` in Phase 2B |
| `SIDEWAYS_MARKET` | `SIDEWAYS` | NO | Rename classifier → `SIDEWAYS_MARKET` in Phase 2B |
| `HIGH_VOLATILITY` | `HIGH_VOLATILITY` | YES | Already aligned |
| `LOW_VOLATILITY` | *(not implemented)* | N/A | Implement in Phase 3 |
| `RISK_ON` | *(not implemented)* | N/A | Implement in Phase 3 |
| `RISK_OFF` | *(not implemented)* | N/A | Implement in Phase 3 |

### Alignment plan

Phase 2B will update `core/regime_classifier.py` and `core/regime_contracts.py`
to rename `BULL` → `BULL_MARKET`, `BEAR` → `BEAR_MARKET`, and
`SIDEWAYS` → `SIDEWAYS_MARKET`. All tests will be updated simultaneously.
The registry IDs are the canonical names — the classifier must converge to them,
not the other way around.

---

## Classifier Scoring Model

The current classifier (`core/regime_classifier.py`) maps two continuous input
scores to a regime label. Both inputs are normalised floats.

| Input | Range | Meaning |
|---|---|---|
| `trend_score` | `−1.0` to `+1.0` | Negative = bearish; positive = bullish; zero = neutral |
| `volatility_score` | `0.0` to `1.0` | Higher = more volatile |

### Classification thresholds (v1 — from classifier source)

| Threshold constant | Value | Effect |
|---|---|---|
| `_VOLATILITY_HIGH_THRESHOLD` | `0.7` | Above this → HIGH_VOLATILITY (priority 1) |
| `_TREND_BULL_THRESHOLD` | `0.5` | Above this (and volatility ≤ 0.7) → BULL_MARKET |
| `_TREND_BEAR_THRESHOLD` | `−0.5` | Below this (and volatility ≤ 0.7) → BEAR_MARKET |

### Classification priority order

The classifier evaluates conditions in strict priority order. The first matching
condition wins.

```
1. volatility_score > 0.7           → HIGH_VOLATILITY
2. trend_score > 0.5                → BULL_MARKET  (currently labelled BULL)
3. trend_score < -0.5               → BEAR_MARKET  (currently labelled BEAR)
4. abs(trend_score) ≤ 0.5
   AND volatility_score ≤ 0.7      → SIDEWAYS_MARKET  (currently labelled SIDEWAYS)
5. (no condition matched)           → UNKNOWN
```

---

## Regime Reference

### BULL_MARKET

| Field | Value |
|---|---|
| Registry ID | `BULL_MARKET` |
| Classifier ID | `BULL` *(misaligned — to fix in Phase 2B)* |
| Label | Bull Market |
| Category | Directional trend |
| Risk level produced | `NORMAL` (trend < 0.85); `HIGH` (trend ≥ 0.85) |

**Definition:** A sustained upward price trend across broad market indices,
characterised by improving market breadth, rising price momentum, and generally
positive investor sentiment.

**Scoring conditions:**
- `trend_score > 0.5` (strong positive trend)
- `volatility_score ≤ 0.7` (volatility not elevated enough to override)
- Confidence = `min(100, int(trend_score × 100))`

**Indicator signals (future Phase 3):**
- S&P 500 / broad index above 200-day moving average
- Advance/decline line trending upward
- More 52-week highs than lows
- VIX below 20
- Investment-grade credit spreads tightening

**Strategy compatibility (future Phase 6):**
Favours momentum strategies, long equity exposure, covered calls on longs,
reduced defensive positioning.

---

### BEAR_MARKET

| Field | Value |
|---|---|
| Registry ID | `BEAR_MARKET` |
| Classifier ID | `BEAR` *(misaligned — to fix in Phase 2B)* |
| Label | Bear Market |
| Category | Directional trend |
| Risk level produced | `HIGH` |

**Definition:** A sustained downward price trend of 20% or more from recent
highs across broad market indices, typically accompanied by worsening market
breadth and deteriorating sentiment.

**Scoring conditions:**
- `trend_score < −0.5` (strong negative trend)
- `volatility_score ≤ 0.7` (pure trend signal, not overridden by volatility spike)
- Confidence = `min(100, int(abs(trend_score) × 100))`

**Indicator signals (future Phase 3):**
- S&P 500 down ≥ 20% from recent high
- Broad index below 200-day moving average
- Advance/decline line in persistent downtrend
- More 52-week lows than highs
- Credit spreads widening

**Strategy compatibility (future Phase 6):**
Favours reduced equity exposure, defensive sectors, cash preservation, and
put-protection strategies.

---

### SIDEWAYS_MARKET

| Field | Value |
|---|---|
| Registry ID | `SIDEWAYS_MARKET` |
| Classifier ID | `SIDEWAYS` *(misaligned — to fix in Phase 2B)* |
| Label | Sideways Market |
| Category | Range / consolidation |
| Risk level produced | `LOW` |

**Definition:** Range-bound price action with no sustained directional trend.
Also known as a consolidation or ranging regime. Characterised by price
oscillating between support and resistance levels without breaking out.

**Scoring conditions:**
- `abs(trend_score) ≤ 0.5` (weak or neutral trend)
- `volatility_score ≤ 0.7` (not a volatility regime)
- Confidence = `max(0, min(100, int((1.0 − abs(trend_score) − volatility_score) × 100)))`
  — higher confidence when both scores are close to zero

**Indicator signals (future Phase 3):**
- Price oscillating between defined support and resistance for ≥ 6 weeks
- Average Directional Index (ADX) below 20
- Bollinger Bands contracting
- Neutral advance/decline momentum

**Strategy compatibility (future Phase 6):**
Favours mean-reversion strategies, range-bound options plays (short strangles,
iron condors), and reduced directional exposure.

---

### HIGH_VOLATILITY

| Field | Value |
|---|---|
| Registry ID | `HIGH_VOLATILITY` |
| Classifier ID | `HIGH_VOLATILITY` *(aligned)* |
| Label | High Volatility |
| Category | Volatility |
| Risk level produced | `HIGH` |

**Definition:** Elevated implied or realised volatility relative to historical
norms. This regime has the highest classification priority — it overrides any
directional trend signal when volatility is sufficiently elevated.

**Scoring conditions:**
- `volatility_score > 0.7` (priority 1 — evaluated before any trend regime)
- Confidence = `min(100, int(volatility_score × 100))`

**Indicator signals (future Phase 3):**
- VIX above 25–30
- Realised 20-day volatility elevated relative to 1-year average
- Large intraday price swings (ATR expansion)
- Options implied volatility skew widening

**Strategy compatibility (future Phase 6):**
Favours volatility-harvesting or volatility-hedging strategies. Directional
conviction is low in this regime; wider stops and reduced size are appropriate.

---

### LOW_VOLATILITY

| Field | Value |
|---|---|
| Registry ID | `LOW_VOLATILITY` |
| Classifier ID | *(not yet implemented)* |
| Label | Low Volatility |
| Category | Volatility |
| Risk level produced | `LOW` *(planned)* |

**Definition:** Suppressed implied or realised volatility relative to historical
norms. Often associated with complacency, and can precede sharp volatility
expansions (the "calm before the storm" pattern).

**Scoring conditions (planned for Phase 3):**
- `volatility_score < 0.15` (approximate — to be calibrated)
- Must NOT be overridden by a strong trend signal

**Indicator signals (future Phase 3):**
- VIX below 15
- Realised 20-day volatility near multi-year lows
- Tight Bollinger Bands
- Low put/call ratio

**Strategy compatibility (future Phase 6):**
Favours premium-selling strategies (short options, iron condors) where low
implied volatility is sold. Risk: volatility can expand sharply from this regime.

**Implementation note:** This regime is in the registry but not yet in the
classifier. It will be added in Phase 3 alongside the scoring engine.

---

### RISK_ON

| Field | Value |
|---|---|
| Registry ID | `RISK_ON` |
| Classifier ID | *(not yet implemented)* |
| Label | Risk On |
| Category | Cross-asset sentiment |
| Risk level produced | `NORMAL` *(planned)* |

**Definition:** A cross-asset sentiment regime where market participants are
rotating into higher-risk assets (equities, high-yield credit, commodities,
emerging markets) away from safe-haven assets.

**Scoring conditions (planned for Phase 3):**
Risk On/Off classification requires cross-asset inputs that are not yet
available in the Phase 2 scoring model. It is a composite regime derived from
relative performance across multiple asset classes.

**Indicator signals (future Phase 3):**
- Equities outperforming bonds (SPY/TLT ratio rising)
- High-yield credit spreads tightening relative to investment-grade
- Commodity prices rising (DJC, oil)
- USD weakening vs. commodity-linked currencies (AUD, CAD)
- Emerging market equity indices outperforming developed markets

**Strategy compatibility (future Phase 6):**
Favours equity longs, high-yield exposure, commodity longs, and reduced
safe-haven positioning.

---

### RISK_OFF

| Field | Value |
|---|---|
| Registry ID | `RISK_OFF` |
| Classifier ID | *(not yet implemented)* |
| Label | Risk Off |
| Category | Cross-asset sentiment |
| Risk level produced | `HIGH` *(planned)* |

**Definition:** A cross-asset sentiment regime where market participants are
rotating into safe-haven assets (government bonds, gold, USD, JPY) away from
risk assets.

**Scoring conditions (planned for Phase 3):**
Composite cross-asset regime — requires multi-asset data not yet in Phase 2.

**Indicator signals (future Phase 3):**
- Bonds outperforming equities (TLT/SPY ratio rising)
- USD and JPY strengthening
- Gold rising
- High-yield spreads widening sharply
- Emerging market equities and currencies weakening

**Strategy compatibility (future Phase 6):**
Favours defensive positioning, long bonds/gold, cash, and hedged structures.

---

## Composite Regime Combinations

Regimes are not mutually exclusive at the conceptual level, though the current
classifier returns a single primary label. Future versions may return a primary
regime plus a secondary overlay.

| Primary | Overlay | Example combined condition |
|---|---|---|
| BULL_MARKET | RISK_ON | Strong trend + cross-asset confirmation |
| BEAR_MARKET | HIGH_VOLATILITY | Falling market + volatility spike (crash) |
| SIDEWAYS_MARKET | LOW_VOLATILITY | Tight range + suppressed vol (compression) |
| SIDEWAYS_MARKET | HIGH_VOLATILITY | Choppy, directionless but volatile |
| BEAR_MARKET | RISK_OFF | Broad risk-asset sell-off with flight to safety |

---

## UNKNOWN Regime

The classifier returns `UNKNOWN` when no condition in the priority chain is
matched (edge cases where inputs fall outside expected ranges or where regime
is genuinely indeterminate). This is also the default output during the dry-run
skeleton phase. Confidence is always 0.

---

## Schema Version History

| Version | Date | Changes |
|---|---|---|
| `1.0.0` | 2026-06-07 | Initial registry — 7 regimes, safety fields, tags |
| `1.1.0` | 2026-06-07 | Added `classifier_id`, `scoring_hints`, `signals` fields |
