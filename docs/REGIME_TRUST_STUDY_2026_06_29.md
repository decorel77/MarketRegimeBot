# Regime trust / edge study — synthetic structured data (REGIME-TRUST-001) — 2026-06-29

**Card:** REGIME-TRUST-001 (VERIFY) from `NOVA_MASTER_TODO_ROADMAP_2026_06_29.md` §4c.
**Type:** research / reporting only. **No live trading, no real broker data, no
production behaviour change.** Runs under the broker-free pandas pytest venv.
**Artifacts:** `research/regime_trust_study.py` (synthetic harness + edge metrics),
`tests/test_regime_trust_study.py` (reproducible, 6 tests green),
this report.

**Question:** *does the MarketRegimeBot classifier add directional edge?* — i.e. do
its BULL / BEAR / HIGH_VOLATILITY / SIDEWAYS labels carry information about the sign
of subsequent returns, and would conditioning exposure on them have helped?

---

## 1. Method

- **Synthetic structured history** (deterministic, seeded): a 180-bar arc with an
  explicit **bull → crash/high-vol → bear → sideways** structure
  (`research/regime_trust_study.generate_structured_history`). SPY/QQQ/VIX series
  built so each phase has known directional + volatility character.
- **Production classifier replayed** over it via `research/calibration_harness`
  (byte-identical production scoring — no research copy that could drift), for both
  model **v1** (production) and **v2** (multi-factor research model), 5-session
  forward horizon.
- **Edge measured** three ways: directional hit rate (BULL precedes up, BEAR
  precedes down), mean forward return by regime, and a **long-only regime-conditioned
  exposure** (full risk only when BULL, flat otherwise) vs **buy-and-hold**.

**Honesty boundary:** synthetic data with embedded structure can only show the
classifier *responds correctly to structure that is there by construction*. It does
**not** prove real-market edge. Real/approved-data validation is **HUMAN_GATED** and
is NOT performed here. All artifacts carry `research_only` / `not_for_live_trading` /
`data_is_real=False`.

## 2. Results

| Metric | model v1 | model v2 |
|---|---|---|
| BULL directional hit rate | **0.878** | **0.900** |
| BEAR directional hit rate | **0.933** | **0.909** |
| Mean fwd return — BULL | +1.47% | +1.63% |
| Mean fwd return — BEAR | −1.49% | −1.26% |
| Mean fwd return — HIGH_VOLATILITY | **−4.68%** | **−4.75%** |
| Mean fwd return — SIDEWAYS | +0.09% | −0.02% |
| Persistence rate (1 − transition rate) | 0.943 | 0.969 |
| Walk-forward folds / max distribution drift | 7 / **0.95** | 7 / **1.00** |

**Regime-conditioned exposure vs buy-and-hold (long-only, BULL=full / else flat):**

| | buy-and-hold | regime-conditioned (v1) | regime-conditioned (v2) |
|---|---|---|---|
| Mean per-bar forward return | −0.83% | **+0.39%** | **+0.42%** |
| Mean downside (neg-only, per bar) | −1.38% | **−0.09%** | **−0.06%** |

## 3. Findings

1. **The labels are directionally informative on structured data.** BULL precedes
   positive 5-day returns ~88–90% of the time; BEAR precedes negative ~91–93%.
   HIGH_VOLATILITY is the strongest signal — it precedes a sharp mean −4.7%, exactly
   the risk-off escalation it is meant to flag.
2. **Regime-awareness converts a losing arc into a positive one.** On this arc
   (net-down because the crash+bear phases dominate) buy-and-hold averages −0.83%
   per bar; a long-only "full risk only in BULL" rule averages **+0.4%** and cuts
   mean downside by ~**20×** (−1.38% → ~−0.07%). That is the core value proposition:
   the classifier's main contribution is **avoiding drawdown phases**, not picking
   tops.
3. **Decisions are stable.** Persistence 0.94–0.97 — the classifier does not
   flip-flop bar-to-bar; v2 is slightly more persistent than v1.
4. **v1 and v2 agree directionally**; v2's BULL signal is marginally stronger and
   its decisions marginally more persistent.

## 4. Limitations / honest caveats

- **Synthetic only.** These numbers are a property of the *constructed* arc. They
  prove the classifier is *internally sound and directionally wired correctly*, not
  that real markets contain exploitable regime structure. **Real-data validation is
  HUMAN_GATED** (no real broker/market data was used).
- **High walk-forward distribution drift (0.95–1.0).** The out-of-sample folds each
  land in a different phase, so the regime mix shifts strongly fold-to-fold. By
  construction here, but on *real* data this same metric being high would be a
  warning of instability — it should be re-checked on approved real history before
  any trust is extended.
- **No transaction costs / slippage** in the edge comparison (it measures signal
  alignment, not a tradable strategy). The €200 live cap + whole-share sizing
  (NovaBotV2) further constrain any real exploitation.
- **The classifier does NOT currently hard-stop the live bot** *(provenance
  corrected 2026-07-03, REGIME-HARDSTOP-TRUTH-001)*. NovaBotV2's buy gate reads
  `MaxNewPositions` / `ExecutionAllowed` from its **own**
  `workflow/nova_regime_checker.py` via its SystemStatus sheet; no NovaBotV2
  code consumes this repo's `regime_export.json` (NovaBridge/NovaDashboard read
  it, advisory-only). Contract pinned in NovaBotV2
  `tests/test_regime_provenance_contract.py`. *If* that wiring ever lands
  (HUMAN_GATED), a mis-emitted hard-stop state would silently halt NovaBotV2 —
  so the *fail-closed* freshness/contract guards matter as much as edge; those
  remain in place and are unaffected by this study.

## 5. Verdict

**On synthetic structured data the classifier adds clear, stable directional edge,
dominated by its drawdown-avoidance in BEAR/HIGH_VOLATILITY.** This is a *necessary
but not sufficient* trust result: it clears the "is the classifier directionally
wired correctly?" bar. It does **not** establish real-market trust — that requires a
HUMAN_GATED real/approved-data replay (the same `calibration_harness` +
`regime_trust_study` can be pointed at approved history once provisioned). Until
then the classifier stays **advisory with fail-closed guards**, exactly as today.

**Reproduce:** `Apps/MarketRegimeBot/.venv/Scripts/python -m pytest
tests/test_regime_trust_study.py -q` (broker-free venv; no real data; no writes to
`data/system/`).
