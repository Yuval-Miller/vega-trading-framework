import pandas as pd

cases = [
    ("CELH", "2021-11-01"),
    ("CROX", "2021-07-15"),
    ("BOOT", "2021-09-01"),
    ("MSCI", "2023-06-01"),
]

for ticker, date in cases:
    df = pd.read_csv(f"research/case_studies/winners/{ticker}.csv", parse_dates=["Date"])
    row = df[df["Date"] <= date].iloc[-1]
    print(f"{ticker} | {row['Date'].date()} | Close={row['Close']:.2f}")
