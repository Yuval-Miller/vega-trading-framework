"""
ml_validator.py — VCP Golden Pattern Analyzer
Research Engine | VEGA Framework
Run: python research/run_ml_validation.py
"""

import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sklearn.tree import DecisionTreeClassifier, export_text
import warnings
warnings.filterwarnings("ignore")

# ── DATASET ───────────────────────────────────────────────────────
DATASET = [
    {"ticker":"CELH",  "breakout":"2023-01-12","label":1,"is_mega":False},
    {"ticker":"CROX",  "breakout":"2021-11-04","label":1,"is_mega":False},
    {"ticker":"BOOT",  "breakout":"2021-11-05","label":1,"is_mega":False},
    {"ticker":"SMCI",  "breakout":"2024-02-01","label":1,"is_mega":False},
    {"ticker":"GNRC",  "breakout":"2021-06-01","label":1,"is_mega":False},
    {"ticker":"NVDA",  "breakout":"2023-05-25","label":1,"is_mega":False},
    {"ticker":"PLTR",  "breakout":"2024-02-06","label":1,"is_mega":False},
    {"ticker":"VRT",   "breakout":"2024-03-14","label":1,"is_mega":False},
    {"ticker":"AXON",  "breakout":"2023-09-07","label":1,"is_mega":False},
    {"ticker":"ORCL",  "breakout":"2023-09-12","label":1,"is_mega":False},
    {"ticker":"CRWD",  "breakout":"2024-02-21","label":1,"is_mega":False},
    {"ticker":"META",  "breakout":"2023-02-02","label":1,"is_mega":True},
    {"ticker":"LLY",   "breakout":"2023-05-04","label":1,"is_mega":True},
    {"ticker":"GOOGL", "breakout":"2023-07-25","label":1,"is_mega":True},
    {"ticker":"LCID",  "breakout":"2021-11-15","label":0,"is_mega":False},
    {"ticker":"RIDE",  "breakout":"2021-06-28","label":0,"is_mega":False},
    {"ticker":"PLUG",  "breakout":"2021-01-26","label":0,"is_mega":False},
    {"ticker":"SPCE",  "breakout":"2021-02-01","label":0,"is_mega":False},
    {"ticker":"AFRM",  "breakout":"2021-11-04","label":0,"is_mega":False},
]

FEATURES = [
    "sma20_slope","dist_from_52h","price_vs_sma150",
    "n_contractions","vol_dry_ratio","weekly_vol_tight",
    "rs_63","rs_126","rvol_avg","eps_growth","ext_from_sma20"
]

# ── FEATURE EXTRACTION ────────────────────────────────────────────
def extract_features(ticker: str, breakout_str: str) -> dict | None:
    import yfinance as yf
    breakout = pd.Timestamp(breakout_str)
    start = breakout - pd.Timedelta(days=380)

    try:
        df = yf.download(ticker, start=start, end=breakout,
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 60:
            print(f"  [{ticker}] Insufficient data ({len(df) if df is not None else 0} rows)")
            return None

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        high   = df["High"].squeeze()

        sma20  = close.rolling(20).mean()
        sma150 = close.rolling(150).mean()

        # Feature 1: SMA20 slope
        sma20_w = sma20.iloc[-20:]
        x = np.arange(len(sma20_w))
        slope = np.polyfit(x, sma20_w.values, 1)[0]
        sma20_slope = slope / sma20_w.mean()

        # Feature 2: Distance from 52W high
        high_52w = high.iloc[-252:].max()
        dist_from_52h = (high_52w - close.iloc[-1]) / high_52w

        # Feature 3: Price vs SMA150
        price_vs_sma150 = close.iloc[-1] / sma150.iloc[-1] if sma150.iloc[-1] > 0 else np.nan

        # Feature 4: VCP contractions
        df120 = df.iloc[-120:]
        n_contractions = _count_contractions(
            df120["High"].squeeze(), df120["Low"].squeeze(), window=7)

        # Feature 5: Volume dry-up — lowest institutional accumulation signal
        avg_vol_50 = volume.iloc[-50:].mean()
        if avg_vol_50 > 0:
            min_1d = float(volume.iloc[-20:].min() / avg_vol_50)
            rolling3 = volume.iloc[-20:].rolling(3).mean()
            min_3d = float(rolling3.min() / avg_vol_50)
            vol_dry_ratio = min(min_1d, min_3d)
        else:
            vol_dry_ratio = np.nan

        # Feature 6: Weekly volatility tightness
        close_w = close.iloc[-20:]
        weekly_ranges = []
        for i in range(0, min(20, len(close_w)-4), 5):
            w = close_w.iloc[i:i+5]
            if len(w) >= 3:
                weekly_ranges.append((w.max()-w.min())/w.mean())
        weekly_vol_tight = float(np.std(weekly_ranges)) if weekly_ranges else np.nan

        # Features 7 & 8: RS vs SPY
        spy = yf.download("SPY", start=start, end=breakout,
                          progress=False, auto_adjust=True)
        spy_close = spy["Close"].squeeze()
        aligned = pd.concat([close, spy_close], axis=1, join="inner")
        aligned.columns = ["stock","spy"]
        if len(aligned) >= 126:
            rs_63  = float((aligned["stock"].iloc[-1]/aligned["stock"].iloc[-63]) -
                           (aligned["spy"].iloc[-1]/aligned["spy"].iloc[-63]))
            rs_126 = float((aligned["stock"].iloc[-1]/aligned["stock"].iloc[-126]) -
                           (aligned["spy"].iloc[-1]/aligned["spy"].iloc[-126]))
        else:
            rs_63 = rs_126 = np.nan

        # Feature 9: Average RVOL
        avg_vol_base = volume.iloc[-63:-20].mean()
        rvol_window  = volume.iloc[-20:-5]
        rvol_avg = float((rvol_window / avg_vol_base).mean()) if avg_vol_base > 0 else np.nan

        # Feature 10: EPS growth
        try:
            info = yf.Ticker(ticker).info
            eps_growth = info.get("earningsGrowth", np.nan)
            if eps_growth is None:
                eps_growth = np.nan
        except Exception:
            eps_growth = np.nan

        # Feature 11: Extension from SMA20
        ext_from_sma20 = float(close.iloc[-1] / sma20.iloc[-1] - 1) if sma20.iloc[-1] > 0 else np.nan

        eps_val = float(eps_growth) if eps_growth is not None and not (isinstance(eps_growth, float) and np.isnan(eps_growth)) else np.nan

        return {
            "ticker":           ticker,
            "sma20_slope":      round(float(sma20_slope), 4),
            "dist_from_52h":    round(float(dist_from_52h), 4),
            "price_vs_sma150":  round(float(price_vs_sma150), 4),
            "n_contractions":   int(n_contractions),
            "vol_dry_ratio":    round(float(vol_dry_ratio), 4),
            "weekly_vol_tight": round(float(weekly_vol_tight), 4),
            "rs_63":            round(rs_63, 4),
            "rs_126":           round(rs_126, 4),
            "rvol_avg":         round(rvol_avg, 4),
            "eps_growth":       round(eps_val, 4) if not np.isnan(eps_val) else np.nan,
            "ext_from_sma20":   round(ext_from_sma20, 4),
        }

    except Exception as e:
        print(f"  [{ticker}] ERROR: {e}")
        return None


def _count_contractions(highs: pd.Series, lows: pd.Series, window: int = 7) -> int:
    swing_highs = []
    for i in range(window, len(highs) - window):
        if highs.iloc[i] == highs.iloc[i-window:i+window].max():
            swing_highs.append(float(highs.iloc[i]))
    contractions = 0
    for i in range(1, len(swing_highs)):
        if swing_highs[i] < swing_highs[i-1]:
            contractions += 1
    return contractions


# ── ML ANALYSIS ───────────────────────────────────────────────────
def run_analysis(rows: list, group_name: str = "MAIN"):
    print(f"\n{'='*60}")
    print(f"  ML VALIDATION — {group_name}")
    print(f"{'='*60}")

    df = pd.DataFrame(rows)
    labels     = df["label"].values
    tickers    = df["ticker"].values
    feature_df = df[FEATURES].copy()

    nan_counts = feature_df.isna().sum(axis=1)
    clean_mask = (nan_counts <= 3).values
    feature_df = feature_df[clean_mask]
    labels     = labels[clean_mask]
    tickers    = tickers[clean_mask]

    print(f"  Stocks: {len(tickers)} | Winners: {labels.sum()} | Traps: {(labels==0).sum()}")
    feature_df = feature_df.fillna(feature_df.median())

    X = feature_df.values
    y = labels

    clf = DecisionTreeClassifier(max_depth=4, min_samples_leaf=2, random_state=42)
    clf.fit(X, y)

    importances = clf.feature_importances_
    imp_df = pd.DataFrame({
        "Feature":     FEATURES,
        "Importance":  importances,
        "Winners_avg": [feature_df[f].values[y==1].mean() for f in FEATURES],
        "Traps_avg":   [feature_df[f].values[y==0].mean() for f in FEATURES],
    }).sort_values("Importance", ascending=False)

    print(f"\n  {'Feature':<20} {'Importance':>10} {'Winners':>10} {'Traps':>10} {'Signal':>8}")
    print(f"  {'─'*60}")
    for _, row in imp_df.iterrows():
        direction = "▲ W" if row["Winners_avg"] > row["Traps_avg"] else "▼ T"
        print(f"  {row['Feature']:<20} {row['Importance']:>10.3f} "
              f"{row['Winners_avg']:>10.3f} {row['Traps_avg']:>10.3f} {direction:>8}")

    print(f"\n  ── DECISION TREE RULES ──")
    for line in export_text(clf, feature_names=FEATURES).split("\n")[:25]:
        print(f"  {line}")

    print(f"\n  ── HARD RULE CONFIRMATION ──")
    _check_rule("H3 contractions>=2",    feature_df, y, lambda r: r["n_contractions"] >= 2)
    _check_rule("H6 ext_sma20<0.15",     feature_df, y, lambda r: r["ext_from_sma20"] < 0.15)
    _check_rule("S1 dist_52h<0.15",      feature_df, y, lambda r: r["dist_from_52h"] < 0.15)
    _check_rule("RS+ rs_63>0",           feature_df, y, lambda r: r["rs_63"] > 0)
    _check_rule("VOLDRY dry_ratio<0.65", feature_df, y, lambda r: r["vol_dry_ratio"] < 0.65)

    print(f"\n  Training accuracy: {clf.score(X, y):.1%} "
          f"(n={len(tickers)} — pattern descriptor, not predictor)\n")


def _check_rule(name, feature_df, y, condition):
    results = feature_df.apply(condition, axis=1).values
    w_pass = results[y==1].sum(); w_tot = int((y==1).sum())
    t_pass = results[y==0].sum(); t_tot = int((y==0).sum())
    if w_tot > 0 and t_tot > 0:
        verdict = "✅ HARD" if (w_pass/w_tot >= 0.8 and t_pass/t_tot <= 0.4) else \
                  "⚠️  SOFT" if (w_pass/w_tot >= 0.6) else "❌ WEAK"
    else:
        verdict = "⚠️  N/A"
    print(f"  {name:<28} W:{w_pass}/{w_tot}  T:{t_pass}/{t_tot}  {verdict}")


if __name__ == "__main__":
    print("Running standalone test on first 3 tickers...")
    rows = []
    for s in DATASET[:3]:
        print(f"Fetching {s['ticker']}...")
        f = extract_features(s["ticker"], s["breakout"])
        if f:
            f["label"] = s["label"]
            rows.append(f)
    if rows:
        run_analysis(rows, "QUICK TEST")