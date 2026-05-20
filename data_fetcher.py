import requests
import pandas as pd
import os
import time

class DataFetcher:
    def __init__(self):
        # Render එකේ Environment Variable එකෙන් Key එක ගන්නවා
        self.api_key = os.environ.get("ALPHA_VANTAGE_KEY")

    def get_candles(self, symbol: str, to_symbol: str, period: str = None) -> pd.DataFrame | None:
        if not self.api_key:
            print(" ❌ Error: ALPHA_VANTAGE_KEY is missing!")
            return None

        # Alpha Vantage API එකෙන් 1-Hour දත්ත (FX_INTRADAY) ඉල්ලීම
        url = (
            f"https://www.alphavantage.co/query?"
            f"function=FX_INTRADAY&from_symbol={to_symbol}&to_symbol=USD"
            f"&interval=60min&outputsize=full&apikey={self.api_key}"
        )
        # USD මුලට එන ඒවා (USDJPY, USDCAD, USDCHF) හරවන්න ඕනේ
        if symbol.startswith("USD"):
             url = (
                f"https://www.alphavantage.co/query?"
                f"function=FX_INTRADAY&from_symbol=USD&to_symbol={to_symbol}"
                f"&interval=60min&outputsize=full&apikey={self.api_key}"
            )

        try:
            # Free API එකේ විනාඩියකට request 5ක් විතරයි පුළුවන්, ඒ නිසා පොඩි delay එකක් දානවා
            time.sleep(12) 
            
            response = requests.get(url)
            data = response.json()

            # Error Messages ඇවිත්ද කියලා බැලීම
            if "Error Message" in data or "Information" in data:
                print(f"     ❌ API Error ({symbol}): {data.get('Information', 'Unknown Error')}")
                return None

            time_series = data.get("Time Series FX (60min)")
            if not time_series:
                return None

            # දත්ත DataFrame එකකට හැරවීම
            df = pd.DataFrame.from_dict(time_series, orient="index")
            df = df.rename(columns={
                "1. open": "Open",
                "2. high": "High",
                "3. low": "Low",
                "4. close": "Close"
            })
            
            # දත්ත Float වලට හැරවීම සහ Sort කිරීම
            df = df.astype(float)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # Volume එකක් API එකෙන් දෙන්නේ නැති නිසා බොරු 0 ක් දානවා (කෝඩ් එකේ Error එන එක නවත්වන්න)
            df['Volume'] = 0

            return df.tail(300) # අන්තිම පැය 300 දත්ත යැවීම

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol}): {e}")
            return None