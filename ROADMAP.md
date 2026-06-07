# MarketRegimeBot — Development Roadmap

## Classification

| Property | Value |
|---|---|
| Role | Read-only market regime analysis service |
| Authority | Advisory only — no execution authority |
| Broker authority | None |
| Order authority | None |
| Capital authority | None |
| Ecosystem position | NOVA intelligence layer — informational output only |

---

## Safety Guarantees (All Phases)

MarketRegimeBot carries these constraints in every phase without exception:

- **No broker connection** — never connects to IBKR/TWS or any broker API
- **No order placement** — never submits, routes, or influences orders
- **No execution authority** — regime outputs are advisory signals only
- **No capital allocation** — never moves, recommends, or sizes capital
- **No scheduler authority** — never triggers jobs in other NOVA bots
- **No Telegram execution** — may send informational notifications but never execution commands
- **No writes to other NOVA repos** — all output stays within this project boundary
- **No credential access** — never reads `.env` files, broker credentials, or API keys

---

## Phase 1 — Project Foundation

**Status:** Complete (2026-06-07)

**Goal:** Establish the project skeleton, contracts, and documentation baseline.

**Deliverables:**
- `ROADMAP.md` — this document
- `data/system/regime_registry.json` — canonical list of recognised regimes
- `utils/regime_registry_validator.py` — offline schema validator
- `tests/test_regime_registry.py` — registry unit tests
- `docs/architecture/autocycle_architecture.md` — 8-phase autocycle architecture
- `data/system/autocycle_policy.json` — autocycle policy schema (execution disabled)
- `utils/autocycle_policy_validator.py` — offline policy validator
- `tests/test_autocycle_policy.py` — policy unit tests
- `docs/architecture/sequential_autocycle_dev_prompt.md` — reusable dev prompt template
- Updated `docs/handover/CURRENT_STATE.md` and `savegame.md`

**Known structural issue (to resolve in Phase 2):**
The runtime classifier (`core/regime_classifier.py`) and contracts (`core/regime_contracts.py`)
use short regime IDs (`BULL`, `BEAR`, `SIDEWAYS`) while the registry uses full IDs
(`BULL_MARKET`, `BEAR_MARKET`, `SIDEWAYS_MARKET`). These must be aligned before
live data is wired to the registry.

**Safety:** Inert. No connections. No runtime effects. No execution.

---

## Phase 2 — Regime Definitions

**Goal:** Define the full vocabulary of market regimes with structured metadata.

**Deliverables:**
- Expanded `regime_registry.json` with signals, indicators, and scoring hints per regime
- `docs/regime_definitions.md` — human-readable regime taxonomy
- Unit tests for every defined regime

**Safety:** Schema and documentation only. No live data. No execution.

---

## Phase 3 — Regime Scoring Engine

**Goal:** Build a pure-function scoring engine that maps indicator values to regime scores.

**Deliverables:**
- `core/regime_scorer.py` — stateless scoring logic, no I/O
- Scoring weights per regime defined in `data/system/regime_weights.json`
- Full unit-test coverage of scoring logic with mocked inputs

**Safety:** Pure functions only. No market data connections. No execution.

---

## Phase 4 — Read-Only Market Analysis

**Goal:** Connect the scoring engine to read-only market data sources.

**Deliverables:**
- `core/market_data_reader.py` — read-only adapter for public market data
- Integration tests using recorded/static fixtures
- `data/system/result_snapshot.json` updated with live regime output

**Safety:** Read-only data access only. No broker. No orders. No execution.

---

## Phase 5 — Historical Regime Tracking

**Goal:** Persist regime history for backtesting and drift detection.

**Deliverables:**
- `data/history/regime_log.jsonl` — append-only regime history
- `core/regime_history.py` — write-to-local-file only, no network writes
- Basic drift-detection reporting

**Safety:** Local file writes only. No broker. No execution.

---

## Phase 6 — Strategy / Regime Compatibility Analysis

**Goal:** Produce read-only compatibility scores between regime outputs and known strategy types.

**Deliverables:**
- `core/strategy_compatibility.py` — maps regime → compatible strategy archetypes
- `data/system/compatibility_snapshot.json` — output artifact
- No allocation logic — archetypes are informational labels only

**Safety:** Advisory output only. No execution. No allocation.

---

## Phase 7 — Read-Only Integration with NovaBotV2

**Goal:** Expose regime snapshots that NovaBotV2 can optionally read for context.

**Deliverables:**
- `data/export/novabot_regime_snapshot.json` — shared read-only artifact
- Documentation of the interface contract
- NovaBotV2 is never required to act on this data; it is advisory context only

**Safety:** File export only. No broker. No orders. NovaBotV2 makes all its own decisions independently.

---

## Phase 8 — Read-Only Integration with NovaBotV2Options

**Goal:** Expose regime snapshots for NovaBotV2Options optional context consumption.

**Deliverables:**
- `data/export/options_regime_snapshot.json` — shared read-only artifact
- Documentation of the options-specific regime signals (volatility regime, risk-on/off)

**Safety:** File export only. No broker. No orders. NovaBotV2Options retains full autonomous decision authority.

---

## Phase 9 — Future TacticBot Support

**Goal:** Design the regime signal interface for a future TacticBot consumer.

**Deliverables:**
- `docs/tacticbot_interface.md` — interface specification (documentation only)
- Placeholder export schema in `data/export/tacticbot_regime_snapshot.json`

**Safety:** Documentation and schema planning only. No TacticBot code modified.

---

## Phase 10 — Ecosystem Intelligence Layer

**Goal:** Graduate MarketRegimeBot into a central read-only intelligence service for the full NOVA ecosystem.

**Deliverables:**
- Unified regime broadcast artifact consumed by any NOVA bot that opts in
- `docs/ecosystem_intelligence.md` — governance and consumption contract
- Versioned schema for backward-compatible regime signal evolution

**Safety:** Advisory intelligence layer only. All consuming bots retain full decision authority. MarketRegimeBot never holds execution, broker, or capital authority in any phase.

---

## Non-Goals (Permanent)

The following are permanently out of scope for MarketRegimeBot regardless of phase:

- Placing, routing, or influencing orders
- Accessing broker APIs or TWS/IBKR
- Moving or sizing capital
- Triggering scheduler jobs in other bots
- Sending execution commands via Telegram
- Reading credentials or `.env` files
- Writing to other NOVA repository trees
