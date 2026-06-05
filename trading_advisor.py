import sys
import os
from datetime import datetime, date
import pytz
import pandas as pd

from research.knn_engine import KNNEngine

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *
from core.data_fetcher import DataFetcher
from core.market_scanner import MarketScanner
from core.entry_engine import EntryEngine
from core.sizing_engine import SizingEngine
from core.defense_engine import DefenseEngine
from core.sheets_connector import SheetsConnector
from core.notifier import Notifier
from core.cross_verifier import CrossVerifier

OPEN_COLS = [
    "Ticker", "Entry_Price", "Entry_Date", "Stop_Loss",
    "Position_Size", "Exit_Price", "Exit_Date",
    "Defense_Status", "Status", "Notes"
]
CLOSED_COLS = [
    "Ticker", "Entry_Price", "Entry_Date", "Exit_Price",
    "Exit_Date", "PnL_USD", "PnL_PCT", "Notes"
]


class TradingAdvisor:

    def __init__(self):
        self.fetcher  = DataFetcher()
        self.scanner  = MarketScanner()
        self.entry    = EntryEngine()
        self.sizing   = SizingEngine()
        self.defense  = DefenseEngine()
        self.sheets   = SheetsConnector()
        self.notifier = Notifier()

    def get_open_positions(self):
        try:
            records = self.sheets.read_all(SHEET_OPEN)
            return records if records else []
        except Exception:
            return []

    def get_pending_orders(self):
        try:
            records = self.sheets.read_all(SHEET_PENDING)
            return records if records else []
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────
    # Status Watcher — runs at the top of every scan
    # ─────────────────────────────────────────────────────────
    def run_status_watcher(self):
        self.notifier.send("--- STATUS WATCHER ---", "INFO")
        self.sheets.ensure_columns(SHEET_OPEN,   OPEN_COLS)
        self.sheets.ensure_columns(SHEET_CLOSED, CLOSED_COLS)

        # 1. Pending "Bought" → Open_Positions
        pending = self.sheets.get_sheet_data_with_rows(SHEET_PENDING)
        bought  = sorted(
            [r for r in pending if r.get("Status", "").upper() == "BOUGHT"],
            key=lambda r: r["__row__"], reverse=True
        )
        for row in bought:
            ticker = row.get("Ticker", "")
            today  = datetime.now().strftime("%d/%m/%Y")
            self.sheets.append_row(SHEET_OPEN, [
                ticker, "", today, "", "", "", "", "", "ACTIVE",
                "Fill Entry_Price to activate stop calculations"
            ])
            # highlight Entry_Price yellow on the newly appended row
            open_rows = self.sheets.get_sheet_data_with_rows(SHEET_OPEN)
            for r in reversed(open_rows):
                if r.get("Ticker") == ticker and not r.get("Entry_Price", "").strip():
                    self.sheets.highlight_cell_by_col(
                        SHEET_OPEN, r["__row__"], "Entry_Price", "yellow"
                    )
                    break
            self.sheets.delete_row(SHEET_PENDING, row["__row__"])
            self.notifier.send(f"[{ticker}] Pending BOUGHT → Open_Positions", "INFO")

        # 2. Open: Entry_Price now filled but Stop_Loss still empty → calculate
        open_rows = self.sheets.get_sheet_data_with_rows(SHEET_OPEN)
        for row in open_rows:
            entry_str = row.get("Entry_Price", "").strip()
            stop_str  = row.get("Stop_Loss",   "").strip()
            if not entry_str or stop_str:
                continue
            ticker = row.get("Ticker", "")
            try:
                entry_price   = float(entry_str)
                regime, _, _  = self.scanner.check_market_regime()
                trade         = self.sizing.calculate_full_trade(
                    ticker, entry_price, vix_regime=regime
                )
                if trade:
                    self.sheets.update_row_fields(SHEET_OPEN, row["__row__"], {
                        "Stop_Loss":     str(trade["stop_price"]),
                        "Position_Size": str(trade["shares"]),
                        "Notes": (
                            f"Stop ${trade['stop_price']} | "
                            f"{trade['shares']} shares | "
                            f"Risk ${trade['risk_usd']}"
                        )
                    })
                    self.sheets.highlight_cell_by_col(
                        SHEET_OPEN, row["__row__"], "Entry_Price", "white"
                    )
                    self.notifier.send(
                        f"[{ticker}] Stop/Size set: ${trade['stop_price']} | {trade['shares']} shares",
                        "INFO"
                    )
            except Exception as e:
                self.notifier.send(f"[{ticker}] Stop calc error: {e}", "WARNING")

        # 3. Open: Status="Sold" → prompt for exit or close to Closed_Positions
        open_rows = self.sheets.get_sheet_data_with_rows(SHEET_OPEN)
        sold_rows = sorted(
            [r for r in open_rows if r.get("Status", "").upper() == "SOLD"],
            key=lambda r: r["__row__"], reverse=True
        )
        for row in sold_rows:
            ticker   = row.get("Ticker", "")
            exit_str = row.get("Exit_Price", "").strip()
            if not exit_str:
                self.sheets.update_row_fields(SHEET_OPEN, row["__row__"], {
                    "Notes": "SOLD — Fill Exit_Price to close position"
                })
                self.sheets.highlight_cell_by_col(
                    SHEET_OPEN, row["__row__"], "Exit_Price", "yellow"
                )
                self.notifier.send(f"[{ticker}] Status=Sold — awaiting Exit_Price", "WARNING")
            else:
                try:
                    entry_price = float(row.get("Entry_Price", 0) or 0)
                    exit_price  = float(exit_str)
                    shares      = int(row.get("Position_Size", 0) or 0)
                    pnl_usd     = round((exit_price - entry_price) * shares, 2)
                    pnl_pct     = (
                        round((exit_price - entry_price) / entry_price * 100, 2)
                        if entry_price else 0
                    )
                    today = datetime.now().strftime("%d/%m/%Y")
                    self.sheets.append_row(SHEET_CLOSED, [
                        ticker,
                        row.get("Entry_Price", ""),
                        row.get("Entry_Date",  ""),
                        exit_str,
                        today,
                        pnl_usd,
                        f"{pnl_pct}%",
                        row.get("Notes", "")
                    ])
                    self.sheets.delete_row(SHEET_OPEN, row["__row__"])
                    self.notifier.send(
                        f"[{ticker}] Closed → Closed_Positions | PnL ${pnl_usd} ({pnl_pct}%)",
                        "SUCCESS"
                    )
                except Exception as e:
                    self.notifier.send(f"[{ticker}] Close error: {e}", "WARNING")

    # ─────────────────────────────────────────────────────────
    # Defense Loop — runs on every Open_Position with Entry_Price
    # ─────────────────────────────────────────────────────────
    def run_defense_loop(self):
        self.notifier.send("--- DEFENSE LOOP ---", "INFO")
        open_rows = self.sheets.get_sheet_data_with_rows(SHEET_OPEN)
        active    = [r for r in open_rows if r.get("Entry_Price", "").strip()]

        if not active:
            self.notifier.send("No active positions with Entry_Price filled", "INFO")
            return

        for row in active:
            ticker = row.get("Ticker", "")
            try:
                entry_price = float(row.get("Entry_Price", 0))
                stop_str    = row.get("Stop_Loss", "").strip()
                try:
                    stop_price = float(stop_str) if stop_str else entry_price * (1 - MAX_STOP_PCT)
                except (ValueError, TypeError):
                    stop_price = entry_price * (1 - MAX_STOP_PCT)
                position = {
                    "ticker":      ticker,
                    "entry_price": entry_price,
                    "stop_price":  stop_price,
                }
                updated = self.defense.update_stop_loss(position)

                if updated.get("status") == "STOP_HIT":
                    defense_status = "STOP HIT - SELL NOW"
                    color          = "red"
                elif updated.get("stop_updated"):
                    defense_status = "Move stop to breakeven"
                    color          = "orange"
                    self.sheets.update_row_fields(SHEET_OPEN, row["__row__"], {
                        "Stop_Loss": str(updated["stop_price"])
                    })
                elif updated.get("climax_alert"):
                    defense_status = "Climax - consider selling"
                    color          = "purple"
                elif updated.get("sma20_alert"):
                    defense_status = "Trail stop to SMA20"
                    color          = "yellow"
                else:
                    pnl            = updated.get("pnl_pct", 0)
                    cur            = updated.get("current_price", "")
                    defense_status = f"OK | ${cur} | {pnl:.1%}"
                    color          = None

                self.sheets.update_row_fields(SHEET_OPEN, row["__row__"], {
                    "Defense_Status": defense_status
                })
                if color:
                    self.sheets.highlight_row(SHEET_OPEN, row["__row__"], color)

                self.notifier.send(f"[{ticker}] Defense: {defense_status}", "INFO")

            except Exception as e:
                self.notifier.send(f"[{ticker}] Defense error: {e}", "WARNING")

    # ─────────────────────────────────────────────────────────
    # KNN profile builder — live candidate (no CSV needed)
    # ─────────────────────────────────────────────────────────
    def _build_live_profile(self, ticker, df=None):
        if df is None:
            df = self.fetcher.get_price_data(ticker, days=300)
        if df is None or len(df) < 60:
            return None
        window = df.iloc[-260:].copy()
        window["SMA20"]  = window["Close"].rolling(20).mean()
        window["SMA50"]  = window["Close"].rolling(50).mean()
        window["SMA150"] = window["Close"].rolling(150).mean()
        window["SMA200"] = window["Close"].rolling(200).mean()
        try:
            fund = self.fetcher.get_fundamentals(ticker)
            eps_growth = fund.get("eps_growth") if fund else None
        except Exception:
            eps_growth = None
        return {
            "ticker":       ticker,
            "df_full":      window,
            "setup_window": window.iloc[-21:-1].copy(),
            "eps_growth":   eps_growth,
            "rows":         len(df),
        }

    # ─────────────────────────────────────────────────────────
    # Night Scan
    # ─────────────────────────────────────────────────────────
    def run_night_scan(self, watchlist):
        self.notifier.send("=" * 50, "INFO")
        self.notifier.send("--- RUNNING FULL NIGHTLY SCAN ---", "INFO")
        self.notifier.send(f"Checking {len(watchlist)} tickers...", "INFO")

        self.run_status_watcher()
        self.run_defense_loop()

        regime, vix, breadth = self.scanner.check_market_regime()
        self.notifier.market_status(regime, vix, breadth)

        candidates = []
        counters   = {
            "passed_price_volume": 0,
            "passed_trend":        0,
            "passed_rs":           0,
            "passed_prefilters":   0,
            "passed_fund":         0,
            "rejected_rs":         0,
            "rejected_dist":       0,
            "rejected_vol":        0,
            "rejected_base":       0,
            "rejected_fund":       0,
            "failed_vcp":          0,
            "rejected_knn":        0,
        }

        knn_engine = KNNEngine()

        for ticker in watchlist:
            try:
                result = self.scanner.scan_ticker(ticker, counters)
                if result:
                    try:
                        profile = self._build_live_profile(ticker, df=result.get("df"))
                        if profile:
                            knn_result = knn_engine.score_candidate(profile)
                            score      = knn_result["score"]
                            if score < 50:
                                counters["rejected_knn"] += 1
                                self.notifier.send(f"KNN REJECT: {ticker} score={score}", "INFO")
                                continue
                            nearest = knn_result["neighbors"][0]
                            result["notes"] = (
                                f"KNN={score} nn={nearest['ticker']}({nearest['distance']:.3f}) | "
                                + result.get("notes", "")
                            )
                    except Exception as e:
                        self.notifier.send(f"[{ticker}] KNN error: {e}", "WARNING")
                    candidates.append(result)
            except Exception as e:
                self.notifier.send(f"[{ticker}] Error: {e}", "WARNING")
                continue

        self.notifier.send("=" * 50, "INFO")
        self.notifier.send(f"Scan summary:", "INFO")
        self.notifier.send(f"  Total scanned:          {len(watchlist)}", "INFO")
        self.notifier.send(f"  Passed price+volume:    {counters['passed_price_volume']}", "INFO")
        self.notifier.send(f"  Passed Trend Template:  {counters['passed_trend']}", "INFO")
        self.notifier.send(f"  Rejected RS:            {counters['rejected_rs']}", "INFO")
        self.notifier.send(f"  Rejected dist/high:     {counters['rejected_dist']}", "INFO")
        self.notifier.send(f"  Rejected vol cap:       {counters['rejected_vol']}", "INFO")
        self.notifier.send(f"  Rejected extension H6:  {counters.get('rejected_ext', 0)}", "INFO")
        self.notifier.send(f"  Rejected SMA150 H7:     {counters.get('rejected_h7', 0)}", "INFO")
        self.notifier.send(f"  Rejected base length:   {counters['rejected_base']}", "INFO")
        self.notifier.send(f"  Rejected fundamentals:  {counters['rejected_fund']}", "INFO")
        self.notifier.send(f"  Passed RS:              {counters['passed_rs']}", "INFO")
        self.notifier.send(f"  Passed pre-filters:     {counters['passed_prefilters']}", "INFO")
        self.notifier.send(f"  Passed fundamentals:    {counters['passed_fund']}", "INFO")
        self.notifier.send(f"  Failed VCP only:        {counters['failed_vcp']}", "INFO")
        self.notifier.send(f"  Rejected KNN:           {counters['rejected_knn']}", "INFO")
        self.notifier.send(f"  Final candidates:       {len(candidates)}", "INFO")
        self.notifier.send("=" * 50, "INFO")

        if candidates:
            for candidate in candidates:
                candidate = {k.title(): v for k, v in candidate.items()}
                result = self.sheets.upsert_pending_order(candidate)
                logger.info(f"{candidate.get('Ticker')} → Pending_Orders: {result}")

        self.notifier.send(
            f"Night scan complete — {len(candidates)} candidates found",
            "SUCCESS"
        )
        CrossVerifier(self.fetcher, self.sheets).run(candidates)
        return candidates

    # ─────────────────────────────────────────────────────────
    # Day Scan
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _get_day_scan_gate() -> int:
        """Returns gate time in minutes since midnight (IL time). Summer (DST): 17:15. Winter: 16:15."""
        il_tz = pytz.timezone("Asia/Jerusalem")
        il_now = datetime.now(il_tz)
        return 17 * 60 + 15 if bool(il_now.dst()) else 16 * 60 + 15

    def run_day_scan(self):
        il_tz    = pytz.timezone("Asia/Jerusalem")
        now      = datetime.now(il_tz)
        hour     = now.hour
        minute   = now.minute
        time_val = hour * 60 + minute

        if time_val < self._get_day_scan_gate():
            gate = self._get_day_scan_gate()
            gate_str = f"{gate // 60:02d}:{gate % 60:02d}"
            self.notifier.send(
                f"Day scan blocked — time is {hour:02d}:{minute:02d}. Run after {gate_str}",
                "WARNING"
            )
            return

        self.notifier.send("=" * 50, "INFO")
        self.notifier.send("--- RUNNING DAY SCAN ---", "INFO")

        self.run_status_watcher()
        self.run_defense_loop()

        pending = self.get_pending_orders()
        if not pending:
            self.notifier.send("No pending orders", "INFO")
            return

        open_positions = self.get_open_positions()

        for order in pending:
            ticker = order.get("ticker") or order.get("Ticker")
            pivot  = order.get("pivot")  or order.get("Pivot")

            if not ticker or not pivot:
                continue
            try:
                pivot = float(pivot)
            except Exception:
                continue

            result = self.entry.evaluate_entry(
                ticker_symbol  = ticker,
                pivot          = pivot,
                open_positions = open_positions
            )

            if result:
                trade = self.sizing.calculate_full_trade(
                    ticker_symbol = ticker,
                    entry_price   = result["price"],
                    vix_regime    = result["regime"]
                )
                if trade:
                    self.notifier.send(
                        f"[{ticker}] Breakout confirmed — enter Buy Stop in IBKR",
                        "SUCCESS"
                    )
