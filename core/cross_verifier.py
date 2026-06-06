import random
from core.data_fetcher import DataFetcher

TOLERANCES = {
    "atr":      0.02,
    "rs":       0.02,
    "avg_vol":  0.05,
    "dist_high": 0.005,
}

class CrossVerifier:
    def __init__(self, fetcher: DataFetcher, sheets):
        self.fetcher = fetcher
        self.sheets = sheets

    def run(self, candidates: list):
        if not candidates:
            return
        sample = random.sample(candidates, min(5, len(candidates)))
        for c in sample:
            self._verify_one(c)

    def _verify_one(self, c: dict):
        ticker = c["ticker"]
        try:
            df = self.fetcher.get_price_data(ticker)
            if df is None or df.empty:
                return

            fresh_atr   = self.fetcher.get_atr(ticker)
            fresh_vol   = float(df["Volume"].iloc[-64:-1].mean())
            high_52w    = float(df["High"].rolling(252).max().iloc[-1])
            price       = float(df["Close"].iloc[-1])
            fresh_dist  = (high_52w - price) / high_52w

            checks = {
                "atr":       (fresh_atr,              c.get("atr", fresh_atr)),
                "avg_vol":   (fresh_vol,               c.get("avg_vol", fresh_vol)),
                "dist_high": (fresh_dist,              c.get("dist_high", fresh_dist)),
            }

            flags = []
            for key, (fresh, stored) in checks.items():
                if stored == 0:
                    continue
                deviation = abs(fresh - stored) / abs(stored)
                if deviation > TOLERANCES[key]:
                    flags.append(f"{key}:{deviation:.1%}")

            if flags:
                note = "⚠️ VERIFY " + " | ".join(flags)
                self.sheets.append_note_to_pending(ticker, note)

        except Exception as e:
            pass
