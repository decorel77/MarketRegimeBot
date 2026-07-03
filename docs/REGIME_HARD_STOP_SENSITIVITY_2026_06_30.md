# Regime Hard-Stop Mis-Classification Sensitivity (REGIME-TRUST-002)

Date: 2026-06-30 · Type: VERIFY (research/reporting only) · Card: REGIME-TRUST-002
Repo: MarketRegimeBot · Module: `research/regime_hard_stop_sensitivity.py` ·
Tests: `tests/test_regime_hard_stop_sensitivity.py` (14, green under `.venv` pytest)

> **Research only.** No live trading, no real broker data, no production behaviour
> change, **no threshold change**. Synthetic, deterministic (no RNG). The report
> carries `research_only` / `not_for_live_trading` / `data_is_real=False`. The
> off-limits `data/system/regime_export.json` was verified sha256-identical before
> and after the run.

## Question

REGIME-TRUST-001 showed the production classifier is directionally wired on
constructed structure. This follow-up asks the safety question the roadmap flags:
**how sensitive is the downstream hard-stop (`MaxNewPositions=0`) to
mis-classification?**

> **Provenance correction (2026-07-03, REGIME-HARDSTOP-TRUTH-001):** NovaBotV2
> `core/nova_koopbot.py` does halt new buys on `MaxNewPositions=0` /
> `ExecutionAllowed=false`, but it reads those keys from its **own**
> `workflow/nova_regime_checker.py` via its SystemStatus sheet — **not** from
> this repo's `regime_export.json`, which no NovaBotV2 code consumes today
> (NovaBridge/NovaDashboard read it, advisory-only; wiring it into the buy gate
> is HUMAN_GATED). This study therefore models a *hypothetical/future*
> downstream mapping at the classifier output, not an existing wire.

The downstream mapping modelled here: a consumer halts new buys when the
regime export sets `MaxNewPositions=0`. That export is keyed on the regime label;
the two HIGH-risk regimes the classifier emits — **`HIGH_VOLATILITY`** and
**`BEAR`** — are the defensive states a sane downstream maps to a hard-stop. This
study models the hard-stop decision **at the classifier output** (it does not
re-implement, wire, or change the downstream translation) and measures two errors:

- **false-hard-stop rate** — a benign true state mis-measured into a hard-stop
  regime → an *unnecessary* halt (opportunity cost, not unsafe);
- **missed-hard-stop rate** — a true hard-stop state mis-measured into a trading
  regime → the *dangerous* error: the bot keeps buying into a real bear / high-vol.

## Method

Production thresholds (unchanged): BULL `trend > 0.5`, BEAR `trend < -0.5`,
HIGH_VOLATILITY `vol > 0.7`. For each true `(trend, volatility)` state on a grid,
perturb the inputs by every offset on a fixed 5×5 lattice (`radius_steps=2`) at a
given `noise_level` (lattice step), clamp to the classifier's valid domain,
re-classify with the **production** `classify_regime`, and count hard-stop flips.
No RNG — the result is a pure function of grid + lattice, so it is byte-reproducible.

Grid: trend ∈ {−0.9,−0.6,−0.45,−0.3,0,0.3,0.45,0.6,0.9}, vol ∈
{0.1,0.3,0.5,0.6,0.65,0.7,0.75,0.8}; noise ∈ {0,0.05,0.10,0.15,0.20}.

## Results (pooled over the grid)

| noise | false-hard-stop rate | missed-hard-stop rate |
|---:|---:|---:|
| 0.00 | 0.000 | 0.000 |
| 0.05 | 0.158 | 0.128 |
| 0.10 | 0.214 | 0.207 |
| 0.15 | 0.299 | 0.243 |
| 0.20 | 0.299 | 0.279 |

Both error rates rise monotonically with noise (a symmetric lattice can only add
threshold crossings). At zero noise both are exactly 0 (the classifier is a clean
deterministic partition).

### Where the sensitivity lives

The pooled rates are **dominated by states adjacent to the decision boundaries**.
At noise 0.10, **26 of 72 grid states (36%) never flip** (flip-rate 0) — every
clearly-interior state is robust. The most sensitive states are exactly the
near-threshold ones:

| trend | vol | true regime | hard-stop | flip-rate @0.10 |
|---:|---:|---|---|---:|
| −0.45 | 0.65 | SIDEWAYS | no | 0.64 |
| −0.45 | 0.70 | SIDEWAYS | no | 0.64 |
| −0.45 | 0.60 | SIDEWAYS | no | 0.52 |
| −0.60 | 0.10 | BEAR | **yes** | 0.40 |
| −0.60 | 0.30 | BEAR | **yes** | 0.40 |

## Findings

1. **Interior states are safe.** A clear bull (t≈0.9) never false-hard-stops; a
   deep bear (t≈−0.9) is never missed under ≤0.2 noise. The hard-stop is reliable
   away from the boundary.
2. **The dangerous error is concentrated just past the bear threshold.** A true
   BEAR at t≈−0.6 (only 0.1 past the −0.5 cut) is mis-measured as SIDEWAYS — i.e.
   the hard-stop is *missed* — ~40% of the time under 0.10 input noise. This is the
   error that lets the bot keep buying into a real downturn.
3. **False hard-stops (benign → BEAR/HIGH_VOL) are slightly more common but
   benign in consequence** — they only cost opportunity, never safety.
4. **No threshold change is recommended from synthetic data.** This quantifies
   *sensitivity*, not a real-market error rate. The honest next step is the same
   HUMAN_GATED real-data replay REGIME-TRUST-001 flagged.

## Recommendations (advisory only — not implemented here)

- The boundary fragility is a strong argument for the **already-present hysteresis
  filter** (`core/regime_hysteresis.py`, QA-013): requiring dwell-time before
  switching out of a hard-stop regime directly attacks the t≈−0.6 missed-stop case.
  A follow-up could re-run this study *through* the hysteresis filter and quantify
  the reduction in missed-hard-stop rate. (Left as a future VERIFY card; this card
  changes nothing.)
- Treat regime confidence near the boundary as low-trust downstream (the classifier
  already emits `confidence`); consumers can fail-closed (assume hard-stop) when a
  near-bear / near-high-vol regime is reported with low confidence.

## Safety / provenance

- Pure: imports only `core.regime_classifier` (stdlib-only) — no pandas, no broker,
  no network, no runtime read/write.
- Production classifier replayed unchanged (byte-identical scoring).
- `regime_export.json` / `result_snapshot.json` untouched (sha256-verified).
- The classifier stays advisory + fail-closed; real-data replay stays HUMAN_GATED.
