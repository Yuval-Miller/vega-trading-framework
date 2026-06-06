import pandas as pd
import numpy as np
import sys
import os
from datetime import timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from core.data_fetcher import DataFetcher

class MarketScanner:

    CATALYST_KEYWORDS = {
        "FDA":      ["fda", "approval", "approved", "trial", "phase", "clinical"],
        "CONTRACT": ["contract", "deal", "partnership", "awarded", "agreement"],
        "EARNINGS": ["earnings", "revenue", "beat", "eps", "profit", "guidance"],
        "HYPE":     ["soars", "surges", "moon", "reddit", "squeeze", "viral"],
    }

    def __init__(self):
        self.fetcher = DataFetcher()
        self._last_news = []

    def check_trend_template(self, df):
        try:
            close = df["Close"]
            sma20  = close.rolling(20).mean()
            sma50  = close.rolling(50).mean()
            sma150 = close.rolling(150).mean()
            sma200 = close.rolling(200).mean()
            current    = close.iloc[-1]
            cutoff_52w = df.index[-1] - timedelta(weeks=52)
            df_52w     = df[df.index >= cutoff_52w]
            high_52w   = df_52w["High"].max()
            low_52w    = df_52w["Low"].min()
            t1 = (current > sma20.iloc[-1] and current > sma50.iloc[-1] and
                  current > sma150.iloc[-1] and current > sma200.iloc[-1])
            t2 = sma150.iloc[-1] > sma200.iloc[-1]
            t3 = (sma200.iloc[-1] > sma200.iloc[-6]) and (sma200.iloc[-1] > sma200.iloc[-21])
            t4 = sma50.iloc[-1] > sma150.iloc[-1] and sma50.iloc[-1] > sma200.iloc[-1]
            t5 = ((current - low_52w) / low_52w) >= MIN_FROM_52W_LOW_PCT
            t6 = ((high_52w - current) / high_52w) <= MAX_FROM_52W_HIGH_PCT
            return t1 and t2 and t3 and t4 and t5 and t6
        except Exception:
            return False

    def check_vcp(self, df, _debug=False):
        try:
            df = df.iloc[-120:].copy()
            close  = df["Close"]
            volume = df["Volume"]
            returns_week  = close.pct_change().rolling(5).std().iloc[-1]
            returns_month = close.pct_change().rolling(20).std().iloc[-1]
            v2 = returns_week < returns_month
            v3 = returns_week <= VCP_MAX_VOLATILITY_WEEK
            avg_vol = volume.rolling(20).mean().iloc[-1]
            v4 = volume.iloc[-10:].min() < (avg_vol * VCP_VOLUME_DRY_PCT)
            contractions = self._count_contractions(df)
            v1 = VCP_MIN_CONTRACTIONS <= contractions <= VCP_MAX_CONTRACTIONS
            if _debug:
                print(f"  [VCP] contractions={contractions} v1={v1} | week_vol={returns_week:.4f} month_vol={returns_month:.4f} v2={v2} | v3(week<={VCP_MAX_VOLATILITY_WEEK})={v3} | min_vol_10={volume.iloc[-10:].min():.0f} avg_vol={avg_vol:.0f} dry_pct={VCP_VOLUME_DRY_PCT} v4={v4}")
            return v1 and v2 and v3 and v4
        except Exception:
            return False

    def _count_contractions(self, df):
        try:
            high   = df["High"].values
            window = VCP_SWING_WINDOW
            swings = []
            for i in range(window, len(high) - window):
                if high[i] == max(high[i-window:i+window+1]):
                    swings.append(high[i])
            if len(swings) < 2:
                return 0
            contractions = 0
            for i in range(1, len(swings)):
                if swings[i] < swings[i-1]:
                    contractions += 1
            return contractions
        except Exception:
            return 0

    def get_pivot(self, df):
        try:
            pivot_price = df["High"].iloc[-6:-1].max()
            return round(pivot_price + 0.01, 2)
        except Exception:
            return None

    def check_rs_rating(self, ticker_symbol):
        """
        Returns (passed: bool, rs_63: float, rs_126: float).
        passed=True only if stock outperforms SPY on BOTH 63-day and 126-day windows.
        rs values are percentage-point differences vs SPY (positive = outperforming).
        """
        try:
            import yfinance as yf
            import pandas as pd

            raw = yf.download([ticker_symbol, "SPY"], period="7mo",
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw["Close"]
            else:
                close = raw[["Close"]]

            if ticker_symbol not in close.columns or "SPY" not in close.columns:
                return False, None, None

            ticker_close = close[ticker_symbol].dropna()
            spy_close    = close["SPY"].dropna()
            combined     = pd.concat([ticker_close, spy_close], axis=1).dropna()
            combined.columns = ["ticker", "spy"]

            if len(combined) < 127:
                return False, None, None

            def period_return(series, days):
                return (series.iloc[-1] / series.iloc[-days] - 1) * 100

            ret_63_ticker  = period_return(combined["ticker"], 63)
            ret_63_spy     = period_return(combined["spy"],    63)
            ret_126_ticker = period_return(combined["ticker"], 126)
            ret_126_spy    = period_return(combined["spy"],    126)

            rs_63  = round(ret_63_ticker  - ret_63_spy,  2)
            rs_126 = round(ret_126_ticker - ret_126_spy, 2)

            passed = (rs_63 > 0) and (rs_126 > 0)
            return passed, rs_63, rs_126
        except Exception as e:
            return False, None, None

    def check_max_distance_from_high(self, df, max_pct=0.15):
        try:
            from datetime import timedelta
            cutoff = df.index[-1] - timedelta(weeks=52)
            high_52w = df[df.index >= cutoff]["High"].max()
            current  = float(df["Close"].iloc[-1])
            distance = (high_52w - current) / high_52w
            return distance <= max_pct, round(distance * 100, 2)
        except Exception:
            return False, None

    def check_monthly_volatility_cap(self, df, max_annualized=1.20, rs_63=None):
        try:
            if rs_63 is not None and rs_63 > 20:
                max_annualized = 1.50
            high   = df["High"].values
            window = VCP_SWING_WINDOW
            # find most recent swing high within last 60 bars
            lookback   = min(60, len(high) - window - 1)
            swing_idx  = None
            for i in range(len(high) - window - 1, len(high) - window - 1 - lookback, -1):
                if i < window:
                    break
                if high[i] == max(high[i - window:i + window + 1]):
                    swing_idx = i
                    break
            base_days = len(high) - 1 - swing_idx if swing_idx is not None else 15
            base_days = max(base_days, 2)  # need at least 2 returns to compute std
            returns    = df["Close"].pct_change().dropna()
            base_returns = returns.iloc[-base_days:]
            vol_base   = float(base_returns.std())
            annualized = vol_base * (252 ** 0.5)
            return annualized <= max_annualized, round(annualized * 100, 2), base_days
        except Exception:
            return False, None, None

    def check_extension_filter(self, df, max_ext=0.15):
        try:
            close = df["Close"].iloc[-1]
            sma20 = df["Close"].rolling(20).mean().iloc[-1]
            sma50 = df["Close"].rolling(50).mean().iloc[-1]
            ext20 = (close - sma20) / sma20
            ext50 = (close - sma50) / sma50
            if ext20 > max_ext:
                return False, f"ext20={ext20:.1%}"
            if ext50 > max_ext:
                return False, f"ext50={ext50:.1%}"
            return True, None
        except Exception:
            return False, "calc error"

    def check_sma150_extension_filter(self, df):
        try:
            close = df["Close"].iloc[-1]
            sma150 = df["Close"].rolling(150).mean().iloc[-1]
            print(f"  [H7 DEBUG] close={close:.4f}, sma150={sma150:.4f}, ratio={close/sma150:.4f}")
            if (close / sma150) > 1.82:
                return False, "H7: price >82% above SMA150"
            return True, "H7: OK"
        except Exception:
            return True, "H7: OK"

    def check_min_base_length(self, df, min_days=15):
        """
        Looks back from today and finds the most recent swing high using
        VCP_SWING_WINDOW. Base length = bars since that swing high was set.
        Stock must have been consolidating (below that high) for >= min_days.
        """
        try:
            high   = df["High"].values
            window = VCP_SWING_WINDOW
            last_swing_idx = None
            for i in range(len(high) - window - 1, window - 1, -1):
                if high[i] == max(high[i - window:i + window + 1]):
                    last_swing_idx = i
                    break
            if last_swing_idx is None:
                return False, 0
            base_days = len(high) - 1 - last_swing_idx
            return base_days >= min_days, base_days
        except Exception:
            return False, 0

    def check_fundamentals_filter(self, ticker_symbol, df):
        """
        Returns (passed: bool, reject_reason: str | None).
        Rejects if ANY condition is true:
          - EPS growth (TTM YoY) < -15%
          - RVOL (today vs 20d avg) < 0.75
          - Revenue growth Y/Y < -10%
        """
        try:
            fund = self.fetcher.get_fundamentals(ticker_symbol)
            reasons = []

            eps_growth = fund.get("eps_growth") if fund else None
            rev_growth = fund.get("revenue_growth") if fund else None

            if eps_growth is None and rev_growth is None:
                return True, "No fundamental data — manual review required"

            if eps_growth is not None and eps_growth < -0.15:
                reasons.append(f"EPS growth {eps_growth*100:.1f}% < -15%")

            avg_vol_63 = df["Volume"].iloc[-64:-1].mean()
            if avg_vol_63 < 200_000:
                reasons.append(f"avg vol {avg_vol_63:.0f} < 200k")

            if rev_growth is not None and rev_growth < -0.10:
                reasons.append(f"Revenue growth {rev_growth*100:.1f}% < -10%")

            if reasons:
                return False, " | ".join(reasons)
            return True, None
        except Exception as e:
            return False, f"error: {e}"

    def check_market_regime(self):
        try:
            market_data = self.fetcher.get_market_data()
            if market_data is None:
                return "UNKNOWN", 0, 0
            vix_df    = market_data["^VIX"]
            vix_val   = float(vix_df["Close"].iloc[-1])
            if vix_val > VIX_HIGH_RISK:
                regime = "DEFENSE"
            elif vix_val > VIX_CAUTION:
                regime = "HIGH_RISK"
            elif vix_val > VIX_NORMAL:
                regime = "CAUTION"
            else:
                regime = "NORMAL"
            spy_df    = market_data["SPY"]
            spy_sma50 = float(spy_df["Close"].rolling(50).mean().iloc[-1])
            spy_now   = float(spy_df["Close"].iloc[-1])
            if spy_now < spy_sma50:
                regime = "DEFENSE"
            breadth = self.fetcher.get_market_breadth()
            if breadth is None:
                breadth = 1.0
            if breadth < 1.0:
                regime = "DEFENSE"
            return regime, round(vix_val, 2), round(breadth, 2)
        except Exception:
            return "UNKNOWN", 0, 0

    def _get_sentiment_score(self, ticker_symbol):
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            import yfinance as yf
            from datetime import datetime, timedelta
            analyzer = SentimentIntensityAnalyzer()
            news     = yf.Ticker(ticker_symbol).news
            self._last_news = news if news else []
            if not news:
                return 0.0
            cutoff = datetime.now() - timedelta(hours=48)
            scores = []
            for article in news[:5]:
                pub_time = datetime.fromtimestamp(
                    article.get("providerPublishTime", 0)
                )
                if pub_time < cutoff:
                    continue
                title = article.get("title", "")
                score = analyzer.polarity_scores(title)["compound"]
                scores.append(score)
            if not scores:
                return 0.0
            return sum(scores) / len(scores)
        except Exception:
            return 0.0

    def _get_sentiment(self, ticker_symbol):
        try:
            score = self._get_sentiment_score(ticker_symbol)
            if score > 0.05:
                return "Positive"
            elif score < -0.05:
                return "Negative"
            else:
                return "Neutral"
        except Exception:
            return "Neutral"

    def _classify_catalyst(self, news: list) -> str:
        for article in news[:5]:
            title = article.get("title", "").lower()
            for label, keywords in self.CATALYST_KEYWORDS.items():
                if any(kw in title for kw in keywords):
                    return label
        return "NEUTRAL"

    def _generate_notes(self, df, current_price, avg_volume, ticker_symbol):
        try:
            notes  = []
            close  = df["Close"]
            volume = df["Volume"]
            sma20 = close.rolling(20).mean().iloc[-1]
            if current_price < sma20 * 1.02:
                notes.append("close to SMA20")
            if avg_volume < 750_000:
                notes.append("volume low")
            vol_week  = close.pct_change().rolling(5).std().iloc[-1]
            vol_month = close.pct_change().rolling(20).std().iloc[-1]
            if vol_week > vol_month * 0.9:
                notes.append("weekly volatility borderline")
            avg_vol_20 = volume.rolling(20).mean().iloc[-1]
            volume_dry = volume.iloc[-1] / avg_vol_20 if avg_vol_20 > 0 else 1
            vcp_tight  = vol_week <= VCP_MAX_VOLATILITY_WEEK * 0.7
            sentiment  = self._get_sentiment_score(ticker_symbol)
            catalyst   = self._classify_catalyst(self._last_news)
            if volume_dry < 0.5 and vcp_tight and sentiment > 0.05:
                return f"PERFECT SETUP - can place Buy Stop in advance | Catalyst:{catalyst}"
            if not notes:
                return f"all conditions met | Catalyst:{catalyst}"
            notes.append(f"Catalyst:{catalyst}")
            return " | ".join(notes)
        except Exception:
            return "could not calculate"

    def scan_ticker(self, ticker_symbol, counters=None):
        try:
            if counters is None:
                counters = {}
            print(f"Checking {ticker_symbol}...")
            df = self.fetcher.get_price_data(ticker_symbol)
            if df is None:
                print(f"  X {ticker_symbol} - no data")
                return None
            current_price = df["Close"].iloc[-1]
            if current_price < MIN_STOCK_PRICE:
                print(f"  X {ticker_symbol} - price too low: {current_price:.2f}")
                return None
            avg_volume = df["Volume"].iloc[-64:-1].mean()
            if avg_volume < MIN_AVG_VOLUME:
                print(f"  X {ticker_symbol} - volume too low: {avg_volume:.0f}")
                return None
            counters["passed_price_volume"] = counters.get("passed_price_volume", 0) + 1
            if not self.check_trend_template(df):
                print(f"  X {ticker_symbol} - failed Trend Template")
                return None
            counters["passed_trend"] = counters.get("passed_trend", 0) + 1
            rs_passed, rs_63, rs_126 = self.check_rs_rating(ticker_symbol)
            if not rs_passed:
                print(f"  X {ticker_symbol} - REJECTED_RS (63d: {rs_63}, 126d: {rs_126})")
                counters["rejected_rs"] = counters.get("rejected_rs", 0) + 1
                return None
            counters["passed_rs"] = counters.get("passed_rs", 0) + 1
            dist_ok, dist_pct = self.check_max_distance_from_high(df)
            if not dist_ok:
                print(f"  X {ticker_symbol} - REJECTED_DIST ({dist_pct}% below 52W High)")
                counters["rejected_dist"] = counters.get("rejected_dist", 0) + 1
                return None
            vol_ok, vol_ann, vol_base_days = self.check_monthly_volatility_cap(df, rs_63=rs_63)
            if not vol_ok:
                print(f"  X {ticker_symbol} - REJECTED_VOL ({vol_ann}% annualized, {vol_base_days}d base)")
                counters["rejected_vol"] = counters.get("rejected_vol", 0) + 1
                return None
            ext_ok, ext_reason = self.check_extension_filter(df)
            if not ext_ok:
                print(f"  X {ticker_symbol} - REJECTED_EXT ({ext_reason})")
                counters["rejected_ext"] = counters.get("rejected_ext", 0) + 1
                return None
            h7_ok, h7_reason = self.check_sma150_extension_filter(df)
            if not h7_ok:
                print(f"  X {ticker_symbol} - REJECTED_H7 ({h7_reason})")
                counters["rejected_h7"] = counters.get("rejected_h7", 0) + 1
                return None
            base_ok, base_days = self.check_min_base_length(df)
            if not base_ok:
                print(f"  X {ticker_symbol} - REJECTED_BASE ({base_days} days, need 15)")
                counters["rejected_base"] = counters.get("rejected_base", 0) + 1
                return None
            counters["passed_prefilters"] = counters.get("passed_prefilters", 0) + 1
            fund_ok, fund_reason = self.check_fundamentals_filter(ticker_symbol, df)
            if not fund_ok:
                print(f"  X {ticker_symbol} - REJECTED_FUND ({fund_reason})")
                counters["rejected_fund"] = counters.get("rejected_fund", 0) + 1
                return None
            counters["passed_fund"] = counters.get("passed_fund", 0) + 1
            if not self.check_vcp(df):
                print(f"  X {ticker_symbol} - failed VCP")
                counters["failed_vcp"] = counters.get("failed_vcp", 0) + 1
                return None
            pivot     = self.get_pivot(df)
            notes     = self._generate_notes(df, current_price, avg_volume, ticker_symbol)
            sentiment = self._get_sentiment(ticker_symbol)
            print(f"  PASS {ticker_symbol} - price: {current_price:.2f} | sentiment: {sentiment} | {notes}")
            return {
                "ticker":    ticker_symbol,
                "price":     round(current_price, 2),
                "pivot":     pivot,
                "avg_vol":   int(avg_volume),
                "notes":     notes,
                "sentiment": sentiment
            }
        except Exception as e:
            print(f"  X {ticker_symbol} - error: {e}")
            return None
