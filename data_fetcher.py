"""
data_fetcher.py
Yahoo Finance (yfinance) මඟින් දත්ත ලබාගැනීම.
v2: Retry logic + alternate tickers for unstable pairs
"""

import yfinance as yf
import pandas as pd
import time

INTERVAL_PERIOD_MAP = {
    "1m":  "7d",
    "2m":  "7d",
    "5m":  "60d",
    "15m": "60d",
    "30m": "60d",
    "1h":  "60d",
    "60m": "60d",
    "4h":  "60d",
    "1d":  "max",
}

DEFAULT_INTERVAL = "1h"
NEWS_INTERVAL    = "5m"

# Alternate tickers — Yahoo Finance unstable වූ විට fallback
ALTERNATE_TICKERS = {
    "USDCHF=X": ["CHF=X", "USDCHF=X"],
    "USDCAD=X": ["CAD=X", "USDCAD=X"],
    "USDJPY=X": ["JPY=X", "USDJPY=X"],
}


class DataFetcher:
    def __init__(self):
        pass

    def _try_download(self, ticker: str, period: str, interval: str) -> pd.DataFrame | None:
        """Single download attempt."""
        try:
            data = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            if data is None or data.empty:
                return None
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)
            df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
            df = df.astype(float).dropna()
            return df if len(df) >= 50 else None
        except Exception:
            return None

    def get_candles(
        self,
        symbol: str,
        ticker: str,
        interval: str = DEFAULT_INTERVAL,
    ) -> pd.DataFrame | None:

        # ── Ticker normalise ─────────────────────────────────────────────────
        yf_ticker = ticker
        if len(ticker) == 6 and "=" not in ticker and "-" not in ticker:
            yf_ticker = f"{ticker}=X"
        elif ticker.upper() in ("GOLD", "XAUUSD"):
            yf_ticker = "GC=F"
        elif ticker.upper() == "BTCUSD":
            yf_ticker = "BTC-USD"

        # ── Interval validation ──────────────────────────────────────────────
        valid_intervals = {"1m","2m","5m","15m","30m","60m","1h","4h","1d","5d","1wk","1mo","3mo"}
        if interval not in valid_intervals:
            print(f"     ⚠️  Invalid interval '{interval}' → using '{DEFAULT_INTERVAL}'")
            interval = DEFAULT_INTERVAL

        period = INTERVAL_PERIOD_MAP.get(interval, "60d")

        # ── Attempt 1: primary ticker ────────────────────────────────────────
        df = self._try_download(yf_ticker, period, interval)
        if df is not None:
            print(f"     📦 {len(df)} candles ({interval} / {period})")
            return df

        # ── Attempt 2: alternate tickers (unstable pairs) ────────────────────
        alternates = ALTERNATE_TICKERS.get(yf_ticker, [])
        for alt_ticker in alternates:
            if alt_ticker == yf_ticker:
                continue
            print(f"     🔄 Retry with alternate ticker: {alt_ticker}")
            time.sleep(1)
            df = self._try_download(alt_ticker, period, interval)
            if df is not None:
                print(f"     📦 {len(df)} candles ({interval} / {period}) [via {alt_ticker}]")
                return df

        # ── Attempt 3: retry after 3s ────────────────────────────────────────
        print(f"     ⏳ Retry in 3s for {symbol}...")
        time.sleep(3)
        df = self._try_download(yf_ticker, period, interval)
        if df is not None:
            print(f"     📦 {len(df)} candles ({interval} / {period}) [retry OK]")
            return df

        print(f"     ❌ No data for {symbol} ({yf_ticker}) — skipping")
        return None

    def get_news_candles(self, symbol: str, ticker: str) -> pd.DataFrame | None:
        return self.get_candles(symbol, ticker, interval=NEWS_INTERVAL)