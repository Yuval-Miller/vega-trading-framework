import yfinance as yf
import os
from datetime import datetime, timedelta

def download_ticker(ticker, breakout_date, out_dir="research/case_studies/winners"):
    os.makedirs(out_dir, exist_ok=True)
    end = datetime.strptime(breakout_date, "%Y-%m-%d") + timedelta(days=5)
    start = datetime.strptime(breakout_date, "%Y-%m-%d") - timedelta(days=400)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), auto_adjust=True)
    df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.index.name = "Date"
    df.reset_index().to_csv(f"{out_dir}/{ticker}.csv", index=False)
    print(f"Done → {out_dir}/{ticker}.csv")

if __name__ == "__main__":
    cases = [
        ("NVDA", "2023-05-25"),
        ("CELH", "2021-11-01"),
        ("CROX", "2021-07-15"),
        ("BOOT", "2021-09-01"),
        ("SMCI", "2023-05-26"),
    ]
    for ticker, breakout_date in cases:
        download_ticker(ticker, breakout_date)
