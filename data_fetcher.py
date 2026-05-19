import yfinance as yf
import pandas as pd

class DataFetcher:
    def get_candles(self, symbol: str, yf_ticker: str, period: str = "730d") -> pd.DataFrame | None:
        try:
            df = yf.download(
                yf_ticker,
                period="730d",     
                interval="1h",      
                progress=False,
                auto_adjust=True,
            )

            if df is None or df.empty:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)

            if len(df) < 50:
                return None

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None