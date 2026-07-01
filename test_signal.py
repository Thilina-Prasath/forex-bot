"""
test_signal.py — News momentum SL/TP verify කරන test script
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

with mock.patch('analyzer.check_news_conflict', return_value=('NEWS_MOMENTUM', 'Test News')):
    sig = fa.generate()

print(f"direction   : {sig['direction']}")
print(f"stop_loss   : {sig.get('stop_loss')}")
print(f"take_profit1: {sig.get('take_profit1')}")
print(f"take_profit2: {sig.get('take_profit2')}")
print(f"risk_reward : {sig.get('risk_reward')}")
print(f"buy_score   : {sig['buy_score']}")
print(f"sell_score  : {sig['sell_score']}")
print(f"strength    : {sig['strength']}%")

if sig.get('stop_loss') and sig.get('take_profit1'):
    print("\n✅ SL/TP correctly generated!")
else:
    print("\n❌ SL/TP still None — news direction NEUTRAL")
    print(f"Reasons: {sig.get('reasons')}")