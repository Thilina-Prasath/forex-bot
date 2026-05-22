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

        url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=300&apikey={self.api_key}"

        try:
            time.sleep(8) 
            
            response = requests.get(url, timeout=15)
            data = response.json()

            # Error Messages check
            if "status" in data and data["status"] == "error":
                print(f"     ❌ API Error ({symbol}): {data.get('message', 'Unknown Error')}")
                return None

            values = data.get("values")
            if not values:
                print(f"     ❌ No data values found for {symbol}")
                return None

            # data convert DataFrame 
            df = pd.DataFrame(values)
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            
            df = df.rename(columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close"
            })
            
            df = df.astype(float)
            df = df.sort_index()

            df['Volume'] = 0

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None