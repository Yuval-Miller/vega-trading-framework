import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research.compensation_engine import CompensationEngine

class BacktestEngine:

    def __init__(self):
        self.comp = CompensationEngine()

    def run_profile(self, profile: dict) -> dict:
        sw      = profile["setup_window"]   # T-20 עד T-1
        df_full = profile["df_full"]        # 260 יום
        t1_row  = sw.iloc[-1]
        ticker  = profile["ticker"]

        # ── חישוב מדדים גולמיים ──
        sma200_series = df_full["SMA200"].dropna()
        if len(sma200_series) >= 20:
            sma200_slope = float(np.polyfit(range(20), sma200_series.iloc[-20:], 1)[0])
        else:
            sma200_slope = 0.0

        avg_vol_63   = float(df_full["Volume"].iloc[-64:-1].mean())
        avg_vol_setup = float(sw["Volume"].mean())
        vol_dry_ratio = avg_vol_setup / avg_vol_63 if avg_vol_63 > 0 else 1.0
        sw_first_half = sw["Volume"].iloc[:10].mean()
        sw_second_half = sw["Volume"].iloc[10:].mean()
        internal_vol_trend = sw_second_half / sw_first_half if sw_first_half > 0 else 1.0

        ext20 = (t1_row["Close"] - t1_row["SMA20"]) / t1_row["SMA20"] if t1_row["SMA20"] > 0 else 1.0
        ext50 = (t1_row["Close"] - t1_row["SMA50"]) / t1_row["SMA50"] if t1_row["SMA50"] > 0 else 1.0

        high_52w  = df_full["High"].max()
        dist_high = (high_52w - t1_row["Close"]) / high_52w

        # VCP contractions — ספירה פשוטה בחלון setup
        highs = sw["High"].values
        vcp_c = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
        vcp_c = min(vcp_c // 3, 4)  # נורמליזציה גסה

        # base_days — אורך בסיס
        base_days = len(sw)

        # ── HARD dict ──
        hard = {
            "T1":         bool(t1_row["Close"] > t1_row["SMA200"]) if not pd.isna(t1_row["SMA200"]) else False,
            "T6":         sma200_slope >= 0,
            "gap_up":     0.0,
            "avg_vol":    avg_vol_63,
            "ext20":      ext20,
            "ext50":      ext50,
            "vcp_c":      vcp_c,
            "eps_growth": profile.get("eps_growth", 0.0),
        }

        # ── SOFT dict ──
        soft = {
            "T2":        bool(t1_row["Close"] > t1_row["SMA150"]) if not pd.isna(t1_row["SMA150"]) else False,
            "T4":        bool(t1_row["SMA50"]  > t1_row["SMA150"]) if not pd.isna(t1_row["SMA50"]) else False,
            "T5":        bool(t1_row["SMA150"] > t1_row["SMA200"]) if not pd.isna(t1_row["SMA150"]) else False,
            "dist_ok":   dist_high <= 0.15,
            "vol_dry_ok": vol_dry_ratio <= 0.75,
        }

        # ── TECHNICAL dict ──
        technical = {
            "vcp_c":        vcp_c,
            "vol_dry_ratio": vol_dry_ratio,
            "rs_63":        0.0,  # יתווסף בשלב הבא
            "base_days":    base_days,
            "ext20":        ext20,
            "internal_vol_trend": internal_vol_trend,
            "sma200_slope": sma200_slope,
        }

        result = self.comp.evaluate(hard, soft, technical)
        result["ticker"] = ticker

        # ── הדפסה ──
        print(f"\n{'='*55}")
        print(f"TICKER:  {ticker}")
        print(f"VERDICT: {result['verdict']}")
        print(f"{'='*55}")
        print(f"  T1={hard['T1']} | T6_slope={sma200_slope:.3f}")
        print(f"  T2={soft['T2']} T4={soft['T4']} T5={soft['T5']}")
        print(f"  ext20={ext20:.1%} ext50={ext50:.1%}")
        print(f"  VolDry={vol_dry_ratio:.2f} | Dist52W={dist_high:.1%} | Base={base_days}d")
        if result.get("violations"):
            print(f"  Violations:    {result['violations']}")
        if result.get("compensations"):
            print(f"  Compensations: {result['compensations']}")

        return result


if __name__ == "__main__":
    from research.profile_loader import load_profile

    cases = [
        ("research/case_studies/winners/NVDA.csv",  "2023-05-25"),
        ("research/case_studies/winners/CELH.csv",  "2021-11-01"),
        ("research/case_studies/winners/CROX.csv",  "2021-07-15"),
        ("research/case_studies/winners/BOOT.csv",  "2021-09-01"),
        ("research/case_studies/winners/SMCI.csv",  "2023-05-26"),
    ]

    engine = BacktestEngine()
    passed = 0
    for csv_path, breakout_date in cases:
        profile = load_profile(csv_path, breakout_date)
        result  = engine.run_profile(profile)
        if result["verdict"] in ("PASS", "WATCHLIST"):
            passed += 1

    print(f"\n{'='*55}")
    print(f"SUMMARY: {passed}/{len(cases)} winners passed or watchlisted")
    print(f"{'='*55}")
