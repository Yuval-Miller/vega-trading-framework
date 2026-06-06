import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.data_fetcher import DataFetcher

def load_profile(csv_path: str, breakout_date: str) -> dict:
    df = pd.read_csv(csv_path)
    if "Date" not in df.columns and "Unnamed: 0" in df.columns:
        df = df.rename(columns={"Unnamed: 0": "Date"})
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    breakout_dt = pd.to_datetime(breakout_date)
    breakout_idx = df[df["Date"] <= breakout_dt].index[-1]

    start_idx = max(0, breakout_idx - 260)
    window = df.iloc[start_idx:breakout_idx + 1].copy()

    window["SMA20"]  = window["Close"].rolling(20).mean()
    window["SMA50"]  = window["Close"].rolling(50).mean()
    window["SMA150"] = window["Close"].rolling(150).mean()
    window["SMA200"] = window["Close"].rolling(200).mean()

    ticker = csv_path.split("/")[-1].replace(".csv", "")
    try:
        fundamentals = DataFetcher().get_fundamentals(ticker)
        eps_growth = fundamentals.get("eps_growth")
        rev_growth = fundamentals.get("revenue_growth")
    except Exception:
        eps_growth = None
        rev_growth = None

    return {
        "ticker":        ticker,
        "breakout_date": breakout_date,
        "df_full":       window,
        "setup_window":  window.iloc[-21:-1].copy(),
        "breakout_row":  window.iloc[-1].copy(),
        "eps_growth":    eps_growth,
        "rev_growth":    rev_growth,
    }

if __name__ == "__main__":
    profile = load_profile(
        "research/case_studies/winners/CELH.csv",
        breakout_date="2021-11-01"
    )
    sw  = profile["setup_window"]
    row = sw.iloc[-1]
    print(f"df_full rows: {len(profile['df_full'])}")
    print(f"Setup window: {sw['Date'].iloc[0].date()} -> {sw['Date'].iloc[-1].date()}")
    print(f"T-1 Close:    {row['Close']:.2f}")
    print(f"T-1 SMA200:   {row['SMA200']:.2f}")
    print(f"T-1 SMA150:   {row['SMA150']:.2f}")
