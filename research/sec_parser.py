"""
research/sec_parser.py
SEC EDGAR EPS & Revenue Acceleration Parser — Soft Advisory Flag
Run: python research/sec_parser.py
Output: console report + dict (ready for KNN v2 integration)
"""

import requests
import time
import json
from datetime import datetime

# ── Constants ──────────────────────────────────────────────────────────────────
SEC_HEADERS = {"User-Agent": "VegaFramework research@vega.local"}  # SEC requires User-Agent
CIK_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=10-Q&dateRange=custom&startdt=2018-01-01"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
RATE_LIMIT_SLEEP = 0.2  # SEC allows ~10 req/sec; we stay conservative
ACCELERATION_MIN_DELTA = 0.05  # 5pp minimum change to call ACCELERATING vs STABLE
QUARTERS_NEEDED = 3  # YoY slope over last 3 quarters

# EPS concepts to try in order (companies file under different GAAP tags)
EPS_CONCEPTS = [
    "EarningsPerShareDiluted",
    "EarningsPerShareBasic",
    "EarningsPerShareBasicAndDiluted",
]

# Revenue concepts to try in order
REV_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]


# ── Module 1: CIK Lookup ───────────────────────────────────────────────────────
def get_cik(ticker: str) -> str | None:
    """Returns zero-padded 10-digit CIK string, or None if not found."""
    try:
        # Primary: SEC company tickers JSON (fastest, most reliable)
        url = "https://www.sec.gov/files/company_tickers.json"
        r = requests.get(url, headers=SEC_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        for entry in data.values():
            if entry["ticker"].upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
        return None
    except Exception as e:
        print(f"  [CIK ERROR] {ticker}: {e}")
        return None


# ── Module 2: Fetch Company Facts ──────────────────────────────────────────────
def fetch_company_facts(cik: str) -> dict | None:
    """Fetches full XBRL company facts JSON from SEC EDGAR."""
    try:
        url = FACTS_URL.format(cik=cik)
        r = requests.get(url, headers=SEC_HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [FACTS ERROR] CIK {cik}: {e}")
        return None


# ── Module 3: Extract Quarterly Series ────────────────────────────────────────
def extract_quarterly_series(facts: dict, concepts: list[str]) -> list[tuple] | None:
    """
    Tries each concept in order. Returns list of (end_date, value) tuples
    from 10-Q filings only, sorted ascending by end date.
    Returns None if no concept found.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    for concept in concepts:
        if concept not in us_gaap:
            continue
        units = us_gaap[concept].get("units", {})
        # EPS is in USD/shares, Revenue in USD
        unit_key = next(iter(units), None)
        if not unit_key:
            continue

        entries = units[unit_key]
        # Filter: 10-Q only (excludes 10-K annual cumulative), must have 'end' date
        quarterly = [
            e for e in entries
            if e.get("form") == "10-Q" and "end" in e and "val" in e
        ]
        if not quarterly:
            continue

        # Deduplicate by end date (keep latest filed version)
        by_date = {}
        for e in quarterly:
            end = e["end"]
            if end not in by_date or e.get("filed", "") > by_date[end].get("filed", ""):
                by_date[end] = e

        series = sorted(
            [(date, entry["val"]) for date, entry in by_date.items()],
            key=lambda x: x[0]
        )
        return series

    return None  # No valid concept found


# ── Module 4: Calculate YoY Acceleration ──────────────────────────────────────
def calc_yoy_acceleration(series: list[tuple]) -> list[float | None] | None:
    """
    Computes YoY% for the last QUARTERS_NEEDED quarters.
    Requires at least QUARTERS_NEEDED + 4 data points (for YoY comparison).
    Returns [yoy_oldest, ..., yoy_most_recent] or None if insufficient data.
    """
    if len(series) < QUARTERS_NEEDED + 4:
        return None  # Not enough history for YoY on 3 quarters

    yoy_list = []
    # Work backwards from most recent quarter
    recent = series[-(QUARTERS_NEEDED):]  # last 3 quarters

    for date, val in recent:
        # Find the quarter from exactly 4 periods ago (same seasonal quarter)
        # Match by finding entry with end date ~1 year earlier
        prior = _find_prior_year_quarter(series, date)
        if prior is None:
            yoy_list.append(None)
            continue
        prior_val = prior[1]
        if prior_val == 0:
            yoy_list.append(None)  # IPO trap / zero baseline
            continue
        yoy_pct = (val - prior_val) / abs(prior_val)
        yoy_list.append(round(yoy_pct, 4))

    return yoy_list


def _find_prior_year_quarter(series: list[tuple], target_date: str) -> tuple | None:
    """Finds the quarter ending closest to exactly 1 year before target_date."""
    from datetime import datetime, timedelta
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return None

    prior_target = target.replace(year=target.year - 1)
    best = None
    best_delta = timedelta(days=46)  # max 46 days drift allowed for quarter matching

    for date, val in series:
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue
        delta = abs(d - prior_target)
        if delta < best_delta:
            best_delta = delta
            best = (date, val)

    return best


# ── Module 5: Classify Slope ───────────────────────────────────────────────────
def classify_slope(yoy_list: list[float | None] | None) -> tuple[str, list]:
    """
    Returns (label, yoy_list) where label is one of:
    ACCELERATING ✅ | DECELERATING ⚠️ | STABLE / MIXED | NO_BASELINE | INSUFFICIENT_DATA
    """
    if yoy_list is None:
        return "INSUFFICIENT_DATA", []

    if any(v is None for v in yoy_list):
        return "NO_BASELINE (IPO/Early Stage)", yoy_list

    if len(yoy_list) < 2:
        return "INSUFFICIENT_DATA", yoy_list

    # Check strict monotonic direction with minimum delta threshold
    deltas = [yoy_list[i+1] - yoy_list[i] for i in range(len(yoy_list)-1)]

    all_accelerating = all(d > ACCELERATION_MIN_DELTA for d in deltas)
    all_decelerating = all(d < -ACCELERATION_MIN_DELTA for d in deltas)

    if all_accelerating:
        return "ACCELERATING ✅", yoy_list
    elif all_decelerating:
        return "DECELERATING ⚠️", yoy_list
    else:
        return "STABLE / MIXED", yoy_list


# ── Main Parser ────────────────────────────────────────────────────────────────
def parse_candidates(tickers: list[str]) -> dict:
    """
    Main entry point. Returns dict of results per ticker.
    Ready for KNN v2 integration.
    """
    results = {}

    print("=" * 65)
    print(f"SEC EPS Acceleration Report — {datetime.today().strftime('%Y-%m-%d')}")
    print("=" * 65)

    for ticker in tickers:
        print(f"\n{ticker}")
        result = {
            "eps_slope": None,
            "rev_slope": None,
            "eps_yoy": [],
            "rev_yoy": [],
        }

        # Step 1: CIK
        cik = get_cik(ticker)
        time.sleep(RATE_LIMIT_SLEEP)
        if not cik:
            print(f"  EPS YoY: NO_SEC_DATA")
            print(f"  Rev YoY: NO_SEC_DATA")
            result["eps_slope"] = "NO_SEC_DATA"
            result["rev_slope"] = "NO_SEC_DATA"
            results[ticker] = result
            continue

        # Step 2: Facts
        facts = fetch_company_facts(cik)
        time.sleep(RATE_LIMIT_SLEEP)
        if not facts:
            print(f"  EPS YoY: NO_SEC_DATA")
            print(f"  Rev YoY: NO_SEC_DATA")
            result["eps_slope"] = "NO_SEC_DATA"
            result["rev_slope"] = "NO_SEC_DATA"
            results[ticker] = result
            continue

        # Step 3+4+5: EPS
        eps_series = extract_quarterly_series(facts, EPS_CONCEPTS)
        if eps_series:
            eps_yoy = calc_yoy_acceleration(eps_series)
            eps_label, eps_yoy_clean = classify_slope(eps_yoy)
        else:
            eps_label, eps_yoy_clean = "NO_SEC_DATA", []

        # Step 3+4+5: Revenue
        rev_series = extract_quarterly_series(facts, REV_CONCEPTS)
        if rev_series:
            rev_yoy = calc_yoy_acceleration(rev_series)
            rev_label, rev_yoy_clean = classify_slope(rev_yoy)
        else:
            rev_label, rev_yoy_clean = "NO_SEC_DATA", []

        # Format YoY values for display
        def fmt(yoy_list):
            if not yoy_list:
                return "—"
            parts = []
            for i, v in enumerate(yoy_list):
                label = f"Q{i+1}"
                if v is None:
                    parts.append(f"{label}=None")
                else:
                    parts.append(f"{label}={v*100:+.1f}%")
            return " | ".join(parts)

        print(f"  EPS YoY: {fmt(eps_yoy_clean)} → {eps_label}")
        print(f"  Rev YoY: {fmt(rev_yoy_clean)} → {rev_label}")

        result["eps_slope"] = eps_label
        result["rev_slope"] = rev_label
        result["eps_yoy"] = eps_yoy_clean
        result["rev_yoy"] = rev_yoy_clean
        results[ticker] = result

        time.sleep(RATE_LIMIT_SLEEP)

    print("\n" + "=" * 65)
    _print_summary(results)
    return results


def _print_summary(results: dict):
    print("SUMMARY")
    print("-" * 65)
    for ticker, r in results.items():
        eps = r.get("eps_slope", "—")
        rev = r.get("rev_slope", "—")
        # Flag only ACCELERATING on both as strong signal
        if "ACCELERATING" in str(eps) and "ACCELERATING" in str(rev):
            flag = "⭐ STRONG"
        elif "DECELERATING" in str(eps) or "DECELERATING" in str(rev):
            flag = "⚠️  WEAK"
        elif "NO_" in str(eps):
            flag = "❓ MANUAL"
        else:
            flag = "➖ NEUTRAL"
        print(f"  {ticker:<6} EPS={eps:<30} Rev={rev:<30} {flag}")
    print("=" * 65)


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Final candidates from night scan 2026-05-29
    CANDIDATES = ["ALTO", "APLE", "BCAX", "CPRX", "CRI", "CYTK", "TECX", "TFIN", "UNF"]
    parse_candidates(CANDIDATES)