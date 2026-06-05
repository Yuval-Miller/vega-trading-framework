import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yfinance as yf
from datetime import datetime, timedelta
from core.market_scanner import MarketScanner
from core.data_fetcher import DataFetcher

AUDIT_WINDOW_DAYS = 20
VOLUME_SPIKE_FACTOR = 1.4

WINNERS = ["ENPH","CELH","GNRC","CROX","DUOL","SMCI","AXON","NVDA","BOOT","AEHR"]
CONTROL = ["BYND","PTON","LCID","WISH","RIDE"]
ALL_TICKERS = WINNERS + CONTROL

def get_historical(ticker):
    end = datetime.today()
    start = end - timedelta(days=4*365)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
    if df.empty:
        return df
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[df["Volume"] > 0].copy()
    return df

def find_breakout_date(df):
    if len(df) < 280:
        return None
    for i in range(252, len(df)):
        prior_high = df.iloc[i-252:i]["High"].max()
        close = df.iloc[i]["Close"]
        vol = df.iloc[i]["Volume"]
        avg_vol = df.iloc[max(0,i-63):i]["Volume"].mean()
        if close > prior_high and vol >= avg_vol * VOLUME_SPIKE_FACTOR:
            return df.index[min(i+1, len(df)-1)]  # ← שינוי: i+1
    return None

def run_filters(ticker, df_full, breakout_date):
    idx = df_full.index.get_loc(breakout_date)
    df = df_full.iloc[:idx].copy()
    df_vcp = df.iloc[-120:].copy()
    s = MarketScanner()
    f = DataFetcher()
    results = {}

    avg_vol = df.iloc[-20:]["Volume"].mean()
    results["H5_avg_volume"] = {"pass": avg_vol >= 200_000, "detail": f"avg_vol={avg_vol:,.0f}"}

    try:
        results["H1_trend_template"] = {"pass": s.check_trend_template(df), "detail": "T1-T6"}
    except Exception as e:
        results["H1_trend_template"] = {"pass": False, "detail": f"ERROR:{e}"}
    try:
        sma150 = df["Close"].rolling(150).mean()
        sma150_prev = sma150.iloc[-20]
        sma150_curr = sma150.iloc[-1]
        price = df["Close"].iloc[-1]
        stage2 = (price > sma150_curr) and (sma150_curr > sma150_prev)
        results["H2_stage2"] = {"pass": stage2, "detail": f"price={price:.2f} sma150={sma150_curr:.2f} rising={sma150_curr > sma150_prev}"}
    except Exception as e:
        results["H2_stage2"] = {"pass": False, "detail": f"ERROR:{e}"}
    try:
        results["RS_rating"] = {"pass": s.check_rs_rating(ticker), "detail": "63d+126d vs SPY"}
    except Exception as e:
        results["RS_rating"] = {"pass": False, "detail": f"ERROR:{e}"}

    try:
        results["S1_distance_52w"] = {"pass": s.check_max_distance_from_high(df), "detail": "≤15% below 52W high"}
    except Exception as e:
        results["S1_distance_52w"] = {"pass": False, "detail": f"ERROR:{e}"}

    try:
        results["S2_vol_cap"] = {"pass": s.check_monthly_volatility_cap(df), "detail": "≤120% monthly vol"}
    except Exception as e:
        results["S2_vol_cap"] = {"pass": False, "detail": f"ERROR:{e}"}

    try:
        results["S3_base_length"] = {"pass": s.check_min_base_length(df), "detail": "≥15 days"}
    except Exception as e:
        results["S3_base_length"] = {"pass": False, "detail": f"ERROR:{e}"}

    try:
        results["S4_fundamentals"] = {"pass": s.check_fundamentals_filter(ticker, df), "detail": "EPS+vol+rev"}
    except Exception as e:
        results["S4_fundamentals"] = {"pass": False, "detail": f"ERROR:{e}"}

    try:
        fund = f.get_fundamentals(ticker)
        eps_growth = fund.get("eps_growth", 0) if fund else 0
        hyper_growth = eps_growth is not None and eps_growth > 0.30
        contractions = s._count_contractions(df_vcp)
        avg_vol_vcp = df_vcp["Volume"].rolling(20).mean().iloc[-1]
        v1 = 2 <= contractions <= 4
        v4 = df_vcp["Volume"].iloc[-10:].min() < (avg_vol_vcp * 0.75)
        if hyper_growth:
            detail = f"c={contractions} HYPER-GROWTH bypass eps={eps_growth:.0%}"
            results["H3_vcp"] = {"pass": True, "detail": detail}
        else:
            detail = f"c={contractions} v1={v1} v4={v4}"
            results["H3_vcp"] = {"pass": v1 and v4, "detail": detail}
    except Exception as e:
        results["H3_vcp"] = {"pass": False, "detail": f"ERROR:{e}"}

    return results

def main():
    print("\n🔍 VEGA Data Footprint Audit v2\n")
    summary = {"winners_pass":[], "winners_fail":[], "control_caught":[], "control_missed":[]}

    for ticker in ALL_TICKERS:
        group = "WINNER" if ticker in WINNERS else "CONTROL"
        print(f"  Loading {ticker}...", end="", flush=True)

        df = get_historical(ticker)
        if df.empty or len(df) < 280:
            print(" ❌ insufficient data")
            continue

        bd = find_breakout_date(df)
        if bd is None:
            print(" ❌ no breakout found")
            continue

        print(f" breakout={bd.date()}")
        results = run_filters(ticker, df, bd)

        passed = sum(1 for v in results.values() if v["pass"])
        total = len(results)
        status = "✅ PASS" if passed == total else f"⚠️  {passed}/{total}"

        print(f"\n{'='*55}")
        print(f"  {ticker:6s} [{group}]  breakout={bd.date()}  {status}")
        print(f"{'='*55}")
        for name, r in results.items():
            icon = "✅" if r["pass"] else "❌"
            print(f"  {icon}  {name:<25s} {r['detail']}")

        all_pass = all(v["pass"] for v in results.values())
        if group == "WINNER":
            (summary["winners_pass"] if all_pass else summary["winners_fail"]).append(ticker)
        else:
            (summary["control_caught"] if not all_pass else summary["control_missed"]).append(ticker)

    print(f"\n{'='*55}")
    print("  AUDIT SUMMARY")
    print(f"{'='*55}")
    print(f"  Winners passed    : {summary['winners_pass']} ({len(summary['winners_pass'])}/10)")
    print(f"  Winners rejected  : {summary['winners_fail']}")
    print(f"  Control caught    : {summary['control_caught']} ({len(summary['control_caught'])}/5)")
    print(f"  Control MISSED    : {summary['control_missed']} ← matrix gap")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()
