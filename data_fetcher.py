"""
data_fetcher.py
Yahoo Finance (yfinance) මඟින් දත්ත ලබාගැනීම.
API limits නොමැත, එබැවින් M1 (1-Minute) දත්ත පවා ලබා ගත හැක.
"""

import yfinance as yf
import pandas as pd

class DataFetcher:
    def __init__(self):
        # Yahoo Finance සඳහා API Key අවශ්‍ය නොවේ.
        pass

    def get_candles(self, symbol: str, ticker: str, interval: str = "1h") -> pd.DataFrame | None:
        """
        Yahoo Finance හරහා දත්ත ලබා ගැනීම.
        
        Args:
            symbol: බොට් පාවිච්චි කරන නම (උදා: EURUSD)
            ticker: Yahoo Finance හි Ticker නම (උදා: EURUSD=X, GC=F)
            interval: දත්ත කාල පරතරය (උදා: "1m", "5m", "15m", "1h")
        """
        # Yahoo Finance සඳහා Ticker ආකෘතිය සෑදීම
        # Forex pairs වලට '=X' එකතු විය යුතුයි. Crypto වලට '-USD' එකතු විය යුතුයි.
        # config.py හි දැනටමත් යම් ආකෘතියක් ඇත්නම් එයම භාවිතා කරන්න. 
        # එසේ නොමැති නම් මෙහිදී සකසමු:
        yf_ticker = ticker
        
        # මෙය ආරක්ෂිත පියවරක් පමණි (ticker එක වැරදිවී ඇත්නම් නිවැරදි කිරීමට)
        if len(ticker) == 6 and not ("=" in ticker or "-" in ticker):
             yf_ticker = f"{ticker}=X" # උදා: EURUSD=X
        elif ticker.upper() in ["GOLD", "XAUUSD"]:
             yf_ticker = "GC=F" # Gold Futures (yfinance standard)
        elif ticker.upper() == "BTCUSD":
             yf_ticker = "BTC-USD"
             
        try:
            # ── දත්ත ඉල්ලීම (Fetch) ──────────────────────────────────────────
            # interval="1m" සඳහා ලබාගත හැක්කේ උපරිම දින 7ක දත්ත පමණි (yfinance නීතිය).
            # "1h" සඳහා දින 60ක් ලබාගත හැක. අපි අවශ්‍ය ප්‍රමාණයට පමණක් ලබා ගනිමු.
            
            period = "5d" if interval in ["1m", "5m"] else "60d"
            
            data = yf.download(tickers=yf_ticker, period=period, interval=interval, progress=False)

            if data.empty:
                print(f"     ❌ No data values found for {symbol} ({yf_ticker})")
                return None

            # ── DataFrame Build & Clean ──────────────────────────────────────
            # yfinance මඟින් MultiIndex තීරු ලබා දිය හැක, එබැවින් එය සාමාන්‍ය තත්ත්වයට පත් කරමු
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            df = data.copy()
            
            # අවශ්‍ය තීරු පමණක් තබා ගැනීම
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            # දත්ත float බවට පත් කිරීම
            df = df.astype(float)
            
            # දත්ත හිස්තැන් (NaN) ඇත්නම් ඉවත් කිරීම (Forex වල සති අන්ත දත්ත නිසා)
            df = df.dropna()

            return df

        except Exception as e:
            print(f"     ❌ Fetch error ({symbol} / {yf_ticker}): {e}")
            return None