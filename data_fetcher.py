import yfinance as yf
import pandas as pd
import requests
import time

class DataFetcher:
    def __init__(self):
        # 1. බ්‍රවුසරයකින් එනවා වගේ පෙන්වීමට Session එකක් සැකසීම (Block වීම වැළැක්වීමට)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def get_candles(self, symbol: str, yf_ticker: str, period: str = "730d") -> pd.DataFrame | None:
        # 2. එකපාර යැවීම නිසා Block වීම වැළැක්වීමට තත්පර 2ක් රැඳී සිටීම
        time.sleep(2) 
        
        try:
            # session=self.session යන්න අලුතින් එක් කර ඇත
            df = yf.download(
                yf_ticker,
                period=period,
                interval="1h",
                progress=False,
                auto_adjust=True,
                session=self.session  
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