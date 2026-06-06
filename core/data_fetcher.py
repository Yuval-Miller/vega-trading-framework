import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from core.providers import ProviderRouter

logger = logging.getLogger(__name__)


class DataFetcher:

    def __init__(self):
        self.cache  = {}
        self.router = ProviderRouter()

    def get_price_data(self, ticker_symbol, days=400):
        try:
            time.sleep(0.1)
            df = self.router.get_price_data(ticker_symbol, days)
            if df is None or len(df) < 220:
                return None
            return df
        except Exception as e:
            logger.error(f"[{ticker_symbol}] שגיאה: {e}")
            return None

    def get_atr(self, df, period=20):
        try:
            if len(df) < period + 5:
                return None
            high  = df["High"]
            low   = df["Low"]
            close = df["Close"]
            tr1   = high - low
            tr2   = (high - close.shift(1)).abs()
            tr3   = (low  - close.shift(1)).abs()
            tr    = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr   = tr.ewm(alpha=1 / period, adjust=False).mean()
            return atr
        except Exception as e:
            logger.error(f"שגיאה בחישוב ATR: {e}")
            return None

    def get_rvol(self, ticker_symbol, df, intraday=False):
        try:
            avg_volume = df["Volume"].iloc[-31:-1].mean()
            if avg_volume == 0 or pd.isna(avg_volume):
                return None
            if not intraday:
                last_volume = df["Volume"].iloc[-1]
                if last_volume == 0:
                    last_volume = df["Volume"].iloc[-2]
                return round(last_volume / avg_volume, 2)
            else:
                now_israel  = datetime.now()
                market_open = now_israel.replace(
                    hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN,
                    second=0, microsecond=0
                )
                if now_israel < market_open:
                    return None
                minutes_passed = max((now_israel - market_open).seconds / 60, 1)
                stock         = yf.Ticker(ticker_symbol)
                intraday_data = stock.history(period="1d", interval="1m")
                if intraday_data is None or intraday_data.empty:
                    return None
                current_volume   = intraday_data["Volume"].sum()
                projected_volume = (current_volume / minutes_passed) * TRADING_DAY_MINUTES
                return round(projected_volume / avg_volume, 2)
        except Exception as e:
            logger.error(f"[{ticker_symbol}] שגיאה בחישוב RVOL: {e}")
            return None

    def get_market_data(self):
        try:
            result = {}
            for symbol in ["SPY", "QQQ", "^VIX"]:
                df = yf.Ticker(symbol).history(period="60d", auto_adjust=True)
                if df is None or df.empty:
                    return None
                if not symbol.startswith("^"):
                    df = df[df["Volume"] > 0]
                df = df[~df.index.duplicated(keep="last")]
                result[symbol] = df.dropna(subset=["Close"])
            return result
        except Exception as e:
            logger.error(f"שגיאה במשיכת נתוני שוק: {e}")
            return None

    def get_usd_ils_rate(self):
        try:
            ticker = yf.Ticker("ILS=X")
            rate   = ticker.fast_info["last_price"]
            if rate is None or rate <= 0:
                return None
            return rate
        except Exception as e:
            logger.error(f"שגיאה במשיכת שער חליפין: {e}")
            return None

    def get_fundamentals(self, ticker_symbol):
        try:
            result = self.router.get_fundamentals(ticker_symbol)
            if result is None:
                return None
            if result.get("beta") is None:
                result["beta"] = self._calculate_beta(ticker_symbol)
            return result
        except Exception as e:
            logger.error(f"[{ticker_symbol}] שגיאה בפונדמנטלים: {e}")
            return None

    def _calculate_beta(self, ticker_symbol, period_days=252):
        try:
            stock_data = yf.Ticker(ticker_symbol).history(period="1y")
            spy_data   = yf.Ticker("SPY").history(period="1y")
            if stock_data.empty or spy_data.empty:
                return None
            stock_ret = stock_data["Close"].pct_change().dropna()
            spy_ret   = spy_data["Close"].pct_change().dropna()
            aligned   = pd.concat([stock_ret, spy_ret], axis=1, join="inner")
            aligned.columns = ["stock", "spy"]
            if len(aligned) < 30:
                return None
            cov  = aligned["stock"].cov(aligned["spy"])
            var  = aligned["spy"].var()
            beta = cov / var if var != 0 else None
            return round(beta, 2) if beta else None
        except Exception as e:
            logger.error(f"[{ticker_symbol}] שגיאה בחישוב Beta: {e}")
            return None

    def get_market_breadth(self):
        # Primary: 11 SPDR sector ETFs above/below SMA50 — always liquid, reliable yfinance data
        # ^ADVN/^DECN return no data from yfinance
        try:
            sector_etfs = ["XLK","XLF","XLE","XLV","XLI","XLC","XLY","XLP","XLRE","XLB","XLU"]
            above = 0
            below = 0
            for sym in sector_etfs:
                try:
                    df = yf.Ticker(sym).history(period="60d", auto_adjust=True)
                    if df is None or len(df) < 50:
                        continue
                    sma50   = df["Close"].rolling(50).mean().iloc[-1]
                    current = df["Close"].iloc[-1]
                    if current > sma50:
                        above += 1
                    else:
                        below += 1
                except Exception:
                    continue
            if above + below == 0:
                return self._calculate_breadth_fallback()
            if below == 0:
                return 2.0
            return round(above / below, 2)
        except Exception:
            return self._calculate_breadth_fallback()

    def _calculate_breadth_fallback(self):
        try:
            sample = ["AAPL", "MSFT", "NVDA", "GOOGL", "META",
                      "AMZN", "JPM", "V", "MA", "AVGO"]
            above = 0
            below = 0
            for sym in sample:
                try:
                    df = yf.Ticker(sym).history(period="30d", auto_adjust=True)
                    if df is None or len(df) < 20:
                        continue
                    sma20   = df["Close"].rolling(20).mean().iloc[-1]
                    current = df["Close"].iloc[-1]
                    if current > sma20:
                        above += 1
                    else:
                        below += 1
                except Exception:
                    continue
            if below == 0:
                return 2.0
            return round(above / below, 2)
        except Exception:
            return 1.0
