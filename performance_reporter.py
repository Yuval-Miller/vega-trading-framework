import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *
from core.sheets_connector import SheetsConnector
from core.notifier import Notifier


class PerformanceReporter:

    def __init__(self):
        self.sheets   = SheetsConnector()
        self.notifier = Notifier()

    # ──────────────────────────────────────────────
    # חישוב ביצועים
    # ──────────────────────────────────────────────
    def calculate_performance(self):
        try:
            records = self.sheets.read_all(SHEET_CLOSED)
            if not records:
                self.notifier.send("אין עסקאות סגורות עדיין", "INFO")
                return None

            trades     = []
            total_tax  = 0
            tax_shield = 0

            for r in records:
                try:
                    entry  = float(r.get("entry_price", 0))
                    exit_p = float(r.get("exit_price",  0))
                    shares = float(r.get("shares",      0))

                    if entry == 0 or exit_p == 0 or shares == 0:
                        continue

                    pnl = (exit_p - entry) * shares
                    trades.append({"pnl": pnl})

                    # מס פסיבי
                    if pnl > 0:
                        total_tax += pnl * TAX_RATE
                    else:
                        tax_shield += abs(pnl)

                except Exception:
                    continue

            if not trades:
                self.notifier.send("אין עסקאות תקינות לניתוח", "INFO")
                return None

            wins   = [t for t in trades if t["pnl"] > 0]
            losses = [t for t in trades if t["pnl"] <= 0]

            win_rate      = len(wins) / len(trades)
            total_pnl     = sum(t["pnl"] for t in trades)
            total_wins    = sum(t["pnl"] for t in wins)    if wins   else 0
            total_losses  = abs(sum(t["pnl"] for t in losses)) if losses else 0
            profit_factor = total_wins / total_losses if total_losses > 0 else 999

            # מס פסיבי
            net_taxable = max(0, total_pnl - tax_shield)
            net_tax     = net_taxable * TAX_RATE
            net_pnl     = total_pnl - net_tax

            return {
                "trades":         len(trades),
                "win_rate":       round(win_rate, 4),
                "profit_factor":  round(profit_factor, 2),
                "total_pnl":      round(total_pnl, 2),
                "tax_shield":     round(tax_shield, 2),
                "net_tax":        round(net_tax, 2),
                "net_pnl":        round(net_pnl, 2)
            }

        except Exception as e:
            self.notifier.send(f"שגיאה בחישוב ביצועים: {e}", "CRITICAL")
            return None

    # ──────────────────────────────────────────────
    # הצגת דוח
    # ──────────────────────────────────────────────
    def run_report(self):
        self.notifier.send("=" * 50, "INFO")
        self.notifier.send("דוח ביצועים רבעוני", "INFO")
        self.notifier.send(f"תאריך: {datetime.now().strftime('%d/%m/%Y')}", "INFO")

        perf = self.calculate_performance()

        if perf is None:
            return

        self.notifier.send(f"עסקאות: {perf['trades']}", "INFO")
        self.notifier.send(f"Win Rate: {perf['win_rate']:.1%}", "INFO")
        self.notifier.send(f"Profit Factor: {perf['profit_factor']}", "INFO")
        self.notifier.send(f"רווח גולמי: ${perf['total_pnl']:,.2f}", "INFO")
        self.notifier.send(f"מגן מס: ${perf['tax_shield']:,.2f}", "INFO")
        self.notifier.send(f"מס תיאורטי: ${perf['net_tax']:,.2f}", "INFO")
        self.notifier.send(f"רווח נטו: ${perf['net_pnl']:,.2f}", "SUCCESS")

        # המלצת הגדלת תקציב
        self.notifier.send("=" * 50, "INFO")
        self._scaling_recommendation(perf)

    # ──────────────────────────────────────────────
    # המלצת הגדלת תקציב
    # ──────────────────────────────────────────────
    def _scaling_recommendation(self, perf):
        try:
            win_rate_ok      = perf["win_rate"]     >= 0.50
            profit_factor_ok = perf["profit_factor"] >= 1.50

            if win_rate_ok and profit_factor_ok:
                self.notifier.send("המלצה: ניתן לשקול הגדלת תקציב", "SUCCESS")
                self.notifier.send(
                    f"תקציב נוכחי: ₪{PORTFOLIO_BUDGET_ILS:,}", "INFO"
                )

                answer = input("האם לאשר הגדלת תקציב? (Y/N): ")
                if answer.upper() == "Y":
                    new_budget = input("הזן תקציב חדש בשקלים: ")
                    try:
                        new_budget = float(new_budget)
                        self.notifier.send(
                            f"תקציב חדש: ₪{new_budget:,} — עדכן ב-config.py",
                            "SUCCESS"
                        )
                    except Exception:
                        self.notifier.send("קלט לא תקין", "WARNING")
            else:
                self.notifier.send(
                    "המלצה: אל תגדיל תקציב עדיין", "WARNING"
                )
                if not win_rate_ok:
                    self.notifier.send(
                        f"Win Rate נמוך מדי: {perf['win_rate']:.1%} (נדרש 50%+)",
                        "WARNING"
                    )
                if not profit_factor_ok:
                    self.notifier.send(
                        f"Profit Factor נמוך: {perf['profit_factor']} (נדרש 1.5+)",
                        "WARNING"
                    )

        except Exception as e:
            self.notifier.send(f"שגיאה בהמלצת תקציב: {e}", "WARNING")


if __name__ == "__main__":
    reporter = PerformanceReporter()
    reporter.run_report()