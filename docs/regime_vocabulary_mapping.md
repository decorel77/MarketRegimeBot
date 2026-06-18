# MarketRegimeBot — Regime Vocabulary Mapping

Status: mapping/contract document (docs-only); changes no behaviour
Scope: one canonical regime vocabulary mapped to the classifier alias, dashboard label, and Bridge envelope value, plus explicit legacy aliases and an UNKNOWN-fail-closed rule
Implementation status: this document renames nothing in code, changes no classifier output, reads no real runtime data, and touches no `data/system/*` runtime file. It is a reference mapping; behaviour is unchanged.

Card: REGIME-002 (§4 EPIC-05) from the NovaGPT Vault roadmap. Companion to `regime_definitions.md` (definitions/registry↔classifier) and the `regime_result.v2` producer contract. The canonical-vs-classifier rename itself is REGIME-PHASE-002B (not done here).

## Canonical vocabulary

The **registry IDs are canonical** (per `regime_definitions.md`). The classifier must converge to them; consumers should treat the registry ID as the contract value.

| Canonical (registry ID) | Current classifier alias | Human/dashboard label | Bridge `regime_result.v2` `market_regime` value | Status |
|---|---|---|---|---|
| `BULL_MARKET` | `BULL` *(legacy alias)* | Bull Market | `BULL_MARKET` (canonical) | classifier rename pending (REGIME-PHASE-002B) |
| `BEAR_MARKET` | `BEAR` *(legacy alias)* | Bear Market | `BEAR_MARKET` | classifier rename pending |
| `SIDEWAYS_MARKET` | `SIDEWAYS` *(legacy alias)* | Sideways Market | `SIDEWAYS_MARKET` | classifier rename pending |
| `HIGH_VOLATILITY` | `HIGH_VOLATILITY` | High Volatility | `HIGH_VOLATILITY` | aligned |
| `LOW_VOLATILITY` | *(not implemented)* | Low Volatility | `LOW_VOLATILITY` | registry-only (Phase 3) |
| `RISK_ON` | *(not implemented)* | Risk On | `RISK_ON` | registry-only (Phase 3) |
| `RISK_OFF` | *(not implemented)* | Risk Off | `RISK_OFF` | registry-only (Phase 3) |
| `UNKNOWN` | `UNKNOWN` | Unknown / indeterminate | `UNKNOWN` | always available; confidence 0 |

## Legacy alias rule (read direction only)

- A consumer that receives a legacy classifier alias (`BULL`/`BEAR`/`SIDEWAYS`) MUST map it to its canonical ID (`BULL_MARKET`/`BEAR_MARKET`/`SIDEWAYS_MARKET`) for display/contract purposes.
- Mapping is **one-way and read-only**: it does not rename the classifier output (that is REGIME-PHASE-002B) and does not rewrite any runtime envelope.

## UNKNOWN — fail closed

- Any label that is **not** in the canonical table above MUST be treated as `UNKNOWN`, not silently passed through or guessed.
- A missing/empty/null regime value ⇒ `UNKNOWN` (confidence 0), never a directional regime.
- A consumer must never invent a canonical ID from an unrecognised string.

## What this mapping does NOT change

- No classifier/code rename (REGIME-PHASE-002B owns that).
- No registry edit, no runtime envelope rewrite, no `regime_export.json` change.
- No dashboard/Bridge wiring (real wiring is HUMAN_GATED).

## Validation (docs-only / synthetic)

- Exhaustive mapping: every canonical ID has an alias, a label, and a Bridge value (or an explicit *(not implemented)*).
- Unknown/unmapped input ⇒ `UNKNOWN` (fail-closed).
- No real runtime export is read; no behaviour is exercised.

## Safety confirmation

This mapping was written from `regime_definitions.md` and the registry naming-alignment section only. It renamed no code, changed no classifier output, read/modified no runtime/generated data (`data/system/regime_export.json` and the untracked `_test_regime_export.json` were left untouched and unstaged), and touched no `.env`/secret, scheduler, broker, or risk path. It is advisory/reference; it grants no authority and lifts no gate.
