"""Read-only market data reader for MarketRegimeBot.

Downloads OHLCV data for SPY, QQQ, and VIX via yfinance and converts them
into a RegimeInput (trend_score, volatility_score) consumable by the
regime classifier.

Algorithm:
  trend_score      — Average 20-day return of SPY and QQQ, normalised to [-1, 1].
                     Return > 0 is bullish, < 0 bearish.  Clamped at ±1.
  volatility_score — VIX close mapped linearly from [VIX_LOW..VIX_HIGH] to [0..1].
                     VIX ≤ 15 → 0.0 (low vol), VIX ≥ 40 → 1.0 (extreme vol).

Fails closed: any download error, missing data, or bad schema returns
(DRY_RUN_INPUTS, "yfinance_error") without raising.

No broker imports. Read-only. ADVISORY_ONLY.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.regime_classifier import DRY_RUN_INPUTS, RegimeInput

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# --- Constants ------------------------------------------------------------------

_TREND_TICKERS = ("SPY", "QQQ")
_VOL_TICKER = "^VIX"
_LOOKBACK_DAYS = 30           # fetch window — 20 trading days fit inside 30 cal days
_RETURN_WINDOW = 20           # 20-session price return
_RETURN_NORMALISE = 0.10      # 10% return ≈ trend_score 1.0 (reasonable scale)

# VIX → volatility_score linear mapping
_VIX_LOW = 15.0               # VIX ≤ this → vol score 0.0
_VIX_HIGH = 40.0              # VIX ≥ this → vol score 1.0

SOURCE_YFINANCE = "yfinance"
SOURCE_FALLBACK = "yfinance_error"


# --- Internal helpers -----------------------------------------------------------

def _compute_trend_score(prices: "dict[str, list[float]]") -> float | None:
    """Return average 20-day return for SPY+QQQ normalised to [-1, 1]."""
    returns: list[float] = []
    for ticker, closes in prices.items():
        if len(closes) < 2:
            logger.warning("Insufficient price data for %s (%d bars)", ticker, len(closes))
            return None
        # Use last N sessions
        n = min(_RETURN_WINDOW, len(closes) - 1)
        ret = (closes[-1] - closes[-(n + 1)]) / closes[-(n + 1)]
        returns.append(ret)

    if not returns:
        return None

    avg_return = sum(returns) / len(returns)
    score = avg_return / _RETURN_NORMALISE
    return max(-1.0, min(1.0, round(score, 4)))


def _compute_volatility_score(vix_close: float) -> float:
    """Map a VIX close price to [0, 1]."""
    if vix_close <= _VIX_LOW:
        return 0.0
    if vix_close >= _VIX_HIGH:
        return 1.0
    score = (vix_close - _VIX_LOW) / (_VIX_HIGH - _VIX_LOW)
    return round(score, 4)


# --- Public API -----------------------------------------------------------------

def read_market_regime_inputs(
    *,
    lookback_days: int = _LOOKBACK_DAYS,
    _download_fn=None,   # injection point for tests
) -> tuple[RegimeInput, str]:
    """Download SPY/QQQ/VIX and return (RegimeInput, source_label).

    Falls back to (DRY_RUN_INPUTS, 'yfinance_error') on any failure.
    This function never raises.
    """
    try:
        import yfinance as yf  # deferred import — not installed everywhere
    except ImportError:
        logger.warning("yfinance not installed; using synthetic fallback.")
        return DRY_RUN_INPUTS, SOURCE_FALLBACK

    download = _download_fn if _download_fn is not None else yf.download

    # --- Fetch trend tickers (SPY, QQQ) ---
    try:
        trend_data = download(
            list(_TREND_TICKERS),
            period=f"{lookback_days}d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if trend_data is None or trend_data.empty:
            logger.warning("No trend data returned from yfinance.")
            return DRY_RUN_INPUTS, SOURCE_FALLBACK

        trend_prices: dict[str, list[float]] = {}
        close_col = "Close"
        for ticker in _TREND_TICKERS:
            try:
                # Multi-ticker download returns MultiIndex columns
                if hasattr(trend_data.columns, "levels"):
                    col = (close_col, ticker)
                    series = trend_data[col].dropna()
                else:
                    series = trend_data[close_col].dropna()
                trend_prices[ticker] = [float(v) for v in series.tolist()]
            except Exception as exc:
                logger.warning("Cannot extract %s closes: %s", ticker, exc)

        trend_score = _compute_trend_score(trend_prices)
        if trend_score is None:
            logger.warning("Could not compute trend score; using fallback.")
            return DRY_RUN_INPUTS, SOURCE_FALLBACK

    except Exception as exc:
        logger.warning("Trend data download failed: %s", exc)
        return DRY_RUN_INPUTS, SOURCE_FALLBACK

    # --- Fetch VIX ---
    try:
        vix_data = download(
            _VOL_TICKER,
            period=f"{lookback_days}d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if vix_data is None or vix_data.empty:
            logger.warning("No VIX data returned; using fallback.")
            return DRY_RUN_INPUTS, SOURCE_FALLBACK

        close_col = "Close"
        if hasattr(vix_data.columns, "levels"):
            vix_series = vix_data[(close_col, _VOL_TICKER)].dropna()
        else:
            vix_series = vix_data[close_col].dropna()

        if vix_series.empty:
            logger.warning("VIX close series empty; using fallback.")
            return DRY_RUN_INPUTS, SOURCE_FALLBACK

        vix_close = float(vix_series.iloc[-1])
        volatility_score = _compute_volatility_score(vix_close)

    except Exception as exc:
        logger.warning("VIX data download failed: %s", exc)
        return DRY_RUN_INPUTS, SOURCE_FALLBACK

    # --- Build and validate RegimeInput ---
    try:
        inputs = RegimeInput(trend_score=trend_score, volatility_score=volatility_score)
        inputs.validate()
    except Exception as exc:
        logger.warning("RegimeInput validation failed: %s", exc)
        return DRY_RUN_INPUTS, SOURCE_FALLBACK

    logger.info(
        "Market data loaded: trend=%.4f vol=%.4f (vix_close=%.2f)",
        trend_score,
        volatility_score,
        vix_close,
    )
    return inputs, SOURCE_YFINANCE
