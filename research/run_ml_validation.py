"""
run_ml_validation.py
Usage: python research/run_ml_validation.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from research.ml_validator import DATASET, extract_features, run_analysis

def main():
    print("VEGA ML VALIDATOR — loading dataset...")
    print(f"Total stocks in dataset: {len(DATASET)}")
    print("="*60)

    main_rows = []
    mega_rows = []

    for stock in DATASET:
        print(f"  Fetching {stock['ticker']} ({stock['breakout']})...")
        feat = extract_features(stock["ticker"], stock["breakout"])
        if feat is None:
            print(f"  [{stock['ticker']}] SKIPPED")
            continue
        feat["label"]   = stock["label"]
        feat["is_mega"] = stock["is_mega"]

        if stock["is_mega"]:
            mega_rows.append(feat)
        else:
            main_rows.append(feat)

    if main_rows:
        run_analysis(main_rows, group_name="MAIN MATRIX (non-mega)")

    if mega_rows:
        run_analysis(mega_rows, group_name="MEGA-CAP ISOLATED")

if __name__ == "__main__":
    main()