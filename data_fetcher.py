"""
Data Fetcher v5 — TwelveData API (Hourly Data)
────────────────────────────────────────────────
දවසකට Requests 800ක් නොමිලේ ලබාදෙන TwelveData API භාවිතය.
පැයෙන් පැයට Market එක ස්කෑන් කිරීමට මෙය වඩාත් සුදුසුය.
"""

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

        # 1-Hour දත්ත ලබාගැනීමේ URL එක
        url = f"https://api.twelvedata.com/time_series?symbol={ticker}&interval=1h&outputsize=300&apikey={self.api_key}"

        try:
            # Free API එකේ විනාඩියකට request 8ක් පමණක් ඇති බැවින් තත්පර 8ක Delay එකක් දාමු
            time.sleep(8) 
            
            response = requests.get(url, timeout=15)
            data = response.json()

            # Error Messages පරීක්ෂා කිරීම
            if "status" in data and data["status"] == "error":
                print(f"     ❌ API Error ({symbol}): {data.get('message', 'Unknown Error')}")
                return None

            values = data.get("values")
            if not values:
                print(f"     ❌ No data values found for {symbol}")
                return None

            # දත්ත DataFrame එකකට හැරවීම
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

            # බොට් එකට අත්‍යවශ්‍ය වන Volume එක 0 ලෙස යෙදීම
            df['Volume'] = 0

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None