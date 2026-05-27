import requests
import pandas as pd
import time
from config import TWELVEDATA_KEY

class DataFetcher:
    def __init__(self):
        self.api_key = TWELVEDATA_KEY

    def get_candles(self, symbol: str, ticker: str, period: str = None) -> pd.DataFrame | None:
        if not self.api_key:
            print("     ❌ Error: TWELVEDATA_KEY is missing!")
            return None

        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={ticker}&interval=1h&outputsize=300&apikey={self.api_key}"
        )

        try:
            time.sleep(8)

            response = requests.get(url, timeout=15)
            data = response.json()

            # API error check
            if "status" in data and data["status"] == "error":
                print(f"     ❌ API Error ({symbol}): {data.get('message', 'Unknown Error')}")
                return None

            values = data.get("values")
            if not values:
                print(f"     ❌ No data values found for {symbol}")
                return None

            # DataFrame build
            df = pd.DataFrame(values)

            # ── FutureWarning Fix ────────────────────────────────────────────
            # කලින්: df['datetime'] = pd.to_datetime(df['datetime'])
            # pandas 3.0 හිදී chained assignment break වෙනවා.
            # Fix: assign directly without chaining
            df = df.assign(datetime=pd.to_datetime(df["datetime"]))
            df = df.set_index("datetime")

            df = df.rename(columns={
                "open":  "Open",
                "high":  "High",
                "low":   "Low",
                "close": "Close",
            })

            df = df.astype(float)
            df = df.sort_index()
            df["Volume"] = 0

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None