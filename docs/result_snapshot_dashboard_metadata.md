# Result Snapshot — Dashboard Trust Metadata

MarketRegimeBot's `data/system/result_snapshot.json` carries an explicit
public-safe trust/freshness envelope so a read-only consumer (NovaDashboard's
collector / approved-source contract) can gate on it instead of trusting a
once-real regime forever. The envelope is built by
`core/regime_contracts.build_snapshot_envelope()` and is threaded into every
serialized `RegimeDecision.to_dict()`.

## Fields

| Field | Source | Semantics |
|---|---|---|
| `produced_at` | injectable, else `now` (UTC ISO-8601) | when the snapshot was produced |
| `fresh_until` | `produced_at + 24h` (`FRESHNESS_WINDOW`) | conservative freshness horizon |
| `schema_version` | `"regime_result.v2"` | stable schema id |
| `producer_id` | `"MarketRegimeBot"` | producing process |
| `data_is_real` | decision field (REPAIR-005) | **fail-closed**: True only from live market data; fixture/synthetic/snapshot-derived inputs stay False |
| `public_safe` | unconditional `True` (this change) | static marker: the snapshot carries only public-safe fields (regime label, confidence, risk level, reason, vol env, safety flags) — no account/order ids, secrets, or machine paths |

`public_safe` is **not** a realness claim. Realness remains fail-closed in
`data_is_real`; a stale or fixture-derived snapshot is still `public_safe: true`
but `data_is_real: false`.

## Boundaries

Adding `public_safe` is a pure additive metadata change to the snapshot builder.
It runs no live/scheduled/broker/order workflow, performs no network call, and
writes no runtime `result_snapshot.json` (tests use injected `produced_at` and
temporary paths only). MarketRegimeBot stays dry-run.

## Remaining blockers before NovaDashboard can read this as an APPROVED REAL source

Per the dashboard readiness gate
(`Apps/NovaDashboard/docs/DASH_014E_REAL_SOURCE_READINESS_DECISION.md` +
`DASH_014F_REGIME_ALLOCATION_APPROVED_SOURCE.md`), the page stays
MISSING/UNVERIFIED until **Joeri** approves and:

1. A **fresh, real** snapshot exists — `data_is_real: true` requires the regime
   to be derived from live market data, which does not accrue while
   `\NovaBot_Main` / the regime cycle is paused. A stale/dry-run snapshot stays
   UNVERIFIED.
2. The exact source path is human-approved as a read-only, generated (not
   raw-runtime) artifact.
3. The current working-tree `result_snapshot.json` is regenerated under
   supervision so it actually carries these fields with a real, fresh value.
4. No NovaDashboard wiring changes here: the dashboard's approved-source contract
   already requires `public_safe` + `data_is_real` + `produced_at` + `fresh_until`
   and fails closed without them.
