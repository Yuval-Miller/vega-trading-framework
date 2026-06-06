import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *
from trading_advisor import TradingAdvisor
from cash_buffer_manager import CashBufferManager
from performance_reporter import PerformanceReporter
from core.notifier import Notifier

def print_header():
    notifier = Notifier()
    notifier.send("=" * 50, "INFO")
    notifier.send("VEGA Trading System", "INFO")
    notifier.send(f"תאריך: {datetime.now().strftime('%d/%m/%Y %H:%M')}", "INFO")
    notifier.send("=" * 50, "INFO")

def get_full_watchlist():
    import requests
    import pandas as pd
    import os

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    all_tickers = []

    # תחנה 1 — קובץ מקומי (כל השוק)
    try:
        if os.path.exists("ticker_list.txt"):
            with open("ticker_list.txt", "r") as f:
                local = [line.strip() for line in f if line.strip()]
            all_tickers += local
            print(f"קובץ מקומי: {len(local)} מניות")
    except Exception as e:
        print(f"קובץ מקומי נכשל: {e}")

    # תחנה 2 — S&P500 מויקיפדיה (גיבוי)
    if len(all_tickers) < 100:
        try:
            tables = pd.read_html(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                storage_options={"User-Agent": headers["User-Agent"]}
            )
            sp500 = tables[0]["Symbol"].tolist()
            sp500 = [t.replace(".", "-") for t in sp500]
            all_tickers += sp500
            print(f"S&P500 גיבוי: {len(sp500)} מניות")
        except Exception as e:
            print(f"S&P500 נכשל: {e}")

    all_tickers = list(set(all_tickers))
    print(f"סהכ מניות לסריקה: {len(all_tickers)}")
    return all_tickers

def run_trading():
    print("\n" + "="*50)
    print("בחר סוג סריקה:")
    print("1 - FULL NIGHTLY SCAN (סריקה לילית מלאה)")
    print("2 - DAY SCAN (סריקה יומית על Watchlist בלבד)")
    print("="*50)
    
    scan_choice = input("הזן 1 או 2: ").strip()
    
    advisor = TradingAdvisor()
    
    if scan_choice == "1":
        print("\n--- RUNNING FULL NIGHTLY SCAN ---")
        print(f"טוען רשימת מניות...")
        watchlist = get_full_watchlist()
        advisor.run_night_scan(watchlist)
    elif scan_choice == "2":
        print("\n--- RUNNING DAY SCAN ---")
        advisor.run_day_scan()
    else:
        print("בחירה לא תקינה")

def run_cash_buffer():
    manager = CashBufferManager()
    current = float(input("הזן יתרת עתודה נוכחית בשקלים: "))
    manager.check_buffer(current)

def run_performance():
    reporter = PerformanceReporter()
    reporter.run_report()

def main():
    print_header()

    print("\nבחר מצב הפעלה:")
    print("1 — סריקת מסחר (לילית/יומית)")
    print("2 — בדיקת עתודת מזומן")
    print("3 — דוח ביצועים רבעוני")
    print("4 — הכל יחד")

    choice = input("\nהזן מספר (1/2/3/4): ").strip()

    if choice == "1":
        run_trading()
    elif choice == "2":
        run_cash_buffer()
    elif choice == "3":
        run_performance()
    elif choice == "4":
        run_trading()
        run_cash_buffer()
        run_performance()
    else:
        print("בחירה לא תקינה")

if __name__ == "__main__":
    main()