import os

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── TwelveData API ───────────────────────────────────────────────────────────
# Get free key: https://twelvedata.com/
TWELVEDATA_KEY = os.environ.get("TWELVEDATA_KEY", "")

# ── Trading Pairs ────────────────────────────────────────────────────────────
# Format: "DisplayName": "API_Ticker"
# Pairs 8 → 13 (signals frequency increase)
FOREX_PAIRS = {
    # London + NY session pairs
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDCHF": "USD/CHF",
    "USDCAD": "USD/CAD",
    "EURGBP": "EUR/GBP",   # ← NEW

    # Tokyo + London session pairs
    "USDJPY": "USD/JPY",
    "EURJPY": "EUR/JPY",   # ← NEW
    "GBPJPY": "GBP/JPY",   # ← NEW

    # Sydney + Tokyo session pairs
    "AUDUSD": "AUD/USD",
    "NZDUSD": "NZD/USD",   # ← NEW
    "AUDJPY": "AUD/JPY",   # ← NEW

    # Volatile pairs (MIN_SCORE 5 required)
    "GOLD":   "XAU/USD",
    "BTCUSD": "BTC/USD",
}

# ── Indicator Settings ───────────────────────────────────────────────────────
RSI_PERIOD     = 14
RSI_OVERSOLD   = 40
RSI_OVERBOUGHT = 60
EMA_FAST       = 20
EMA_SLOW       = 50
EMA_TREND      = 200
ATR_PERIOD     = 14
ATR_SL_MULTI   = 1.5
ATR_TP_MULTI   = 2.5

# ── Signal Filter ────────────────────────────────────────────────────────────
# Analyzer direction decision: score >= MIN_SCORE
# cron_run quality gate:       score >= QUALITY_MIN_SCORE (4)
# GOLD/BTCUSD volatile:        score >= 5 (in analyzer.py)
MIN_SCORE = 3

# ── Schedule ─────────────────────────────────────────────────────────────────
SIGNAL_TIME_UTC = "00:05"

# ── Data ─────────────────────────────────────────────────────────────────────
CANDLES_PERIOD = "1y"