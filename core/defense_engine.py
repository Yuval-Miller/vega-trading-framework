import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from core.data_fetcher import DataFetcher
from core.notifier import Notifier

class DefenseEngine:

    def __init__(self):
        self.fetcher  = DataFetcher()
        self.notifier = Notifier()

    # ──────────────────────────────────────────────
    # עדכון סטופ לוס דינמי
    # ──────────────────────────────────────────────
    def update_stop_loss(self, position):
        try:
            ticker      = position["ticker"]
            entry_price = position["entry_price"]
            current_stop = position["stop_price"]

            df = self.fetcher.get_price_data(ticker)
            if df is None:
                return position

            current_price = df["Close"].iloc[-1]
            atr           = self.fetcher.get_atr(df)
            if atr is None:
                return position

            n         = atr.iloc[-1]
            new_stop  = current_stop

            # S1: בדיקת Hard Stop
            if current_price <= current_stop:
                self.notifier.send(
                    f"[{ticker}] סטופ לוס הופעל! מחיר: {current_price:.2f} | סטופ: {current_stop:.2f}",
                    "CRITICAL"
                )
                position["status"] = "STOP_HIT"
                return position

            # S2: Breakeven Rule
            if current_price >= entry_price + (BREAKEVEN_TRIGGER_N * n):
                if current_stop < entry_price:
                    new_stop = entry_price
                    self.notifier.stop_updated(ticker, current_stop, new_stop)

            # S3: Climax Sale
            daily_gain = (current_price - df["Close"].iloc[-2]) / df["Close"].iloc[-2]
            if daily_gain > 0.20:
                self.notifier.send(
                    f"[{ticker}] עלייה של {daily_gain:.1%} ביום אחד — שקול מכירה חלקית!",
                    "WARNING"
                )
                position["climax_alert"] = True

            # S4: Trailing Stop (SMA20)
            sma20 = df["Close"].rolling(20).mean().iloc[-1]
            if current_price < sma20:
                self.notifier.send(
                    f"[{ticker}] מחיר מתחת ל-SMA20 — שקול מכירה!",
                    "WARNING"
                )
                position["sma20_alert"] = True

            # עדכון סטופ אם השתנה
            if new_stop > current_stop:
                position["stop_price"]   = round(new_stop, 2)
                position["stop_updated"] = True
            else:
                position["stop_updated"] = False

            position["current_price"] = round(current_price, 2)
            position["pnl_pct"] = round(
                (current_price - entry_price) / entry_price, 4
            )

            return position

        except Exception as e:
            self.notifier.send(f"[{position.get('ticker')}] שגיאה: {e}", "WARNING")
            return position

    # ──────────────────────────────────────────────
    # בדיקת Portfolio Drawdown (KC3)
    # ──────────────────────────────────────────────
    def check_portfolio_drawdown(self, peak_equity, current_equity):
        try:
            if peak_equity <= 0:
                return False

            drawdown = (peak_equity - current_equity) / peak_equity

            if drawdown > 0.10:
                self.notifier.send(
                    f"Drawdown חצה 10%! ({drawdown:.1%}) — חתוך 50% מכל פוזיציה!",
                    "CRITICAL"
                )
                return True

            return False

        except Exception:
            return False

    # ──────────────────────────────────────────────
    # סריקת כל הפוזיציות הפתוחות
    # ──────────────────────────────────────────────
    def scan_open_positions(self, positions):
        try:
            updated    = []
            total_pnl  = 0

            for position in positions:
                updated_pos = self.update_stop_loss(position)
                updated.append(updated_pos)
                total_pnl += updated_pos.get("pnl_pct", 0)

            if updated:
                avg_pnl = total_pnl / len(updated)
                self.notifier.send(
                    f"סריקת פוזיציות הושלמה — {len(updated)} פוזיציות | ממוצע: {avg_pnl:.2%}",
                    "INFO"
                )

            return updated

        except Exception as e:
            self.notifier.send(f"שגיאה בסריקת פוזיציות: {e}", "WARNING")
            return positions