import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research.profile_loader import load_profile
from research.backtest_engine import BacktestEngine

winners = [
    ("research/case_studies/winners/CELH.csv", "2020-11-05", 0.80),
    ("research/case_studies/winners/CROX.csv", "2021-11-04", 4.29),
    ("research/case_studies/winners/BOOT.csv", "2021-10-29", 3.50),
    ("research/case_studies/winners/SMCI.csv", "2023-02-28", 5.56),
    ("research/case_studies/winners/AEHR.csv", "2022-11-17", 0.42),
    ("research/case_studies/winners/GNRC.csv", "2021-06-01", 0.805),
    ("research/case_studies/winners/SITE.csv", "2021-04-27", 0.673),
]

traps = [
    ("research/case_studies/traps/COIN.csv", "2021-08-09", None),   # REJECT_IPO_TRAP
    ("research/case_studies/traps/PLUG.csv", "2020-10-05", -0.049), # REJECT_FUNDAMENTALS
    ("research/case_studies/traps/SPCE.csv", "2021-05-24", -9.99),  # REJECT_FUNDAMENTALS (deepening)
    ("research/case_studies/traps/UPST.csv", "2021-05-19", -3.10),  # REJECT_FUNDAMENTALS
    ("research/case_studies/traps/RIVN.csv", "2021-11-16", None),   # REJECT_IPO_TRAP
]

engine = BacktestEngine()

def run_batch(cases, label):
    print(f"\n{'='*55}")
    print(f"{label}")
    print(f"{'='*55}")
    passed = 0
    for csv_path, breakout_date, eps_growth in cases:
        ticker = os.path.basename(csv_path).replace(".csv", "")
        profile = load_profile(csv_path, breakout_date)
        profile["eps_growth"] = eps_growth if eps_growth is not None else 0.0
        result = engine.run_profile(profile)
        verdict = result["verdict"]
        print(f"\n{ticker} [{breakout_date}] → {verdict}")
        if result.get("violations"):
            print(f"  Violations:    {result['violations']}")
        if result.get("compensations"):
            print(f"  Compensations: {result['compensations']}")
        if verdict in ("PASS", "WATCHLIST"):
            passed += 1
    return passed, len(cases)

w_pass, w_total = run_batch(winners, "WINNERS")
t_pass, t_total = run_batch(traps,   "TRAPS — expect all REJECT")

print(f"\n{'='*55}")
print(f"WINNERS:  {w_pass}/{w_total} PASS/WATCHLIST")
print(f"TRAPS:    {t_pass}/{t_total} slipped through (target: 0)")
print(f"{'='*55}")