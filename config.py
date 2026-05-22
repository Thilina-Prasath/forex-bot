import os

# Telegram 
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# get key: https://twelvedata.com/
TWELVEDATA_KEY     = os.environ.get("TWELVEDATA_KEY", "")

# Trading Pairs 
FOREX_PAIRS = {
    "EURUSD":  "EUR/USD",
    "GBPUSD":  "GBP/USD",
    "USDJPY":  "USD/JPY",
    "AUDUSD":  "AUD/USD",
    "USDCHF":  "USD/CHF",
    "USDCAD":  "USD/CAD",
    "GOLD":    "XAU/USD",
    "BTCUSD":  "BTC/USD",
}

# Indicator Settings
RSI_PERIOD      = 14
RSI_OVERSOLD    = 40
RSI_OVERBOUGHT  = 60
EMA_FAST        = 20
EMA_SLOW        = 50
EMA_TREND       = 200
ATR_PERIOD      = 14
ATR_SL_MULTI    = 1.5
ATR_TP_MULTI    = 2.5

# Signal Filter
MIN_SCORE       = 3

# Schedule
SIGNAL_TIME_UTC = "00:05"

# Data
CANDLES_PERIOD  = "1y"