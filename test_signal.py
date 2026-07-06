"""
test_signal.py — News momentum SL/TP verify කරන test script (v2)
"""
from analyzer import ForexAnalyzer
from data_fetcher import DataFetcher
from config import FOREX_PAIRS
import unittest.mock as mock

pairs = list(FOREX_PAIRS.items())
name, ticker = pairs[0]

print(f"Testing: {name}")
df = DataFetcher().get_candles(name, ticker, '5m')
fa = ForexAnalyzer(name, df)

# Raw data debug
c = df["Close"]
closes = [round(float(c.iloc[i]), 5) for i in range(-5, 0)]
p   = closes[-1]
p2  = closes[-3]
ema20 = round(float(fa._ema(20).iloc[-1]), 5)
rsi   = round(float(fa._rsi().iloc[-1]), 2)

print(f"Last 5 closes : {closes}")
print(f"p={p}, p2={p2}")
print(f"EMA20={ema20}, RSI={rsi}")
print(f"net_rising  = p>p2 : {p > p2}")
print(f"net_falling = p<p2 : {p < p2}")
print(f"p >= ema20 : {p >= ema20}")
print(f"p <= ema20 : {p <= ema20}")
print(f"rsi >= 45  : {rsi >= 45}")
print(f"rsi <= 55  : {rsi <= 55}")
print()

# News mock test
with mock.patch('analyzer.check_news_conflict', return_value=('NEWS_MOMENTUM', 'Test News')):
    sig = fa.generate()

print(f"direction   : {sig['direction']}")
print(f"stop_loss   : {sig.get('stop_loss')}")
print(f"take_profit1: {sig.get('take_profit1')}")
print(f"take_profit2: {sig.get('take_profit2')}")
print(f"risk_reward : {sig.get('risk_reward')}")
print(f"buy_score   : {sig['buy_score']}")
print(f"sell_score  : {sig['sell_score']}")
print(f"reasons     : {sig.get('reasons')}")

if sig.get('stop_loss') and sig.get('take_profit1'):
    print("\n✅ SL/TP correctly generated! Bot ready for auto-trade.")
else:
    print("\n❌ SL/TP still None")
    print("Reason:", sig.get('reasons'))
