# Current State

## MarketRegimeBot — Regime Definitions Complete — 2026-06-07

Status: PHASE_2_DOCS_SCHEMA_COMPLETE / SAFE_PLANNING_ONLY

MarketRegimeBot is a standalone NOVA ecosystem service for future market regime
detection. All current work is documentation, schema, and planning only.

---

### What exists

| Artifact | Path | Purpose |
|---|---|---|
| Roadmap | `ROADMAP.md` | 10-phase development roadmap (Phase 1 complete) |
| Regime registry | `data/system/regime_registry.json` | Regime schema v1.1.0 — 7 regimes with classifier_id, scoring_hints, signals |
| Regime definitions | `docs/regime_definitions.md` | Full regime vocabulary, naming alignment plan, scoring thresholds |
| Registry validator | `utils/regime_registry_validator.py` | Offline schema validator (v1.1.0 aware) |
| Registry tests | `tests/test_regime_registry.py` | 57 unit tests — includes naming alignment and v1.1.0 field coverage |
| Autocycle architecture | `docs/architecture/autocycle_architecture.md` | 8-phase autocycle design (planning only) |
| Autocycle policy | `data/system/autocycle_policy.json` | Policy schema — execution disabled |
| Autocycle validator | `utils/autocycle_policy_validator.py` | Offline policy validator |
| Autocycle tests | `tests/test_autocycle_policy.py` | 41 unit tests |
| Autocycle dev prompt | `docs/architecture/sequential_autocycle_dev_prompt.md` | Reusable autocycle prompt template |
| Skeleton core | `core/` | Inert regime classifier returning UNKNOWN |
| Result snapshot | `data/system/result_snapshot.json` | Dry-run output artifact |

---

### Current behaviour

- Produces a safe dry-run regime result (UNKNOWN, confidence 0).
- Writes only `data/system/result_snapshot.json` inside this project.
- Does not read live market data.
- Does not export allocations or modify other NOVA repositories.
- All validators and tests are fully offline — no network, no broker, no APIs.
- Autocycle execution is NOT implemented. Human approval mandatory.

---

### Naming alignment status (updated)

The registry (v1.1.0) now formally documents the naming mismatch between the
classifier/contracts and the registry IDs. The mismatch is enforced by tests.

| Registry ID | Classifier ID | Aligned | Resolution |
|---|---|---|---|
| `BULL_MARKET` | `BULL` | NO | REGIME-PHASE-002B — rename classifier |
| `BEAR_MARKET` | `BEAR` | NO | REGIME-PHASE-002B — rename classifier |
| `SIDEWAYS_MARKET` | `SIDEWAYS` | NO | REGIME-PHASE-002B — rename classifier |
| `HIGH_VOLATILITY` | `HIGH_VOLATILITY` | YES | No action needed |
| `LOW_VOLATILITY` | *(not implemented)* | N/A | REGIME-PHASE-003 |
| `RISK_ON` | *(not implemented)* | N/A | REGIME-PHASE-003 |
| `RISK_OFF` | *(not implemented)* | N/A | REGIME-PHASE-003 |

---

### Task queue — next tasks

| ID | Title | Status | Risk | Autocycle eligible |
|---|---|---|---|---|
| REGIME-PHASE-002B | Read market index data + classifier ID alignment | TODO | LOW | NO (CODE) |
| REGIME-PHASE-003 | Volatility regime detection | TODO | MEDIUM | NO |
| REGIME-PHASE-004 | Risk-on/risk-off classifier | TODO | MEDIUM | NO |

---

### Safety lock (all phases)

- No broker execution.
- No order placement.
- No live trading.
- No money movement.
- No allocation export.
- No writes to other NOVA repositories.
- No broker API connections.
- No credential access.
- No execution authority.
- No scheduler authority over other bots.
- No autonomous commits.
- No autonomous pushes.

---

### What does NOT exist yet

- Classifier ID alignment (BULL → BULL_MARKET etc.) — REGIME-PHASE-002B
- Live market data reader — REGIME-PHASE-002B
- Regime scoring engine — REGIME-PHASE-003
- Historical tracking — REGIME-PHASE-005
- NovaBotV2 integration — REGIME-PHASE-007
- NovaBotV2Options integration — REGIME-PHASE-008

---

### Guardrails authority

| Artifact | Path |
|---|---|
| Guardrails document | `docs/architecture/guardrails.md` |
| Guardrails policy | `data/system/guardrails.json` |
| Guardrails validator | `utils/guardrails_validator.py` |
| Guardrails tests | `tests/test_guardrails.py` |

All guardrails fields confirmed: `runtime_effect=false`, `broker_access_allowed=false`,
`order_execution_allowed=false`, `commit_requires_human_approval=true`,
`push_requires_human_approval=true`.
