import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

_obb = None


def _get_obb():
    global _obb
    if _obb is None:
        try:
            from openbb import obb as _openbb
            _obb = _openbb
        except ImportError:
            _obb = False
    return _obb if _obb is not False else None


class ProviderRouter:
    """
    Primary:  yfinance (direct, no auth)
    Fallback: OpenBB Platform v4 — rotates through yfinance → fmp → cboe providers.

    After _FAILURE_THRESHOLD consecutive yfinance failures the router switches to
    OpenBB for subsequent calls.  A successful OpenBB fetch resets the counter so
    yfinance is retried on the next call.
    """

    OPENBB_PROVIDERS = ["yfinance", "fmp", "cboe"]
    _FAILURE_THRESHOLD = 3

    def __init__(self):
        self._yf_failures = 0
        self._force_obb   = False

    # ── public interface ─────────────────────────────────────────────────────

    def get_price_data(self, ticker, days=400):
        """Return OHLCV DataFrame (yfinance Title Case columns) or None."""
        if not self._force_obb:
            df = self._yf_price(ticker, days)
            if df is not None:
                self._yf_failures = 0
                return df
            self._yf_failures += 1
            if self._yf_failures >= self._FAILURE_THRESHOLD:
                self._force_obb = True
                logger.warning(
                    f"yfinance failed {self._FAILURE_THRESHOLD} consecutive times "
                    f"— switching to OpenBB fallback"
                )
        return self._obb_price(ticker, days)

    def get_fundamentals(self, ticker):
        """Return fundamentals dict or None."""
        result = self._yf_fundamentals(ticker)
        if result is not None:
            return result
        return self._obb_fundamentals(ticker)

    # ── yfinance ─────────────────────────────────────────────────────────────

    def _yf_price(self, ticker, days):
        try:
            import yfinance as yf
            end   = datetime.today()
            start = end - timedelta(days=days)
            df    = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
            if df is None or df.empty:
                return None
            if not ticker.startswith("^"):
                df = df[df["Volume"] > 0]
            df = df[~df.index.duplicated(keep="last")]
            df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            df = df.sort_index()
            return df if not df.empty else None
        except Exception as e:
            logger.debug(f"[{ticker}] yfinance price: {e}")
            return None

    def _yf_fundamentals(self, ticker):
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            if not info:
                return None
            roe = info.get("returnOnEquity")
            if roe is None or (isinstance(roe, float) and pd.isna(roe)):
                return None
            return {
                "roe":            roe,
                "revenue_growth": info.get("revenueGrowth"),
                "eps_growth":     info.get("earningsGrowth"),
                "industry":       info.get("industry",  "Unknown"),
                "sector":         info.get("sector",    "Unknown"),
                "market_cap":     info.get("marketCap"),
                "beta":           info.get("beta"),
            }
        except Exception as e:
            logger.debug(f"[{ticker}] yfinance fundamentals: {e}")
            return None

    # ── OpenBB Platform v4 ───────────────────────────────────────────────────

    def _obb_price(self, ticker, days):
        obb = _get_obb()
        if obb is None:
            return None
        end   = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        for provider in self.OPENBB_PROVIDERS:
            try:
                result = obb.equity.price.historical(
                    symbol=ticker, start_date=start, end_date=end, provider=provider
                )
                df = result.to_df()
                if df is None or df.empty:
                    continue
                df = _normalize_price_df(df)
                if not df.empty:
                    logger.info(f"[{ticker}] OpenBB price via {provider}")
                    self._yf_failures = 0
                    self._force_obb   = False
                    return df
            except Exception as e:
                logger.debug(f"[{ticker}] OpenBB price [{provider}]: {e}")
        return None

    def _obb_fundamentals(self, ticker):
        obb = _get_obb()
        if obb is None:
            return None
        for provider in self.OPENBB_PROVIDERS:
            try:
                result = obb.equity.profile(symbol=ticker, provider=provider)
                df     = result.to_df()
                if df is None or df.empty:
                    continue
                row = df.iloc[0]
                fund = {
                    "roe":            _safe(row, ["return_on_equity", "roe"]),
                    "revenue_growth": _safe(row, ["revenue_growth", "revenue_growth_yoy"]),
                    "eps_growth":     _safe(row, ["eps_growth", "earnings_growth"]),
                    "industry":       _safe(row, ["industry"],   "Unknown") or "Unknown",
                    "sector":         _safe(row, ["sector"],     "Unknown") or "Unknown",
                    "market_cap":     _safe(row, ["market_cap",  "mktCap"]),
                    "beta":           _safe(row, ["beta"]),
                }
                if fund["roe"] is not None:
                    logger.info(f"[{ticker}] OpenBB fundamentals via {provider}")
                    return fund
            except Exception as e:
                logger.debug(f"[{ticker}] OpenBB fundamentals [{provider}]: {e}")
        return None


# ── helpers ──────────────────────────────────────────────────────────────────

def _normalize_price_df(df):
    """Map OpenBB lowercase column names to yfinance Title Case."""
    rename = {
        "open":   "Open",  "high":  "High",
        "low":    "Low",   "close": "Close",
        "volume": "Volume",
    }
    df = df.rename(columns=rename)
    needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    if not all(c in df.columns for c in ["Open", "High", "Low", "Close", "Volume"]):
        return pd.DataFrame()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=needed)
    df = df.sort_index()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


def _safe(row, keys, default=None):
    """Return first non-null value found in row for any of keys."""
    for k in keys:
        if k in row.index:
            val = row[k]
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
    return default
