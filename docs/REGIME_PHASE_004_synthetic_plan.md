# REGIME-PHASE-004 — Risk-on/Risk-off Classifier: Synthetic Test Plan

**Status:** planning document only (REGIME-PHASE-004 is `TODO` in the task queue).
**Scope:** how to specify and test a future risk-on/risk-off classifier using
**synthetic fixtures only**. This document implements no classifier and changes
no runtime behavior.

## Safety baseline (mirrors the repo safety lock)

This plan, and any future implementation it describes, must stay:

- **synthetic-only** — no live market data, no `yfinance`, no network/API calls,
  no broker feeds, no external sources;
- **read-only / advisory / diagnostic-only** — no broker execution, no order
  placement, no allocation export, no money movement;
- **no execution/scheduler authority** — no scheduler wiring, no autonomous
  commits/pushes, no writes to other NOVA repositories;
- **fail-closed** — missing/invalid/stale/non-real inputs yield a safe,
  non-actionable result, never a guess;
- **provenance-honest** — `data_is_real = false` is never promoted to `true`;
  insufficient confidence/sample stays non-actionable.

## What REGIME-PHASE-004 is

A **pure** risk-on/risk-off classifier that maps already-computed regime and
volatility signals to a `RISK_ON` / `RISK_OFF` / `UNKNOWN` label. The labels
`RISK_ON` and `RISK_OFF` already exist in `core/regime_contracts.py`; this phase
adds the classifier that selects between them. It performs no I/O and connects to
nothing — exactly like the existing `core/volatility_classifier.py` pattern.

It is **not** the ROADMAP "Phase 4 — Read-Only Market Analysis" market-data
connection. Connecting to any real market source (recorded or live) is **out of
scope** here and remains human-gated (see "Out of scope" below).

## Proposed input/output contract (to validate with fixtures)

Input (already-computed, in-memory signals — no market reads):

- `regime` label (existing regime vocabulary), `regime_confidence` (0..1),
- `volatility_class` (from `volatility_classifier`),
- provenance flags `data_is_real: bool` and `is_fresh: bool` (the same fields
  `core/regime_hysteresis.py` already consumes), plus `produced_at` / `fresh_until`
  per `core/regime_contracts.py` (`FRESHNESS_WINDOW` = 24h).

Output (advisory only):

- `label`: `RISK_ON` | `RISK_OFF` | `UNKNOWN`,
- `confidence`: float or `None` (withheld when inputs are weak),
- `status`: `OK` | `INSUFFICIENT` | `STALE` | `MISSING` | `INVALID` | `NOT_REAL`,
- `data_is_real`: propagated verbatim (never invented),
- `notes`: short, redaction-safe diagnostics.

The output must never include order intent, allocation weights, position sizing,
capital/risk changes, or any execution-eligibility field.

## Synthetic fixtures (all under `tests/fixtures/`, no real data)

| Fixture | Intent | Expected result |
|---|---|---|
| `risk_on_clear` | strong risk-on regime + low volatility, real+fresh | `RISK_ON`, status `OK` |
| `risk_off_clear` | strong risk-off regime + high volatility, real+fresh | `RISK_OFF`, status `OK` |
| `ambiguous` | conflicting/low-confidence signals | `UNKNOWN`, status `INSUFFICIENT` |
| `missing_inputs` | required field absent | `UNKNOWN`, status `MISSING` (fail closed) |
| `invalid_inputs` | wrong types / out-of-range confidence | `UNKNOWN`, status `INVALID` (fail closed) |
| `stale` | `fresh_until` in the past / `is_fresh=false` | `UNKNOWN`, status `STALE`, non-actionable |
| `not_real` | `data_is_real=false` | `UNKNOWN`, status `NOT_REAL`, never trusted |
| `mixed_provenance` | some real, some synthetic | `data_is_real=false` (fails closed to untrusted) |

Every fixture is synthetic and asserts `data_is_real=false` unless the case is
explicitly a labeled real-fixture (still offline, never a live read).

## Test plan (`tests/test_risk_classifier.py`, mirrors existing test style)

1. **Happy paths:** `risk_on_clear` → `RISK_ON`; `risk_off_clear` → `RISK_OFF`.
2. **Ambiguity:** `ambiguous` → `UNKNOWN` with `INSUFFICIENT`; confidence withheld.
3. **Fail-closed inputs:** `missing_inputs` → `MISSING`; `invalid_inputs` → `INVALID`;
   neither raises.
4. **Freshness:** `stale` → `STALE` and non-actionable; respects
   `produced_at` + `FRESHNESS_WINDOW` from `core/regime_contracts.py`.
5. **Realness:** `not_real` → `NOT_REAL`; `mixed_provenance` → `data_is_real=false`;
   `data_is_real=false` is never promoted to `true`.
6. **Determinism:** same fixture → identical result (no wall-clock/rng in compute;
   freshness uses an injected `now` like the existing contracts tests).
7. **No trading authority:** assert the output dict contains no order/allocation/
   risk/capital/position/execution field, and no buy/sell wording.
8. **Broker-free / offline:** assert the module imports no `yfinance`, `requests`,
   `urllib`, `socket`, `http.client`, broker SDK, or scheduler module, and reads no
   network or `data/system` / `data/history` path during tests (use temp/synthetic
   inputs only) — mirroring `tests/test_fallback_fail_closed.py` and
   `tests/test_startup_guardrails.py`.

## Freshness / realness rules

- Freshness is evaluated against `fresh_until` (`produced_at` + 24h). `STALE` or
  `MISSING` freshness ⇒ non-actionable `UNKNOWN`.
- `data_is_real` and `is_fresh` are consumed exactly as `core/regime_hysteresis.py`
  already does; the classifier must not upgrade either.
- Below a documented confidence floor, the label is `UNKNOWN` / `INSUFFICIENT` and
  no confidence number is published as trustworthy.

## No-trading-authority boundaries

The classifier output is advisory/diagnostic only. It must never create or imply
trading authority, allocation authority, order intent, risk/capital changes, or
live execution. It cannot reach a broker, place/modify/cancel orders, move money,
or change scheduler state.

## Out of scope (human-gated / blocked)

- Connecting to any real or recorded market data source, `yfinance`, network, or
  external API (ROADMAP "Phase 4 — Read-Only Market Analysis").
- Writing `data/system/result_snapshot.json`, `data/system/regime_export.json`, or
  `data/history/*.jsonl` (runtime/generated artifacts).
- `REGIME-TACTICBOT-001` export schema (blocked by `MASTER-017`).
- Any scheduler/runtime wiring or autocycle promotion.

These require an explicit, human-reviewed task card and are not part of this
synthetic plan.

## Acceptance criteria for a future safe implementation loop

- A pure `risk_classifier` module with the contract above, broker-free and unwired.
- `tests/test_risk_classifier.py` green on synthetic fixtures, covering every row in
  the fixtures table and the test plan.
- No live market read, no network, no `data/system`/`data/history` writes during tests.
- Fail-closed and provenance-honest behavior proven; no trading-authority fields.
