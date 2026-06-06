import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from core.data_fetcher import DataFetcher
from core.market_scanner import MarketScanner
from core.notifier import Notifier

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except:
    VADER_AVAILABLE = False

class EntryEngine:

    def __init__(self):
        self.fetcher  = DataFetcher()
        self.scanner  = MarketScanner()
        self.notifier = Notifier()
        if VADER_AVAILABLE:
            self.analyzer = SentimentIntensityAnalyzer()

    # ──────────────────────────────────────────────
    # בדיקת סנטימנט חדשות (NS1)
    # ──────────────────────────────────────────────
    def check_news_sentiment(self, ticker_symbol):
        try:
            if not VADER_AVAILABLE:
                return True

            import yfinance as yf
            stock = yf.Ticker(ticker_symbol)
            news  = stock.news

            if not news:
                return True

            cutoff = datetime.now() - timedelta(hours=NEWS_LOOKBACK_HOURS)

            for article in news:
                pub_time = datetime.fromtimestamp(article.get("providerPublishTime", 0))
                if pub_time < cutoff:
                    continue

                title     = article.get("title", "")
                sentiment = self.analyzer.polarity_scores(title)

                if sentiment["compound"] < NEWS_BEARISH_THRESHOLD:
                    self.notifier.send(
                        f"[{ticker_symbol}] חדשות שליליות: {title}",
                        "WARNING"
                    )
                    return False

            return True

        except Exception as e:
            return True

    # ──────────────────────────────────────────────
    # בדיקת RVOL תוך-יומי
    # ──────────────────────────────────────────────
    def check_intraday_rvol(self, ticker_symbol, df):
        try:
            rvol = self.fetcher.get_rvol(ticker_symbol, df, intraday=True)
            if rvol is None:
                return False, 0

            # קביעת סף RVOL לפי גודל מניה
            import yfinance as yf
            market_cap = yf.Ticker(ticker_symbol).info.get("marketCap", 0)
            if market_cap and market_cap < SMALL_CAP_THRESHOLD:
                threshold = MIN_RVOL_ENTRY_SMALL
            else:
                threshold = MIN_RVOL_ENTRY

            return rvol >= threshold, rvol
        except Exception:
            return False, 0

    # ──────────────────────────────────────────────
    # בדיקת פריצת Pivot
    # ──────────────────────────────────────────────
    def check_pivot_breakout(self, df, pivot):
        try:
            current_price = df["Close"].iloc[-1]

            if current_price < pivot:
                return False, current_price

            # Gap-Up Rule — פסילה אם פריצה של 5%+ מעל הפיבוט
            gap_pct = (current_price - pivot) / pivot
            if gap_pct > 0.05:
                self.notifier.send(
                    f"Gap-Up חריג: {gap_pct:.1%} מעל פיבוט — סיכון גבוה",
                    "WARNING"
                )
                return False, current_price

            return True, current_price
        except Exception:
            return False, 0

    # ──────────────────────────────────────────────
    # בדיקת תאריך דוח רווחים
    # ──────────────────────────────────────────────
    def check_earnings(self, ticker_symbol, entry_price, current_price):
        try:
            import yfinance as yf
            stock    = yf.Ticker(ticker_symbol)
            calendar = stock.calendar

            if calendar is None or calendar.empty:
                return "NO_EARNINGS", 0

            earnings_date = calendar.iloc[0]["Earnings Date"]
            if hasattr(earnings_date, "date"):
                earnings_date = earnings_date.date()

            days_to_earnings = (earnings_date - datetime.now().date()).days

            if days_to_earnings > 21:
                return "SAFE", days_to_earnings

            # Run-up mode — בדיקת כרית רווח
            cushion = (current_price - entry_price) / entry_price

            if cushion < EARNINGS_CUSHION_PCT:
                return "SELL_BEFORE_EARNINGS", days_to_earnings
            else:
                return "HOLD_THROUGH_EARNINGS", days_to_earnings

        except Exception:
            return "UNKNOWN", 0

    # ──────────────────────────────────────────────
    # בדיקת Industry Diversification
    # ──────────────────────────────────────────────
    def check_industry_limit(self, ticker_symbol, open_positions):
        try:
            import yfinance as yf
            info     = yf.Ticker(ticker_symbol).info
            industry = info.get("industry", "Unknown")

            count = sum(
                1 for pos in open_positions
                if pos.get("industry") == industry
            )

            if count >= MAX_POSITIONS_PER_INDUSTRY:
                if not ALLOW_INDUSTRY_EXCEPTION:
                    self.notifier.send(
                        f"[{ticker_symbol}] וטו — כבר {count} פוזיציות ב-{industry}",
                        "WARNING"
                    )
                    return False, industry

            return True, industry

        except Exception:
            return True, "Unknown"

    # ──────────────────────────────────────────────
    # בדיקה מלאה לפני כניסה
    # ──────────────────────────────────────────────
    def evaluate_entry(self, ticker_symbol, pivot, open_positions=[]):
        try:
            df = self.fetcher.get_price_data(ticker_symbol)
            if df is None:
                return None

            # E1: בדיקת שוק כללי
            regime, vix, breadth = self.scanner.check_market_regime()
            if regime == "DEFENSE":
                self.notifier.send(f"שוק במצב הגנה — אין כניסות", "WARNING")
                return None

            # E2: בדיקת פריצת Pivot
            broke_pivot, current_price = self.check_pivot_breakout(df, pivot)
            if not broke_pivot:
                return None

            # E3: בדיקת RVOL
            rvol_ok, rvol = self.check_intraday_rvol(ticker_symbol, df)
            if not rvol_ok:
                self.notifier.send(
                    f"[{ticker_symbol}] פריצת שווא — RVOL נמוך: {rvol}",
                    "WARNING"
                )
                return None

            # NS1: בדיקת חדשות
            news_ok = self.check_news_sentiment(ticker_symbol)
            if not news_ok:
                return None

            # בדיקת Industry
            industry_ok, industry = self.check_industry_limit(
                ticker_symbol, open_positions
            )
            if not industry_ok:
                return None

            return {
                "ticker":        ticker_symbol,
                "price":         current_price,
                "pivot":         pivot,
                "rvol":          rvol,
                "regime":        regime,
                "vix":           vix,
                "industry":      industry
            }

        except Exception as e:
            self.notifier.send(f"[{ticker_symbol}] שגיאה: {e}", "WARNING")
            return None