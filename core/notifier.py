import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *

class Notifier:

    def __init__(self):
        self.channels = ["console"]

    def _timestamp(self):
        return datetime.now().strftime("%d/%m/%Y %H:%M")

    def send(self, message, level="INFO"):
        timestamp = self._timestamp()

        if level == "INFO":
            prefix = "ℹ️"
        elif level == "WARNING":
            prefix = "⚠️"
        elif level == "SUCCESS":
            prefix = "✅"
        elif level == "CRITICAL":
            prefix = "🚨"
        else:
            prefix = "📢"

        full_message = f"{prefix} [{timestamp}] {message}"
        print(full_message)

    def buy_signal(self, ticker, entry, stop, quantity, risk):
        self.send("─" * 50, "INFO")
        self.send(f"איתות כניסה חדש!", "SUCCESS")
        self.send(f"מניה:        {ticker}", "SUCCESS")
        self.send(f"מחיר כניסה:  ${entry}", "SUCCESS")
        self.send(f"סטופ לוס:    ${stop}", "SUCCESS")
        self.send(f"כמות:        {quantity} מניות", "SUCCESS")
        self.send(f"סיכון:       ₪{risk}", "SUCCESS")
        self.send("─" * 50, "INFO")

    def stop_updated(self, ticker, old_stop, new_stop):
        self.send("─" * 50, "WARNING")
        self.send(f"⚡ סטופ לוס עודכן!", "WARNING")
        self.send(f"מניה:        {ticker}", "WARNING")
        self.send(f"סטופ ישן:    ${old_stop}", "WARNING")
        self.send(f"סטופ חדש:    ${new_stop}", "WARNING")
        self.send("עדכן בברוקר עכשיו!", "WARNING")
        self.send("─" * 50, "WARNING")

    def earnings_alert(self, ticker, cushion_pct):
        self.send("─" * 50, "CRITICAL")
        self.send(f"התראת דוח רווחים!", "CRITICAL")
        self.send(f"מניה:        {ticker}", "CRITICAL")
        self.send(f"כרית רווח:   {cushion_pct:.1%}", "CRITICAL")
        if cushion_pct < EARNINGS_CUSHION_PCT:
            self.send("כרית מתחת ל-7% — מכור לפני סגירה היום!", "CRITICAL")
        self.send("─" * 50, "CRITICAL")

    def market_status(self, regime, vix, breadth):
        self.send("─" * 50, "INFO")
        self.send(f"סטטוס שוק:", "INFO")
        self.send(f"משטר שוק:   {regime}", "INFO")
        self.send(f"VIX:         {vix}", "INFO")
        self.send(f"Breadth:     {breadth}", "INFO")
        self.send("─" * 50, "INFO")