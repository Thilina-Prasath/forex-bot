"""
data_fetcher.py
Yahoo Finance (yfinance) මඟින් දත්ත ලබාගැනීම.

Interval strategy:
  Normal scan  → "1h" interval, 60d period  (1440 candles — EMA200 ට ඕනෑ)
  News scan    → "5m" interval,  5d period  (1440 candles — fast momentum)
"""

import yfinance as yf
import pandas as pd


# ── Yahoo Finance interval → period mapping ──────────────────────────────────
# EMA200 ට minimum 200 candles ඕනේ. 
# Yahoo limits: 1m=7d, 5m=60d, 15m=60d, 30m=60d, 1h=730d, 1d=max
INTERVAL_PERIOD_MAP = {
    "1m":  "7d",    # 7d × 1440 min/day ≈ 10080 candles (market hours only ~2500)
    "2m":  "7d",
    "5m":  "60d",   # 60d × 288 = 17280 → plenty
    "15m": "60d",
    "30m": "60d",
    "1h":  "60d",   # 60d × 24 = 1440 → EMA200 OK ✅
    "60m": "60d",
    "4h":  "60d",
    "1d":  "max",
}

DEFAULT_INTERVAL = "1h"   # Normal technical scan
NEWS_INTERVAL    = "5m"   # News momentum scan (fast candles)


class DataFetcher:
    def __init__(self):
        pass

    def get_candles(
        self,
        symbol: str,
        ticker: str,
        interval: str = DEFAULT_INTERVAL,
    ) -> pd.DataFrame | None:
        """
        Yahoo Finance හරහා candle data ගනී.

        Args:
            symbol:   bot display name   (e.g. "EURUSD")
            ticker:   Yahoo ticker       (e.g. "EURUSD=X", "GC=F", "BTC-USD")
            interval: candle size        (e.g. "1h", "5m") — NOT period like "1y"
        """

        # ── Ticker normalise ─────────────────────────────────────────────────
        yf_ticker = ticker
        if len(ticker) == 6 and "=" not in ticker and "-" not in ticker:
            yf_ticker = f"{ticker}=X"
        elif ticker.upper() in ("GOLD", "XAUUSD"):
            yf_ticker = "GC=F"
        elif ticker.upper() == "BTCUSD":
            yf_ticker = "BTC-USD"

        # ── Interval validation + fix ────────────────────────────────────────
        # config.py ෙදිගටම "1y" වැනි wrong value ආවොත් default ට fallback
        valid_intervals = {"1m","2m","5m","15m","30m","60m","1h","4h","1d","5d","1wk","1mo","3mo"}
        if interval not in valid_intervals:
            print(f"     ⚠️  Invalid interval '{interval}' → using '{DEFAULT_INTERVAL}'")
            interval = DEFAULT_INTERVAL

        period = INTERVAL_PERIOD_MAP.get(interval, "60d")

        try:
            data = yf.download(
                tickers=yf_ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )

            if data is None or data.empty:
                print(f"     ❌ No data values found for {symbol} ({yf_ticker})")
                return None

            # ── MultiIndex flatten ───────────────────────────────────────────
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
            df = df.astype(float).dropna()

            if len(df) < 50:
                print(f"     ❌ Too few candles ({len(df)}) for {symbol} — skipping")
                return None

            print(f"     📦 {len(df)} candles ({interval} / {period})")
            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol} / {yf_ticker}): {e}")
            return None

    def get_news_candles(self, symbol: str, ticker: str) -> pd.DataFrame | None:
        """News momentum ට fast (5m) candles — short-term direction detect කිරීමට."""
        return self.get_candles(symbol, ticker, interval=NEWS_INTERVAL)