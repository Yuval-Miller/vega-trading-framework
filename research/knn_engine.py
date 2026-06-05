import numpy as np
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research.profile_loader import load_profile

# ── Reference dataset (7 certified winners) ──────────────────────────────────
_WINNERS_META = [
    ("CELH", "2020-11-05", 0.80),
    ("CROX", "2021-11-04", 4.29),
    ("BOOT", "2021-10-29", 3.50),
    ("SMCI", "2023-02-28", 5.56),
    ("AEHR", "2022-11-17", 0.42),
    ("GNRC", "2021-06-01", 0.805),
    ("SITE", "2021-04-27", 0.673),
]

FEATURE_NAMES = [
    "dist_52w",
    "vol_dry_ratio",
    "ext_sma20",
    "ext_sma50",
    "base_length",
    "t6_slope",
    "contraction_count",
    "eps_growth",
]


# ── Feature extraction ────────────────────────────────────────────────────────

def _extract_features(profile: dict) -> np.ndarray:
    sw      = profile["setup_window"]   # T-20 to T-1, 20 rows
    df_full = profile["df_full"]        # 260-day window with SMA columns
    t1      = sw.iloc[-1]
    eps     = float(profile.get("eps_growth") or 0.0)
    eps = min(eps, 6.0)

    close    = float(t1["Close"])
    sma20    = float(t1["SMA20"])
    sma50    = float(t1["SMA50"])

    # Distance from 52W high
    high_52w  = float(df_full["High"].max())
    dist_52w  = (high_52w - close) / high_52w if high_52w > 0 else 0.0

    # Volume dry-up ratio (setup avg / 63-bar baseline)
    avg_vol_63    = float(df_full["Volume"].iloc[-64:-1].mean())
    avg_vol_setup = float(sw["Volume"].mean())
    vol_dry_ratio = avg_vol_setup / avg_vol_63 if avg_vol_63 > 0 else 1.0

    # Extension from SMA20 / SMA50
    ext_sma20 = (close - sma20) / sma20 if sma20 > 0 else 0.0
    ext_sma50 = (close - sma50) / sma50 if sma50 > 0 else 0.0

    # Base length (setup window rows)
    base_length = float(len(sw))

    # SMA200 slope — Wilder direction indicator (T6)
    sma200_vals = df_full["SMA200"].dropna()
    if len(sma200_vals) >= 20:
        t6_slope = float(np.polyfit(range(20), sma200_vals.iloc[-20:].values, 1)[0])
    else:
        t6_slope = 0.0

    # VCP contraction count (rough proxy over setup window)
    highs = sw["High"].values
    raw_c            = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])
    contraction_count = float(min(raw_c // 3, 4))

    return np.array(
        [dist_52w, vol_dry_ratio, ext_sma20, ext_sma50,
         base_length, t6_slope, contraction_count, eps],
        dtype=float,
    )


# ── KNN Engine ────────────────────────────────────────────────────────────────

class KNNEngine:
    """
    Scores a candidate setup profile against the 7 certified winner profiles
    using K=3 nearest-neighbour lookup in a min-max normalised feature space.
    """

    K = 3

    def __init__(self):
        self._tickers: list = []
        self._winner_matrix: np.ndarray = None
        self._min: np.ndarray = None
        self._scale: np.ndarray = None
        self._load_and_fit()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _load_and_fit(self):
        base = os.path.dirname(os.path.abspath(__file__))
        raw_vecs = []

        for ticker, breakout_date, eps_growth in _WINNERS_META:
            csv_path = os.path.join(
                base, "case_studies", "winners", f"{ticker}.csv"
            ).replace("\\", "/")
            profile = load_profile(csv_path, breakout_date)
            profile["eps_growth"] = eps_growth
            raw_vecs.append(_extract_features(profile))
            self._tickers.append(ticker)

        raw = np.array(raw_vecs)                     # (7, 8)
        self._min   = raw.min(axis=0)
        scale       = raw.max(axis=0) - self._min
        scale[scale == 0] = 1.0                      # constant feature → all zeros after norm
        self._scale = scale
        self._winner_matrix = self._normalize(raw)   # (7, 8) in [0,1]
        print(f"[KNNEngine] Loaded {len(self._tickers)} winners. Re-initialize after adding new winners.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _normalize(self, mat: np.ndarray) -> np.ndarray:
        return (mat - self._min) / self._scale

    # ── Public API ────────────────────────────────────────────────────────────

    def score_candidate(self, profile: dict, exclude: str = None) -> dict:
        """
        Score a candidate profile against the winners reference set.

        Parameters
        ----------
        profile : dict   Output of research.profile_loader.load_profile()
        exclude : str    Optional ticker to skip (used for leave-one-out self-test)

        Returns
        -------
        {"score": float,          # 0–100, higher = more similar to certified winners
         "neighbors": [           # top-K nearest winners
             {"rank": int, "ticker": str, "distance": float}, ...
         ]}
        """
        rows = profile.get("rows", 9999)
        if rows < 220:
            return {"score": 0, "neighbors": [], "reject_reason": f"IPO_GATE: only {rows} rows"}

        vec  = _extract_features(profile)
        norm = self._normalize(vec)

        if exclude:
            keep    = [t != exclude for t in self._tickers]
            ref_mat = self._winner_matrix[np.array(keep)]
            ref_lbl = [t for t, k in zip(self._tickers, keep) if k]
        else:
            ref_mat = self._winner_matrix
            ref_lbl = self._tickers

        k_eff     = min(self.K, len(ref_mat))
        distances = np.sqrt(((ref_mat - norm) ** 2).sum(axis=1))
        order     = np.argsort(distances)

        neighbors = [
            {"rank": i + 1, "ticker": ref_lbl[order[i]], "distance": round(float(distances[order[i]]), 4)}
            for i in range(k_eff)
        ]

        mean_k_dist = float(np.mean([n["distance"] for n in neighbors]))
        # Normalise against theoretical max in [0,1]^N space → sqrt(N)
        score = max(0.0, round(100.0 * (1.0 - mean_k_dist / float(np.sqrt(len(FEATURE_NAMES)))), 1))

        return {"score": score, "neighbors": neighbors}


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading KNNEngine (7 winners) …")
    engine = KNNEngine()

    print(f"\nFeature ranges (fitted on {len(engine._tickers)} winners):")
    col_w = max(len(n) for n in FEATURE_NAMES)
    for i, name in enumerate(FEATURE_NAMES):
        lo = engine._min[i]
        hi = engine._min[i] + engine._scale[i]
        print(f"  {name:{col_w}s}: [{lo:.4f}, {hi:.4f}]")

    print(f"\n{'='*65}")
    print("LOO Self-Test — each winner scored against the other 6")
    print(f"{'='*65}")

    base = os.path.dirname(os.path.abspath(__file__))
    for ticker, breakout_date, eps_growth in _WINNERS_META:
        csv_path = os.path.join(
            base, "case_studies", "winners", f"{ticker}.csv"
        ).replace("\\", "/")
        profile = load_profile(csv_path, breakout_date)
        profile["eps_growth"] = eps_growth

        result   = engine.score_candidate(profile, exclude=ticker)
        nb_str   = " | ".join(
            f"{n['ticker']}({n['distance']:.3f})" for n in result["neighbors"]
        )
        print(f"{ticker:6s}  score={result['score']:5.1f}  nearest: {nb_str}")
