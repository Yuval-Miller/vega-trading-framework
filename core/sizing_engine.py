import sys
import os
import math

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from core.data_fetcher import DataFetcher
from core.notifier import Notifier

class SizingEngine:

    def __init__(self):
        self.fetcher  = DataFetcher()
        self.notifier = Notifier()

    # ──────────────────────────────────────────────
    # חישוב Kelly Criterion
    # ──────────────────────────────────────────────
    def calculate_kelly(self, trades_history):
        try:
            if not trades_history or len(trades_history) < 10:
                return 0.25  # ברירת מחדל אם אין היסטוריה

            wins   = [t for t in trades_history if t["pnl"] > 0]
            losses = [t for t in trades_history if t["pnl"] <= 0]

            if not wins or not losses:
                return 0.25

            win_rate = len(wins) / len(trades_history)
            avg_win  = sum(t["pnl"] for t in wins)  / len(wins)
            avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses))

            if avg_loss == 0:
                return MAX_KELLY_PCT

            r      = avg_win / avg_loss
            kelly  = win_rate - ((1 - win_rate) / r)

            # Half-Kelly
            kelly = kelly * 0.5

            # תקרה מוחלטת
            kelly = min(kelly, MAX_KELLY_PCT)

            # רצפה — לא פחות מ-0
            kelly = max(kelly, 0)

            return round(kelly, 4)

        except Exception as e:
            return 0.25

    # ──────────────────────────────────────────────
    # חישוב Stop Loss (2N)
    # ──────────────────────────────────────────────
    def calculate_stop_loss(self, df, entry_price):
        try:
            atr = self.fetcher.get_atr(df)
            if atr is None:
                return None, None

            n          = atr.iloc[-1]
            stop_price = entry_price - (ATR_STOP_MULTIPLIER * n)

            # תקרת סטופ מקסימלי (7%)
            max_stop   = entry_price * (1 - MAX_STOP_PCT)
            stop_price = max(stop_price, max_stop)

            stop_distance = entry_price - stop_price

            # בדיקת Freeze Status
            atr_ma50 = atr.rolling(ATR_FREEZE_PERIOD).mean().iloc[-1]
            if n > ATR_FREEZE_MULTIPLIER * atr_ma50:
                self.notifier.send(
                    f"Freeze Status — ATR גבוה מדי: {n:.2f} vs {atr_ma50:.2f}",
                    "WARNING"
                )
                return None, None

            return round(stop_price, 2), round(stop_distance, 2)

        except Exception as e:
            return None, None

    # ──────────────────────────────────────────────
    # חישוב גודל פוזיציה (KC4)
    # ──────────────────────────────────────────────
    def calculate_position_size(self, entry_price, stop_distance,
                                portfolio_ils, usd_ils_rate,
                                kelly_pct=0.25, vix_regime="NORMAL"):
        try:
            if stop_distance <= 0 or usd_ils_rate <= 0:
                return None

            # המרת תקציב לדולרים
            portfolio_usd = portfolio_ils / usd_ils_rate

            # 1% סיכון מהתיק
            risk_usd = portfolio_usd * RISK_PER_TRADE_PCT

            # התאמה לפי VIX
            if vix_regime == "CAUTION":
                risk_usd *= VIX_SIZE_REDUCTION_CAUTION
            elif vix_regime == "HIGH_RISK":
                risk_usd *= VIX_SIZE_REDUCTION_HIGH
            elif vix_regime == "DEFENSE":
                return None

            # חישוב כמות מניות
            shares = math.floor(risk_usd / stop_distance)

            # בדיקה מול Kelly
            max_position_usd   = portfolio_usd * kelly_pct
            position_value_usd = shares * entry_price

            if position_value_usd > max_position_usd:
                shares = math.floor(max_position_usd / entry_price)

            if shares <= 0:
                return None

            position_value_usd = shares * entry_price
            actual_risk_usd    = shares * stop_distance
            actual_risk_ils    = actual_risk_usd * usd_ils_rate

            return {
                "shares":          shares,
                "entry_price":     entry_price,
                "position_usd":    round(position_value_usd, 2),
                "position_ils":    round(position_value_usd * usd_ils_rate, 2),
                "risk_usd":        round(actual_risk_usd, 2),
                "risk_ils":        round(actual_risk_ils, 2),
                "kelly_pct":       kelly_pct
            }

        except Exception as e:
            return None

    # ──────────────────────────────────────────────
    # חישוב מלא לעסקה
    # ──────────────────────────────────────────────
    def calculate_full_trade(self, ticker_symbol, entry_price,
                             trades_history=[], vix_regime="NORMAL"):
        try:
            usd_ils = self.fetcher.get_usd_ils_rate()
            if usd_ils is None:
                return None

            df = self.fetcher.get_price_data(ticker_symbol)
            if df is None:
                return None

            stop_price, stop_distance = self.calculate_stop_loss(df, entry_price)
            if stop_price is None:
                return None

            kelly = self.calculate_kelly(trades_history)

            sizing = self.calculate_position_size(
                entry_price    = entry_price,
                stop_distance  = stop_distance,
                portfolio_ils  = PORTFOLIO_BUDGET_ILS,
                usd_ils_rate   = usd_ils,
                kelly_pct      = kelly,
                vix_regime     = vix_regime
            )

            if sizing is None:
                return None

            result = {
                **sizing,
                "stop_price":    stop_price,
                "stop_distance": stop_distance,
                "usd_ils_rate":  usd_ils,
                "kelly":         kelly
            }

            self.notifier.buy_signal(
                ticker   = ticker_symbol,
                entry    = entry_price,
                stop     = stop_price,
                quantity = sizing["shares"],
                risk     = sizing["risk_ils"]
            )

            return result

        except Exception as e:
            return None