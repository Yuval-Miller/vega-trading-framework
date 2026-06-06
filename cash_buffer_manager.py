import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *
from core.data_fetcher import DataFetcher
from core.notifier import Notifier


class CashBufferManager:

    def __init__(self):
        self.fetcher  = DataFetcher()
        self.notifier = Notifier()

    # ──────────────────────────────────────────────
    # בדיקת עתודת המזומן
    # ──────────────────────────────────────────────
    def check_buffer(self, current_balance_ils):
        try:
            usd_ils = self.fetcher.get_usd_ils_rate()
            if usd_ils is None:
                self.notifier.send("שגיאה במשיכת שער חליפין", "CRITICAL")
                return None

            self.notifier.send("=" * 50, "INFO")
            self.notifier.send("דוח עתודת מזומן", "INFO")
            self.notifier.send(f"תאריך: {datetime.now().strftime('%d/%m/%Y')}", "INFO")
            self.notifier.send(f"שער ILS/USD: {usd_ils:.4f}", "INFO")
            self.notifier.send(f"יעד עתודה: ₪{CASH_BUFFER_TARGET_ILS:,}", "INFO")
            self.notifier.send(f"יתרה נוכחית: ₪{current_balance_ils:,}", "INFO")

            gap_ils = CASH_BUFFER_TARGET_ILS - current_balance_ils

            if gap_ils <= 0:
                self.notifier.send("העתודה מלאה — אין צורך בפעולה", "SUCCESS")
                return {"status": "FULL", "gap_ils": 0}

            gap_usd = gap_ils / usd_ils

            self.notifier.send(f"פער: ₪{gap_ils:,.0f} (${gap_usd:,.0f})", "WARNING")
            self.notifier.send("=" * 50, "INFO")
            self.notifier.send("המלצת מאזן יבשה:", "INFO")
            self.notifier.send(
                f"נדרש: ${gap_usd:,.0f} מהתיק הכללי", "WARNING"
            )
            self.notifier.send(
                "ההחלטה היא שלך בלבד — המערכת לא מבצעת פעולה", "INFO"
            )

            return {
                "status":       "REPLENISH",
                "gap_ils":      round(gap_ils, 2),
                "gap_usd":      round(gap_usd, 2),
                "usd_ils_rate": round(usd_ils, 4)
            }

        except Exception as e:
            self.notifier.send(f"שגיאה בבדיקת עתודה: {e}", "CRITICAL")
            return None


if __name__ == "__main__":
    manager = CashBufferManager()

    current = float(input("הזן את יתרת העתודה הנוכחית בשקלים: "))
    manager.check_buffer(current)