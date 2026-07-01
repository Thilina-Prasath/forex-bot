"""
test_signal2.py — _detect_news_direction logic debug කරයි
"""
from analyzer import ForexAnalyzer
from data_fetcher import DataFetcher
from config import FOREX_PAIRS
import unittest.mock as mock

pairs = list(FOREX_PAIRS.items())
name, ticker = pairs[0]

df = DataFetcher().get_candles(name, ticker, '5m')
fa = ForexAnalyzer(name, df)

c = df["Close"]
closes = [round(float(c.iloc[i]), 5) for i in range(-5, 0)]
p, p1, p2, p3 = closes[-1], closes[-2], closes[-3], closes[-4]

ema20 = round(float(fa._ema(20).iloc[-1]), 5)
rsi   = round(float(fa._rsi().iloc[-1]),   2)

print(f"Last 5 closes : {closes}")
print(f"p={p}, p1={p1}, p2={p2}, p3={p3}")
print(f"EMA20={ema20}, RSI={rsi}")
print()
print(f"rising  = p>p1 and p1>p2 : {p > p1 and p1 > p2}")
print(f"falling = p<p1 and p1<p2 : {p < p1 and p1 < p2}")
print(f"p > ema20 : {p > ema20}")
print(f"p < ema20 : {p < ema20}")
print(f"rsi > 45  : {rsi > 45}")
print(f"rsi < 55  : {rsi < 55}")