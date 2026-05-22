"""
Indicators (6 points max):
  1. EMA200    — Long-term trend
  2. EMA 20/50 — Medium trend crossover
  3. RSI       — Refined zones (no half points)
  4. MACD      — Histogram + zero-line
  5. Bollinger Bands — Band position
  6. Momentum  — 3/4 candle price action

Signal: BUY/SELL score >= MIN_SCORE → signal sent
"""

import pandas as pd
import numpy as np
from config import (
    RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT,
    EMA_FAST, EMA_SLOW, EMA_TREND,
    ATR_PERIOD, ATR_SL_MULTI, ATR_TP_MULTI,
    MIN_SCORE,
)


class ForexAnalyzer:

    def __init__(self, symbol: str, df: pd.DataFrame):
        self.symbol = symbol
        self.df = df.copy()

    def _ema(self, period):
        return self.df["Close"].ewm(span=period, adjust=False).mean()

    def _rsi(self):
        delta = self.df["Close"].diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        ag = gain.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
        al = loss.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
        rs = ag / al.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _macd(self):
        e12  = self.df["Close"].ewm(span=12, adjust=False).mean()
        e26  = self.df["Close"].ewm(span=26, adjust=False).mean()
        line = e12 - e26
        sig  = line.ewm(span=9, adjust=False).mean()
        hist = line - sig
        return line, sig, hist

    def _bollinger(self, period=20, std=2.0):
        sma = self.df["Close"].rolling(window=period).mean()
        sd  = self.df["Close"].rolling(window=period).std()
        return sma + sd * std, sma, sma - sd * std

    def _atr(self):
        h, l, c = self.df["High"], self.df["Low"], self.df["Close"]
        tr = pd.concat([
            h - l,
            (h - c.shift()).abs(),
            (l - c.shift()).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    def generate(self) -> dict:
        ema20  = self._ema(EMA_FAST)
        ema50  = self._ema(EMA_SLOW)
        ema200 = self._ema(EMA_TREND)
        rsi    = self._rsi()
        macd_l, macd_s, macd_h = self._macd()
        bb_up, _, bb_lo = self._bollinger()
        atr = self._atr()

        c  = self.df["Close"]
        p  = round(float(c.iloc[-1]), 5)
        p1 = round(float(c.iloc[-2]), 5)
        p2 = round(float(c.iloc[-3]), 5)
        p3 = round(float(c.iloc[-4]), 5)

        rsi_now   = round(float(rsi.iloc[-1]), 2)
        rsi_prev  = round(float(rsi.iloc[-2]), 2)
        rsi_prev2 = round(float(rsi.iloc[-3]), 2)

        ema20_v  = round(float(ema20.iloc[-1]),  5)
        ema50_v  = round(float(ema50.iloc[-1]),  5)
        ema200_v = round(float(ema200.iloc[-1]), 5)

        macd_v   = round(float(macd_l.iloc[-1]), 6)
        sig_v    = round(float(macd_s.iloc[-1]), 6)
        hist_now = round(float(macd_h.iloc[-1]), 6)
        hist_pre = round(float(macd_h.iloc[-2]), 6)

        bbu_v = round(float(bb_up.iloc[-1]), 5)
        bbl_v = round(float(bb_lo.iloc[-1]), 5)
        atr_v = round(float(atr.iloc[-1]),   5)

        buy_score  = 0
        sell_score = 0
        buy_why    = []
        sell_why   = []

        # 1. EMA200
        if p > ema200_v:
            buy_score += 1
            buy_why.append(f"EMA200 ✅ Uptrend")
        else:
            sell_score += 1
            sell_why.append(f"EMA200 ❌ Downtrend")

        # 2. EMA 20/50
        if ema20_v > ema50_v:
            buy_score += 1
            buy_why.append(f"EMA20>50 ✅ Bullish")
        else:
            sell_score += 1
            sell_why.append(f"EMA20<50 ❌ Bearish")

        # 3. RSI — refined (no half points)
        rsi_rising  = rsi_now > rsi_prev > rsi_prev2
        rsi_falling = rsi_now < rsi_prev < rsi_prev2

        if rsi_now < 40:
            buy_score += 1
            buy_why.append(f"RSI {rsi_now} ✅ Oversold")
        elif rsi_now > 60:
            sell_score += 1
            sell_why.append(f"RSI {rsi_now} ❌ Overbought")
        elif 40 <= rsi_now <= 47 and rsi_rising:
            buy_score += 1
            buy_why.append(f"RSI {rsi_now} ✅ Rising from low")
        elif 53 <= rsi_now <= 60 and rsi_falling:
            sell_score += 1
            sell_why.append(f"RSI {rsi_now} ❌ Falling from high")
        # 47-53 = truly neutral, 0 points

        # 4. MACD
        if macd_v > sig_v and hist_now > hist_pre:
            buy_score += 1
            buy_why.append(f"MACD ✅ Bullish momentum")
        elif macd_v < sig_v and hist_now < hist_pre:
            sell_score += 1
            sell_why.append(f"MACD ❌ Bearish momentum")

        # 5. Bollinger Bands
        bb_range = bbu_v - bbl_v
        bb_pct   = (p - bbl_v) / bb_range if bb_range != 0 else 0.5

        if p <= bbl_v:
            buy_score += 1
            buy_why.append(f"BB ✅ Below lower band")
        elif p >= bbu_v:
            sell_score += 1
            sell_why.append(f"BB ❌ Above upper band")
        elif bb_pct < 0.30:
            buy_score += 1
            buy_why.append(f"BB ✅ Lower zone")
        elif bb_pct > 0.70:
            sell_score += 1
            sell_why.append(f"BB ❌ Upper zone")

        # 6. Momentum (3-4 candles)
        if p > p1 > p2 > p3:
            buy_score += 1
            buy_why.append("Momentum ✅ 4 bull candles")
        elif p > p1 > p2:
            buy_score += 1
            buy_why.append("Momentum ✅ 3 bull candles")
        elif p < p1 < p2 < p3:
            sell_score += 1
            sell_why.append("Momentum ❌ 4 bear candles")
        elif p < p1 < p2:
            sell_score += 1
            sell_why.append("Momentum ❌ 3 bear candles")

        # Direction
        if buy_score >= MIN_SCORE and buy_score > sell_score:
            direction = "BUY"
            reasons   = buy_why
            strength  = round((buy_score / 6) * 100)
        elif sell_score >= MIN_SCORE and sell_score > buy_score:
            direction = "SELL"
            reasons   = sell_why
            strength  = round((sell_score / 6) * 100)
        else:
            direction = "NEUTRAL"
            reasons   = ["⚖️ No clear signal"]
            strength  = round((max(buy_score, sell_score) / 6) * 100)

        # Risk Management
        sl = tp1 = tp2 = rr = None
        if direction == "BUY":
            sl  = round(p - atr_v * ATR_SL_MULTI,       5)
            tp1 = round(p + atr_v * ATR_TP_MULTI * 0.6, 5)
            tp2 = round(p + atr_v * ATR_TP_MULTI,       5)
            rr  = round(ATR_TP_MULTI / ATR_SL_MULTI, 1)
        elif direction == "SELL":
            sl  = round(p + atr_v * ATR_SL_MULTI,       5)
            tp1 = round(p - atr_v * ATR_TP_MULTI * 0.6, 5)
            tp2 = round(p - atr_v * ATR_TP_MULTI,       5)
            rr  = round(ATR_TP_MULTI / ATR_SL_MULTI, 1)

        return {
            "symbol":       self.symbol,
            "price":        p,
            "direction":    direction,
            "strength":     strength,
            "buy_score":    buy_score,
            "sell_score":   sell_score,
            "reasons":      reasons,
            "rsi":          rsi_now,
            "ema20":        ema20_v,
            "ema50":        ema50_v,
            "ema200":       ema200_v,
            "macd":         macd_v,
            "atr":          atr_v,
            "stop_loss":    sl,
            "take_profit1": tp1,
            "take_profit2": tp2,
            "risk_reward":  rr,
        }