"""
Indicators (6 points max):
  1. EMA200    — Long-term trend
  2. EMA 20/50 — Medium trend crossover
  3. RSI       — Refined zones (no half points)
  4. MACD      — Histogram + zero-line
  5. Bollinger Bands — Band position
  6. Momentum  — 3/4 candle price action

Signal Rules:
  - BUY/SELL score >= MIN_SCORE → signal candidate
  - RSI OR BB confirmation mandatory (Option B)
  - EMA200 direction conflict rejected (Option C)
  - Session filter: Pair-specific sessions only

Session Coverage (LK Time / UTC):
  Sydney   : 03:30 AM – 12:30 PM LK  (22:00 – 07:00 UTC)
  Tokyo    : 05:30 AM – 02:30 PM LK  (00:00 – 09:00 UTC)
  London   : 01:30 PM – 10:30 PM LK  (08:00 – 17:00 UTC)
  New York : 06:30 PM – 03:30 AM LK  (13:00 – 22:00 UTC)

Best pairs per session:
  Sydney   → AUDUSD, AUDJPY, AUDNZD, NZDUSD
  Tokyo    → USDJPY, AUDJPY, EURJPY, GBPJPY
  London   → EURUSD, GBPUSD, EURGBP, USDCHF, USDCAD
  NY       → EURUSD, GBPUSD, USDCAD, GOLD, BTCUSD
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from config import (
    RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT,
    EMA_FAST, EMA_SLOW, EMA_TREND,
    ATR_PERIOD, ATR_SL_MULTI, ATR_TP_MULTI,
    MIN_SCORE,
)

# ── Signal validity window (minutes) ────────────────────────────────────────
SIGNAL_VALID_MINUTES = 3

# ── Pair → Valid sessions mapping ───────────────────────────────────────────
# UTC hour ranges: (start_inclusive, end_exclusive)
# Sydney:  22–07 UTC  (crosses midnight, special handling)
# Tokyo:   00–09 UTC
# London:  08–17 UTC
# NY:      13–22 UTC

PAIR_SESSIONS = {
    # Australia session pairs
    "AUDUSD": [("sydney", "Australian Dollar — Sydney+Tokyo best")],
    "AUDJPY": [("sydney", "AUD+JPY — Sydney+Tokyo overlap best")],
    "AUDNZD": [("sydney", "Australian pairs — Sydney best")],
    "NZDUSD": [("sydney", "NZD — Sydney best")],

    # Japan session pairs
    "USDJPY": [("tokyo",  "Japanese Yen — Tokyo best")],
    "EURJPY": [("tokyo",  "JPY cross — Tokyo best")],
    "GBPJPY": [("tokyo",  "JPY cross — Tokyo best")],

    # London session pairs
    "EURUSD": [("london", "Euro — London+NY best")],
    "GBPUSD": [("london", "Pound — London+NY best")],
    "EURGBP": [("london", "Euro/Pound — London best")],
    "USDCHF": [("london", "Swiss Franc — London+NY best")],

    # NY / multi-session pairs
    "USDCAD": [("london", "CAD — London+NY best")],
    "GOLD":   [("london", "Gold — London+NY best")],
    "XAUUSD": [("london", "Gold — London+NY best")],
    "BTCUSD": [("london", "BTC — NY best, 24/7 but filter applied")],
}

# Session UTC ranges
# Sydney crosses midnight so handled separately
SESSION_RANGES = {
    "sydney": None,         # special: 22:00–07:00 UTC
    "tokyo":  (0,  9),      # 00:00–09:00 UTC
    "london": (8,  17),     # 08:00–17:00 UTC
    "ny":     (13, 22),     # 13:00–22:00 UTC
}

# Sessions that are active per pair — we check ALL valid sessions for that pair
PAIR_ACTIVE_SESSIONS = {
    "AUDUSD": ["sydney", "tokyo", "london"],
    "AUDJPY": ["sydney", "tokyo"],
    "AUDNZD": ["sydney", "tokyo"],
    "NZDUSD": ["sydney", "tokyo"],
    "USDJPY": ["tokyo",  "london"],
    "EURJPY": ["tokyo",  "london"],
    "GBPJPY": ["tokyo",  "london"],
    "EURUSD": ["london", "ny"],
    "GBPUSD": ["london", "ny"],
    "EURGBP": ["london", "ny"],
    "USDCHF": ["london", "ny"],
    "USDCAD": ["london", "ny"],
    "GOLD":   ["london", "ny"],
    "XAUUSD": ["london", "ny"],
    "BTCUSD": ["london", "ny"],
}

SESSION_LABELS = {
    "sydney": "Sydney 🇦🇺",
    "tokyo":  "Tokyo 🇯🇵",
    "london": "London 🇬🇧",
    "ny":     "New York 🇺🇸",
}


def _in_session(session: str, hour_utc: int) -> bool:
    """UTC hour ගිය session active ද check කරනවා."""
    if session == "sydney":
        # Sydney: 22:00–07:00 UTC (midnight cross)
        return hour_utc >= 22 or hour_utc < 7
    start, end = SESSION_RANGES[session]
    return start <= hour_utc < end


def get_session_status(symbol: str, dt_utc: datetime = None) -> tuple[bool, str]:
    """
    Symbol + UTC time දී pair-specific session active ද check.
    Returns: (is_valid: bool, session_label: str)
    """
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)

    hour = dt_utc.hour

    # Symbol normalize (XAUUSD → GOLD etc.)
    sym = symbol.upper().replace("XAUUSD", "GOLD")

    active_sessions = PAIR_ACTIVE_SESSIONS.get(sym, ["london", "ny"])
    active_now = [s for s in active_sessions if _in_session(s, hour)]

    if active_now:
        labels = " + ".join(SESSION_LABELS[s] for s in active_now)
        return True, labels

    # Active නෑ — next session කීයටද?
    lk_time = dt_utc + timedelta(hours=5, minutes=30)

    # First valid session find
    next_session = active_sessions[0]
    if next_session == "sydney":
        next_utc_hour = 22
    else:
        next_utc_hour = SESSION_RANGES[next_session][0]

    next_open = dt_utc.replace(hour=next_utc_hour, minute=0, second=0, microsecond=0)
    if next_open <= dt_utc:
        next_open += timedelta(days=1)

    wait = next_open - dt_utc
    wait_h = int(wait.total_seconds() // 3600)
    wait_m = int((wait.total_seconds() % 3600) // 60)

    next_label = SESSION_LABELS[next_session]
    return False, f"Off-session ⏸️  ({next_label} opens in {wait_h}h {wait_m}m)"


class ForexAnalyzer:

    def __init__(self, symbol: str, df: pd.DataFrame):
        self.symbol = symbol
        self.df     = df.copy()

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

        # ── SESSION FILTER ───────────────────────────────────────────────────
        now_utc = datetime.now(timezone.utc)
        session_ok, session_name = get_session_status(self.symbol, now_utc)

        if not session_ok:
            return {
                "symbol":       self.symbol,
                "price":        round(float(self.df["Close"].iloc[-1]), 5),
                "direction":    "NEUTRAL",
                "strength":     0,
                "buy_score":    0,
                "sell_score":   0,
                "reasons":      [f"⏸️ {session_name}"],
                "session":      session_name,
                "session_ok":   False,
                "valid_until":  None,
                "rsi":          None,
                "ema20":        None,
                "ema50":        None,
                "ema200":       None,
                "macd":         None,
                "atr":          None,
                "stop_loss":    None,
                "take_profit1": None,
                "take_profit2": None,
                "risk_reward":  None,
            }

        # ── INDICATORS ──────────────────────────────────────────────────────
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
            buy_why.append("EMA200 ✅ Uptrend")
        else:
            sell_score += 1
            sell_why.append("EMA200 ❌ Downtrend")

        # 2. EMA 20/50
        if ema20_v > ema50_v:
            buy_score += 1
            buy_why.append("EMA20>50 ✅ Bullish")
        else:
            sell_score += 1
            sell_why.append("EMA20<50 ❌ Bearish")

        # 3. RSI
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

        # 4. MACD
        if macd_v > sig_v and hist_now > hist_pre:
            buy_score += 1
            buy_why.append("MACD ✅ Bullish momentum")
        elif macd_v < sig_v and hist_now < hist_pre:
            sell_score += 1
            sell_why.append("MACD ❌ Bearish momentum")

        # 5. Bollinger Bands
        bb_range = bbu_v - bbl_v
        bb_pct   = (p - bbl_v) / bb_range if bb_range != 0 else 0.5

        if p <= bbl_v:
            buy_score += 1
            buy_why.append("BB ✅ Below lower band")
        elif p >= bbu_v:
            sell_score += 1
            sell_why.append("BB ❌ Above upper band")
        elif bb_pct < 0.30:
            buy_score += 1
            buy_why.append("BB ✅ Lower zone")
        elif bb_pct > 0.70:
            sell_score += 1
            sell_why.append("BB ❌ Upper zone")

        # 6. Momentum
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

        # ── OPTION B: RSI හෝ BB mandatory ───────────────────────────────────
        buy_rsi_bb  = any("RSI" in r or "BB" in r for r in buy_why)
        sell_rsi_bb = any("RSI" in r or "BB" in r for r in sell_why)

        # ── OPTION C: EMA200 conflict reject ────────────────────────────────
        ema200_bullish = p > ema200_v

        # ── DIRECTION ────────────────────────────────────────────────────────
        if (
            buy_score >= MIN_SCORE
            and buy_score > sell_score
            and buy_rsi_bb
            and ema200_bullish
        ):
            direction = "BUY"
            reasons   = buy_why
            strength  = round((buy_score / 6) * 100)

        elif (
            sell_score >= MIN_SCORE
            and sell_score > buy_score
            and sell_rsi_bb
            and not ema200_bullish
        ):
            direction = "SELL"
            reasons   = sell_why
            strength  = round((sell_score / 6) * 100)

        else:
            direction = "NEUTRAL"
            strength  = round((max(buy_score, sell_score) / 6) * 100)
            neutral_reasons = []

            if buy_score >= MIN_SCORE and buy_score > sell_score:
                if not buy_rsi_bb:
                    neutral_reasons.append("⚠️ RSI/BB confirmation නෑ — skip")
                if not ema200_bullish:
                    neutral_reasons.append("⚠️ EMA200 downtrend — BUY conflict")
            elif sell_score >= MIN_SCORE and sell_score > buy_score:
                if not sell_rsi_bb:
                    neutral_reasons.append("⚠️ RSI/BB confirmation නෑ — skip")
                if ema200_bullish:
                    neutral_reasons.append("⚠️ EMA200 uptrend — SELL conflict")
            else:
                neutral_reasons.append("⚖️ No clear signal")

            reasons = neutral_reasons

        # ── RISK MANAGEMENT ──────────────────────────────────────────────────
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

        # ── SIGNAL VALIDITY WINDOW ───────────────────────────────────────────
        valid_until_utc = now_utc + timedelta(minutes=SIGNAL_VALID_MINUTES)
        valid_until_lk  = valid_until_utc + timedelta(hours=5, minutes=30)
        valid_until_str = valid_until_lk.strftime("%I:%M %p") + " (LK)"

        return {
            "symbol":       self.symbol,
            "price":        p,
            "direction":    direction,
            "strength":     strength,
            "buy_score":    buy_score,
            "sell_score":   sell_score,
            "reasons":      reasons,
            "session":      session_name,
            "session_ok":   True,
            "valid_until":  valid_until_str,
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