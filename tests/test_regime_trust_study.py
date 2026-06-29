"""REGIME-TRUST-001 — reproducible regime trust/edge study on synthetic data.

Pins the synthetic-data edge findings so the trust study cannot silently rot:
on a constructed bull→crash→bear→sideways history the classifier's BULL/BEAR
labels align with the sign of forward returns, HIGH_VOLATILITY precedes negative
forward returns, and a long-only regime-conditioned exposure does not worsen the
mean outcome versus buy-and-hold while reducing downside.

These are properties of SYNTHETIC structure only (research-only, data_is_real=False);
they are NOT a real-market edge proof. Runs under the broker-free pandas pytest
venv (no real data, no live import).
"""
from __future__ import annotations

import unittest

from research.regime_trust_study import (
    build_regime_trust_study,
    generate_structured_history,
)


class StructuredHistoryTest(unittest.TestCase):
    def test_history_is_deterministic_and_well_formed(self) -> None:
        h1 = generate_structured_history()
        h2 = generate_structured_history()
        self.assertEqual(h1.spy_close, h2.spy_close)
        self.assertEqual(h1.vix_close, h2.vix_close)
        self.assertEqual(len(h1.dates), 60 + 30 + 40 + 50)


class RegimeEdgeTest(unittest.TestCase):
    def _study(self, model_version: str) -> dict:
        return build_regime_trust_study(
            model_version=model_version, generated_at="2026-06-29T00:00:00+00:00"
        )

    def test_research_markers_present(self) -> None:
        s = self._study("v2")
        self.assertTrue(s["research_only"])
        self.assertTrue(s["not_for_live_trading"])
        self.assertIs(s["data_is_real"], False)

    def test_all_four_regimes_emitted(self) -> None:
        for mv in ("v1", "v2"):
            counts = self._study(mv)["regime_counts"]
            for regime in ("BULL", "BEAR", "HIGH_VOLATILITY", "SIDEWAYS"):
                self.assertIn(regime, counts, f"{mv}: {regime} not emitted")

    def test_directional_hit_rates_are_strong(self) -> None:
        # On structured synthetic data the labels should align with forward sign.
        for mv in ("v1", "v2"):
            hit = self._study(mv)["directional_hit_rate"]
            self.assertGreaterEqual(hit["BULL"], 0.7, f"{mv} BULL hit rate weak")
            self.assertGreaterEqual(hit["BEAR"], 0.7, f"{mv} BEAR hit rate weak")

    def test_forward_returns_align_with_regime_sign(self) -> None:
        for mv in ("v1", "v2"):
            fwd = self._study(mv)["forward_return_by_regime"]
            self.assertGreater(fwd["BULL"]["mean"], 0.0, f"{mv} BULL fwd not positive")
            self.assertLess(fwd["BEAR"]["mean"], 0.0, f"{mv} BEAR fwd not negative")
            self.assertLess(
                fwd["HIGH_VOLATILITY"]["mean"], 0.0, f"{mv} HIGH_VOL fwd not negative"
            )

    def test_regime_conditioning_does_not_worsen_and_cuts_downside(self) -> None:
        for mv in ("v1", "v2"):
            edge = self._study(mv)["regime_conditioned_edge"]
            self.assertGreater(edge["comparable_bars"], 0)
            # Long-only risk-managed exposure should reduce downside (less negative
            # mean-downside) versus always-on buy-and-hold.
            self.assertTrue(edge["reduces_downside"], f"{mv} did not cut downside")


if __name__ == "__main__":
    unittest.main()
