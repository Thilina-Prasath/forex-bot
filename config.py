import os

# ─── Telegram ────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Alpha Vantage API (FREE) ─────────────────
# Key ගන්නේ: https://www.alphavantage.co/support/#api-key
# "GET FREE API KEY" → Email → Instant key
ALPHA_VANTAGE_KEY  = os.environ.get("ALPHA_VANTAGE_KEY")

# ─── Trading Pairs ───────────────────────────
FOREX_PAIRS = {
    "EURUSD":  "EURUSD=X",
    "GBPUSD":  "GBPUSD=X",
    "USDJPY":  "USDJPY=X",
    "AUDUSD":  "AUDUSD=X",
    "USDCHF":  "USDCHF=X",
    "USDCAD":  "USDCAD=X",
    "GOLD":    "GC=F",
    "BTCUSD":  "BTC-USD",
}

# ─── Indicator Settings ──────────────────────
RSI_PERIOD      = 14
RSI_OVERSOLD    = 40
RSI_OVERBOUGHT  = 60
EMA_FAST        = 20
EMA_SLOW        = 50
EMA_TREND       = 200
ATR_PERIOD      = 14
ATR_SL_MULTI    = 1.5
ATR_TP_MULTI    = 2.5

# ─── Signal Filter ───────────────────────────
MIN_SCORE       = 3

# ─── Schedule ────────────────────────────────
SIGNAL_TIME_UTC = "00:05"

# ─── Data ────────────────────────────────────
CANDLES_PERIOD  = "1y"