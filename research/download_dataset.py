import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

WINNERS = {
    "CELH": "2020-11-05",
    "CROX": "2021-11-04",
    "BOOT": "2021-11-04",
    "SMCI": "2023-02-28",
    "ENPH": "2022-01-06",
    "AEHR": "2022-11-17",
    "GNRC": "2021-06-01",
    "LNTH": "2022-04-07",
    "IRTC": "2020-01-15",
    "INSP": "2021-08-04",
    "AXON": "2020-05-08",
    "MELI": "2020-05-06",
    "IBP":  "2021-10-27",
    "SITE": "2021-04-27",
    "PAYC": "2019-11-20",
    "APP":  "2023-05-11",
    "NVCR": "2019-06-13",
}

TRAPS = {}

OUTPUT_DIR = "research/case_studies"
os.makedirs(f"{OUTPUT_DIR}/winners", exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/traps", exist_ok=True)

def download_csv(ticker, breakout_date_str, subfolder):
    t0 = datetime.strptime(breakout_date_str, "%Y-%m-%d")
    start = t0 - timedelta(days=380)
    end   = t0 + timedelta(days=60)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if df.empty:
        print(f"{ticker} -> אין נתונים")
        return
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = df[["Open","High","Low","Close","Volume"]]
    path = f"{OUTPUT_DIR}/{subfolder}/{ticker}.csv"
    df.to_csv(path, index_label="Date")
    print(f"{ticker} -> {len(df)} rows saved to {path}")

print("Downloading WINNERS...")
for ticker, date in WINNERS.items():
    download_csv(ticker, date, "winners")

print("Downloading TRAPS...")
for ticker, date in TRAPS.items():
    download_csv(ticker, date, "traps")

print("Done.")
