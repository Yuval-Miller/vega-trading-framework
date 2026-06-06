import yfinance as yf
import pandas as pd

CANDIDATES = {
    # --- TRAPS ---
    "COIN":  ("2021-04-01", "2022-06-01"),
    "PLUG":  ("2020-06-01", "2021-06-01"),
    "RIVN":  ("2021-11-01", "2022-06-01"),
    "SPCE":  ("2021-01-01", "2022-01-01"),
    "UPST":  ("2021-01-01", "2022-06-01"),
}

def find_breakout(ticker, search_start, search_end):
    df = yf.download(ticker, start=search_start, end=search_end, auto_adjust=True, progress=False)
    if df.empty:
        print(f"{ticker} -> אין נתונים")
        return
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = df[["Open","High","Low","Close","Volume"]].dropna()
    pivot = df["High"].rolling(20).max().shift(1)
    vol_avg = df["Volume"].rolling(63).mean().shift(1)
    breakouts = []
    for i in range(63, len(df)):
        price = float(df["Close"].iloc[i])
        vol_today = float(df["Volume"].iloc[i])
        piv = float(pivot.iloc[i]) if not pd.isna(pivot.iloc[i]) else None
        avg_vol = float(vol_avg.iloc[i]) if not pd.isna(vol_avg.iloc[i]) else None
        if piv is None or avg_vol is None:
            continue
        if price > piv and vol_today > avg_vol * 1.5:
            breakouts.append({
                "date": df.index[i].date(),
                "close": round(price, 2),
                "vol_ratio": round(vol_today / avg_vol, 2),
                "pivot": round(piv, 2),
            })
    if breakouts:
        t0 = breakouts[0]
        print(f"{ticker} -> T-0: {t0['date']} | Close: {t0['close']} | Pivot: {t0['pivot']} | Vol: {t0['vol_ratio']}x")
    else:
        print(f"{ticker} -> לא נמצאה פריצה בחלון")

print("=" * 55)
for ticker, (s, e) in CANDIDATES.items():
    find_breakout(ticker, s, e)
