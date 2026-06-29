"""Calibration constants for the v2 regime model (HWL-005).

These are the *strategy* parameters of ``core/regime_model_v2.py`` — factor
windows, normalisation divisors, composite weights, and classification
thresholds. They were previously hard-coded literals inside the model module.
HWL-005 (NOVA_MASTER_TODO_ROADMAP_2026_06_29.md §4a) extracts them into this
single calibration config so they can be reviewed / tuned in one place.

**This is a pure mechanical extraction — every value is byte-identical to the
previous in-line literal, so classification output is unchanged.** That guarantee
is pinned by ``tests/test_regime_calibration_golden.py`` against the golden
snapshot ``tests/fixtures/regime_v2_calibration_golden.json``. Changing a value
here is a *model* change (it alters classification) and must be reviewed as such —
it is NOT a free SAFE edit, and it would (correctly) break the golden test.

No imports beyond the stdlib are needed: these are plain numeric constants.
"""
from __future__ import annotations

# --- Factor windows and normalisation ---------------------------------------------

SHORT_WINDOW = 10           # sessions for ma_gap and momentum factors
DRAWDOWN_NORMALISE = 0.15   # 15% decline from window peak → drawdown_score 1.0
MA_GAP_NORMALISE = 0.025    # ±2.5% vs 10-session MA → ma_gap_score ±1.0

# --- Composite weights --------------------------------------------------------------

WEIGHT_TREND = 0.45
WEIGHT_MA_GAP = 0.30
WEIGHT_MOMENTUM = 0.25

# --- Classification thresholds --------------------------------------------------------

VOL_HIGH_THRESHOLD = 0.7           # identical to v1
VOL_ELEVATED_THRESHOLD = 0.55      # escalation: elevated vol …
DRAWDOWN_SEVERE_THRESHOLD = 0.6    # … plus severe drawdown → HIGH_VOLATILITY
COMPOSITE_BULL_THRESHOLD = 0.5
COMPOSITE_BEAR_THRESHOLD = -0.35
BEAR_DRAWDOWN_QUALIFIER = 0.7      # deep drawdown + non-positive composite → BEAR
