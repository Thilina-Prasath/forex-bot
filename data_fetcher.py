"""
Data Fetcher v4 — Cloud Compatible
────────────────────────────────────
Render/Cloud servers හි yfinance block වෙනවා.
Solution: Alpha Vantage free API use කරනවා.

FREE API KEY ගන්නේ කොහොමද:
  1. https://www.alphavantage.co/support/#api-key
  2. "GET FREE API KEY" click කරන්න
  3. Email දාලා key ගන්න (instant, free)
  4. config.py හි ALPHA_VANTAGE_KEY = "YOUR_KEY" දාන්න

Free plan: 25 requests/day, 5 requests/minute
8 pairs × 1 request = 8 requests/day ✅
"""

import requests
import pandas as pd
import time
import os
from config import ALPHA_VANTAGE_KEY


# Alpha Vantage symbol map
AV_SYMBOLS = {
    # Forex pairs → from/to
    "EURUSD":  ("EUR", "USD"),
    "GBPUSD":  ("GBP", "USD"),
    "USDJPY":  ("USD", "JPY"),
    "AUDUSD":  ("AUD", "USD"),
    "USDCHF":  ("USD", "CHF"),
    "USDCAD":  ("USD", "CAD"),
    # Commodities/Crypto → special handling
    "GOLD":    ("XAU", "USD"),
    "BTCUSD":  ("BTC", "USD"),
}


class DataFetcher:

    def __init__(self):
        self.key = ALPHA_VANTAGE_KEY
        self.base = "https://www.alphavantage.co/query"

    def get_candles(self, symbol: str, yf_ticker: str = None, period: str = "1y") -> pd.DataFrame | None:
        """
        Alpha Vantage API වලින් daily OHLCV data ගෙනෙනවා.
        """
        if symbol in ("GOLD", "BTCUSD"):
            return self._get_crypto_or_commodity(symbol)
        else:
            return self._get_forex(symbol)

    def _get_forex(self, symbol: str) -> pd.DataFrame | None:
        if symbol not in AV_SYMBOLS:
            print(f"     ❌ Unknown symbol: {symbol}")
            return None

        from_sym, to_sym = AV_SYMBOLS[symbol]

        params = {
            "function":    "FX_DAILY",
            "from_symbol": from_sym,
            "to_symbol":   to_sym,
            "outputsize":  "compact",   # last 100 days
            "apikey":      self.key,
        }

        try:
            r = requests.get(self.base, params=params, timeout=15)
            data = r.json()

            if "Note" in data:
                print(f"     ⚠️  Rate limit hit — waiting 60s...")
                time.sleep(60)
                r = requests.get(self.base, params=params, timeout=15)
                data = r.json()

            if "Error Message" in data:
                print(f"     ❌ API error: {data['Error Message'][:50]}")
                return None

            ts_key = "Time Series FX (Daily)"
            if ts_key not in data:
                print(f"     ❌ No data key. Response: {str(data)[:100]}")
                return None

            ts = data[ts_key]
            rows = []
            for date_str, vals in ts.items():
                rows.append({
                    "Date":   pd.to_datetime(date_str),
                    "Open":   float(vals["1. open"]),
                    "High":   float(vals["2. high"]),
                    "Low":    float(vals["3. low"]),
                    "Close":  float(vals["4. close"]),
                    "Volume": 0,
                })

            df = pd.DataFrame(rows).set_index("Date").sort_index()
            df.dropna(inplace=True)

            if len(df) < 50:
                print(f"     ❌ Insufficient data ({len(df)} rows)")
                return None

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None

    def _get_crypto_or_commodity(self, symbol: str) -> pd.DataFrame | None:
        """
        GOLD → DIGITAL_CURRENCY_DAILY (XAU not supported in free)
        BTCUSD → DIGITAL_CURRENCY_DAILY
        """
        if symbol == "BTCUSD":
            params = {
                "function":      "DIGITAL_CURRENCY_DAILY",
                "symbol":        "BTC",
                "market":        "USD",
                "apikey":        self.key,
            }
            open_key  = "1. open"
            high_key  = "2. high"
            low_key   = "3. low"
            close_key = "4. close"
            ts_key    = "Time Series (Digital Currency Daily)"
        else:
            # GOLD — use forex XAU/USD
            params = {
                "function":    "FX_DAILY",
                "from_symbol": "XAU",
                "to_symbol":   "USD",
                "outputsize":  "compact",
                "apikey":      self.key,
            }
            open_key  = "1. open"
            high_key  = "2. high"
            low_key   = "3. low"
            close_key = "4. close"
            ts_key    = "Time Series FX (Daily)"

        try:
            r    = requests.get(self.base, params=params, timeout=15)
            data = r.json()

            if "Note" in data:
                print(f"     ⚠️  Rate limit — waiting 60s...")
                time.sleep(60)
                r    = requests.get(self.base, params=params, timeout=15)
                data = r.json()

            if ts_key not in data:
                print(f"     ❌ No data for {symbol}")
                return None

            rows = []
            for date_str, vals in data[ts_key].items():
                rows.append({
                    "Date":   pd.to_datetime(date_str),
                    "Open":   float(vals[open_key]),
                    "High":   float(vals[high_key]),
                    "Low":    float(vals[low_key]),
                    "Close":  float(vals[close_key]),
                    "Volume": 0,
                })

            df = pd.DataFrame(rows).set_index("Date").sort_index()
            df.dropna(inplace=True)

            if len(df) < 50:
                return None

            return df

        except Exception as e:
            print(f"     ❌ {symbol} fetch error: {e}")
            return None