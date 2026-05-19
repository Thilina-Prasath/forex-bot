import yfinance as yf
import pandas as pd


class DataFetcher:

    def get_candles(self, symbol: str, yf_ticker: str, period: str = "1y") -> pd.DataFrame | None:
        try:
            df = yf.download(
                yf_ticker,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True,
            )

            if df is None or df.empty:
                print(f"     ❌ No data: {symbol}")
                return None

            # Multi-index flatten
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename to standard
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)

            if len(df) < 50:
                print(f"     ❌ Insufficient data: {symbol} ({len(df)} candles)")
                return None

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None