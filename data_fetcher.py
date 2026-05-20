import yfinance as yf
import pandas as pd
import requests
import time
import random

class DataFetcher:
    def __init__(self):
        # විවිධ Web Browsers වල නම් (බොට් කෙනෙක් නෙවෙයි කියලා පෙන්වීමට)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]

    def get_candles(self, symbol: str, yf_ticker: str, period: str = "730d") -> pd.DataFrame | None:
        # තත්පර 3 ත් 6 ත් අතර අහඹු වෙලාවක් රැඳී සිටීම (Random Delay)
        delay = random.uniform(3, 6)
        time.sleep(delay)
        
        try:
            # අලුත් Session එකක් සාදා Random User-Agent එකක් යෙදීම
            session = requests.Session()
            session.headers.update({
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })

            # yf.download වෙනුවට වඩාත් ආරක්ෂිත yf.Ticker ක්‍රමය භාවිතා කිරීම
            ticker = yf.Ticker(yf_ticker, session=session)
            df = ticker.history(period=period, interval="1h", auto_adjust=True)

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