import yfinance as yf
import pandas as pd

TICKERS = ["HOPE", "BEN", "VISN", "RKLB", "NBIX", "AAON"]
PERIOD = "1y"

def fetch(ticker, auto_adjust):
    df = yf.download(ticker, period=PERIOD, auto_adjust=auto_adjust, progress=False)
    if df.empty:
        return None
    # flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close_col = "Close"
    price = float(df[close_col].iloc[-1])
    sma50 = float(df[close_col].rolling(50).mean().iloc[-1])
    sma200 = float(df[close_col].rolling(200).mean().iloc[-1])
    high52 = float(df["High"].max())
    low52 = float(df["Low"].min())
    return {"price": price, "sma50": sma50, "sma200": sma200, "high52": high52, "low52": low52}

def pct_diff(a, b):
    if b == 0:
        return float("nan")
    return (a - b) / b * 100

for ticker in TICKERS:
    t = fetch(ticker, True)
    f = fetch(ticker, False)
    if t is None or f is None:
        print(f"{ticker}: NO DATA")
        continue

    print(f"\n{'='*60}")
    print(f"  {ticker}")
    print(f"{'='*60}")
    print(f"{'Metric':<12} {'adj=True':>12} {'adj=False':>12} {'% diff':>10}")
    print(f"{'-'*48}")
    for key, label in [("price","Price"), ("sma50","SMA50"), ("sma200","SMA200"), ("high52","52W High"), ("low52","52W Low")]:
        tv, fv = t[key], f[key]
        diff = pct_diff(tv, fv)
        print(f"  {label:<10} {tv:>12.4f} {fv:>12.4f} {diff:>9.2f}%")
