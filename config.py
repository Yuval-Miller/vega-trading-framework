import os
from dotenv import load_dotenv

load_dotenv()

PORTFOLIO_BUDGET_ILS       = 30_000
CASH_BUFFER_TARGET_ILS     = 25_000
RISK_PER_TRADE_PCT         = 0.01
MAX_KELLY_PCT              = 0.25

MIN_STOCK_PRICE            = 5.0
MIN_AVG_VOLUME             = 200_000
MAX_FROM_52W_HIGH_PCT      = 0.25
MIN_FROM_52W_LOW_PCT       = 0.30
MIN_RVOL_ENTRY             = 1.5   # Large Cap
MIN_RVOL_ENTRY_SMALL       = 2.0   # Small/Mid Cap (שווי שוק < $10B)
MIN_RVOL_FALLBACK          = 1.2
SMALL_CAP_THRESHOLD        = 10_000_000_000  # $10B

VCP_MIN_CONTRACTIONS       = 2
VCP_MAX_CONTRACTIONS       = 4
VCP_WINDOW_DAYS            = 60
VCP_CONTRACTION_TOLERANCE  = 0.15
VCP_VOLUME_DRY_PCT = 0.65
VCP_SWING_WINDOW = 7
VCP_MAX_VOLATILITY_WEEK = 0.05

ATR_PERIOD                 = 20
ATR_STOP_MULTIPLIER        = 2.0
MAX_STOP_PCT               = 0.07
ATR_FREEZE_MULTIPLIER      = 2.0
ATR_FREEZE_PERIOD          = 50

VIX_NORMAL                 = 20
VIX_CAUTION                = 25
VIX_HIGH_RISK              = 30
VIX_SIZE_REDUCTION_CAUTION = 0.75
VIX_SIZE_REDUCTION_HIGH    = 0.50
MAX_DISTRIBUTION_DAYS      = 4
DISTRIBUTION_WINDOW        = 25

BREAKEVEN_TRIGGER_N        = 1.0
EARNINGS_CUSHION_PCT       = 0.07
MAX_POSITIONS_PER_INDUSTRY = 2
ALLOW_INDUSTRY_EXCEPTION   = False

TAX_RATE                   = 0.25

SHEETS_CREDENTIALS_FILE    = "credentials.json"
SHEETS_SPREADSHEET_NAME    = "VEGA Trading Portfolio"
SHEET_PENDING              = "Pending_Orders"
SHEET_OPEN                 = "Open_Positions"
SHEET_CLOSED               = "Closed_Positions"
SHEET_DASHBOARD            = "Dashboard"

MARKET_OPEN_HOUR           = 16
MARKET_OPEN_MIN            = 30
MARKET_CLOSE_HOUR          = 23
MARKET_CLOSE_MIN           = 0
NIGHT_SCAN_START_HOUR      = 23
NIGHT_SCAN_START_MIN       = 15
TRADING_DAY_MINUTES        = 390

NEWS_LOOKBACK_HOURS        = 48
NEWS_BEARISH_THRESHOLD     = -0.05

LOG_DIR                    = "logs"
LOG_LEVEL                  = "INFO"