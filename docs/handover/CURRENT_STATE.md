# Current State

## MarketRegimeBot — Phase 3 Volatility Classifier — 2026-06-09

Status: PHASE_3_VOLATILITY_CLASSIFIER_COMPLETE / ADVISORY_ONLY

MarketRegimeBot is a standalone NOVA ecosystem service for market regime detection.
Phase 3 delivers live yfinance-driven classification with dedicated volatility environment
labeling (HIGH_VOL / NORMAL / LOW_VOL).

---

### What exists

| Artifact | Path | Purpose |
|---|---|---|
| Roadmap | `ROADMAP.md` | 10-phase development roadmap |
| Regime registry | `data/system/regime_registry.json` | Regime schema v1.1.0 — 7 regimes |
| Regime definitions | `docs/regime_definitions.md` | Full regime vocabulary and scoring thresholds |
| Registry validator | `utils/regime_registry_validator.py` | Offline schema validator |
| Autocycle architecture | `docs/architecture/autocycle_architecture.md` | 8-phase autocycle design |
| Autocycle policy | `data/system/autocycle_policy.json` | Policy schema — execution disabled |
| Autocycle validator | `utils/autocycle_policy_validator.py` | Offline policy validator |
| Regime classifier | `core/regime_classifier.py` | BULL/BEAR/SIDEWAYS/HIGH_VOLATILITY classifier |
| Regime contracts | `core/regime_contracts.py` | `RegimeDecision` (now includes `volatility_env`, `input_source`) |
| **Volatility classifier** | `core/volatility_classifier.py` | **NEW** HIGH_VOL/NORMAL/LOW_VOL from vol_score. VIX mapping. ADVISORY_ONLY. (REGIME-PHASE-003 / MASTER-016) |
| **Market data reader** | `core/market_data_reader.py` | yfinance reader for SPY/QQQ/VIX → RegimeInput. Fails closed. (REGIME-PHASE-002B / MASTER-012) |
| Snapshot adapter | `core/snapshot_adapter.py` | Reads sibling project snapshots |
| **Regime cycle (Phase 3)** | `workflow/regime_cycle.py` | **UPDATED** Input priority: explicit > yfinance > snapshot > DRY_RUN_INPUTS. Outputs `volatility_env` and `input_source`. |
| Result snapshot | `data/system/result_snapshot.json` | Dry-run output artifact (now includes `volatility_env`, `input_source`) |

---

### Current behaviour (Phase 3)

- Classifies market regime from live yfinance SPY/QQQ/VIX data (when available).
- Input source priority: explicit inputs → yfinance live data → snapshot adapter → DRY_RUN_INPUTS.
- Writes only `data/system/result_snapshot.json` inside this project.
- `volatility_env` field (HIGH_VOL / NORMAL / LOW_VOL) computed from VIX-derived volatility_score.
- `input_source` field records which data source was used.
- Fails closed: any yfinance failure → falls back to snapshot adapter → falls back to synthetic inputs.
- No broker access. No writes to other NOVA repositories. Advisory only.

---

### Volatility environment thresholds

| vol_score | volatility_env | VIX equivalent |
|---|---|---|
| < 0.30 | LOW_VOL | VIX < ~22.5 |
| 0.30 – 0.60 | NORMAL | VIX ~22.5–30 |
| ≥ 0.60 | HIGH_VOL | VIX ≥ ~30 |

---

### Naming alignment status

The naming mismatch between classifier IDs and registry IDs remains unresolved
(BULL vs BULL_MARKET etc.). Tracked under REGIME-PHASE-002B.

---

### Tests (248 passing)

| File | Tests |
|---|---|
| `tests/test_regime_registry.py` | 57 |
| `tests/test_autocycle_policy.py` | 41 |
| `tests/test_regime_classifier.py` | — |
| `tests/test_regime_contracts.py` | — |
| `tests/test_market_data_reader.py` | 28 |
| `tests/test_volatility_classifier.py` | **NEW** 20+ |
| `tests/test_regime_cycle.py` | updated (Phase 3 tests) |

---

### Task queue — next tasks

| ID | Title | Status | Blocked by |
|---|---|---|---|
| REGIME-PHASE-003 | Volatility regime detection | **DONE** | — |
| REGIME-TACTICBOT-001 | TacticBot-compatible export schema | TODO | MASTER-017 |
| REGIME-PHASE-004 | Risk-on/risk-off classifier | TODO | — |

> REGIME-PHASE-004 synthetic test plan: `docs/REGIME_PHASE_004_synthetic_plan.md` (synthetic-only, fail-closed, advisory-only; live market data remains out of scope / human-gated).

---

### Safety lock (all phases)

- No broker execution, no order placement, no live trading.
- No money movement, no allocation export.
- No writes to other NOVA repositories.
- No broker API connections, no credential access.
- No execution authority, no scheduler authority.
- No autonomous commits or pushes.
