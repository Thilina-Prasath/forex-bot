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
  - GOLD/BTCUSD → MIN_SCORE 5 (volatile pairs)
  - RSI OR BB confirmation mandatory (Option B)
  - EMA200 direction conflict rejected (Option C)
  - Session filter: Pair-specific sessions only
  - News filter: High Impact News 30min block
  - Max SL distance: Pair-specific pip limits
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
from news_filter import check_news_conflict

# ── Signal validity window (minutes) ────────────────────────────────────────
SIGNAL_VALID_MINUTES = 3

# ── Volatile pairs — higher MIN_SCORE required ───────────────────────────────
# GOLD, BTCUSD: ATR ලොකු, false signals ගොඩාක් — 5/6 mandatory
VOLATILE_PAIRS     = {"GOLD", "XAUUSD", "BTCUSD"}
VOLATILE_MIN_SCORE = 5

# ── Position size warnings ───────────────────────────────────────────────────
POSITION_SIZE_WARNINGS = {
    "GOLD":   "⚠️ GOLD — Max 0.01 lot use කරන්න!",
    "XAUUSD": "⚠️ GOLD — Max 0.01 lot use කරන්න!",
    "BTCUSD": "⚠️ BTC  — Max 0.001 lot use කරන්න!",
}

# ── Session config ───────────────────────────────────────────────────────────
SESSION_RANGES = {
    "sydney": None,
    "tokyo":  (0,  9),
    "london": (8,  17),
    "ny":     (13, 22),
}

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
    if session == "sydney":
        return hour_utc >= 22 or hour_utc < 7
    start, end = SESSION_RANGES[session]
    return start <= hour_utc < end


def get_session_status(symbol: str, dt_utc: datetime = None) -> tuple[bool, str]:
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)
    hour = dt_utc.hour
    sym  = symbol.upper().replace("XAUUSD", "GOLD")

    active_sessions = PAIR_ACTIVE_SESSIONS.get(sym, ["london", "ny"])
    active_now = [s for s in active_sessions if _in_session(s, hour)]

    if active_now:
        labels = " + ".join(SESSION_LABELS[s] for s in active_now)
        return True, labels

    next_session  = active_sessions[0]
    next_utc_hour = 22 if next_session == "sydney" else SESSION_RANGES[next_session][0]
    next_open     = dt_utc.replace(hour=next_utc_hour, minute=0, second=0, microsecond=0)
    if next_open <= dt_utc:
        next_open += timedelta(days=1)

    wait   = next_open - dt_utc
    wait_h = int(wait.total_seconds() // 3600)
    wait_m = int((wait.total_seconds() % 3600) // 60)
    return False, f"Off-session ⏸️  ({SESSION_LABELS[next_session]} opens in {wait_h}h {wait_m}m)"


def _empty_result(symbol: str, price: float, reason: str,
                  session_ok: bool, session_name: str,
                  news_blocked: bool = False) -> dict:
    """Session/News block වූ විට return කරන standard dict."""
    return {
        "symbol":        symbol,
        "price":         price,
        "direction":     "NEUTRAL",
        "strength":      0,
        "buy_score":     0,
        "sell_score":    0,
        "reasons":       [reason],
        "session":       session_name,
        "session_ok":    session_ok,
        "news_blocked":  news_blocked,
        "valid_until":   None,
        "pos_size_warn": None,
        "rsi":           None,
        "ema20":         None,
        "ema50":         None,
        "ema200":        None,
        "macd":          None,
        "atr":           None,
        "stop_loss":     None,
        "take_profit1":  None,
        "take_profit2":  None,
        "risk_reward":   None,
    }


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

    def _get_max_sl_dist(self) -> float:
        """Pair-specific maximum SL distance (price units)."""
        sym = self.symbol.upper()
        if "JPY"  in sym:                  return 1.00
        if "GOLD" in sym or "XAU" in sym:  return 10.0
        if "BTC"  in sym:                  return 400.0
        return 0.0100

    def generate(self) -> dict:
        now_utc = datetime.now(timezone.utc)
        price   = round(float(self.df["Close"].iloc[-1]), 5)
        sym     = self.symbol.upper()

        # ── 1. SESSION FILTER ────────────────────────────────────────────────
        session_ok, session_name = get_session_status(self.symbol, now_utc)
        if not session_ok:
            return _empty_result(
                self.symbol, price,
                f"⏸️ {session_name}",
                session_ok=False, session_name=session_name,
            )

        # ── 2. NEWS FILTER ───────────────────────────────────────────────────
        has_news, news_title = check_news_conflict(self.symbol, buffer_minutes=30)
        if has_news:
            return _empty_result(
                self.symbol, price,
                f"🚨 News blocked: {news_title}",
                session_ok=True, session_name=session_name,
                news_blocked=True,
            )

        # ── 3. PAIR-SPECIFIC MIN_SCORE ───────────────────────────────────────
        min_score = VOLATILE_MIN_SCORE if sym in VOLATILE_PAIRS else MIN_SCORE

        # ── INDICATORS ───────────────────────────────────────────────────────
        ema20  = self._ema(EMA_FAST)
        ema50  = self._ema(EMA_SLOW)
        ema200 = self._ema(EMA_TREND)
        rsi    = self._rsi()
        macd_l, macd_s, macd_h = self._macd()
        bb_up, _, bb_lo = self._bollinger()
        atr    = self._atr()

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
            buy_score += 1;  buy_why.append("EMA200 ✅ Uptrend")
        else:
            sell_score += 1; sell_why.append("EMA200 ❌ Downtrend")

        # 2. EMA 20/50
        if ema20_v > ema50_v:
            buy_score += 1;  buy_why.append("EMA20>50 ✅ Bullish")
        else:
            sell_score += 1; sell_why.append("EMA20<50 ❌ Bearish")

        # 3. RSI
        rsi_rising  = rsi_now > rsi_prev > rsi_prev2
        rsi_falling = rsi_now < rsi_prev < rsi_prev2

        if rsi_now < 40:
            buy_score += 1;  buy_why.append(f"RSI {rsi_now} ✅ Oversold")
        elif rsi_now > 60:
            sell_score += 1; sell_why.append(f"RSI {rsi_now} ❌ Overbought")
        elif 40 <= rsi_now <= 47 and rsi_rising:
            buy_score += 1;  buy_why.append(f"RSI {rsi_now} ✅ Rising from low")
        elif 53 <= rsi_now <= 60 and rsi_falling:
            sell_score += 1; sell_why.append(f"RSI {rsi_now} ❌ Falling from high")

        # 4. MACD
        if macd_v > sig_v and hist_now > hist_pre:
            buy_score += 1;  buy_why.append("MACD ✅ Bullish momentum")
        elif macd_v < sig_v and hist_now < hist_pre:
            sell_score += 1; sell_why.append("MACD ❌ Bearish momentum")

        # 5. Bollinger Bands
        bb_range = bbu_v - bbl_v
        bb_pct   = (p - bbl_v) / bb_range if bb_range != 0 else 0.5

        if p <= bbl_v:
            buy_score += 1;  buy_why.append("BB ✅ Below lower band")
        elif p >= bbu_v:
            sell_score += 1; sell_why.append("BB ❌ Above upper band")
        elif bb_pct < 0.30:
            buy_score += 1;  buy_why.append("BB ✅ Lower zone")
        elif bb_pct > 0.70:
            sell_score += 1; sell_why.append("BB ❌ Upper zone")

        # 6. Momentum
        if p > p1 > p2 > p3:
            buy_score += 1;  buy_why.append("Momentum ✅ 4 bull candles")
        elif p > p1 > p2:
            buy_score += 1;  buy_why.append("Momentum ✅ 3 bull candles")
        elif p < p1 < p2 < p3:
            sell_score += 1; sell_why.append("Momentum ❌ 4 bear candles")
        elif p < p1 < p2:
            sell_score += 1; sell_why.append("Momentum ❌ 3 bear candles")

        # ── Option B: RSI/BB mandatory ───────────────────────────────────────
        buy_rsi_bb  = any("RSI" in r or "BB" in r for r in buy_why)
        sell_rsi_bb = any("RSI" in r or "BB" in r for r in sell_why)

        # ── Option C: EMA200 conflict reject ─────────────────────────────────
        ema200_bullish = p > ema200_v

        # ── DIRECTION ────────────────────────────────────────────────────────
        if (buy_score >= min_score and buy_score > sell_score
                and buy_rsi_bb and ema200_bullish):
            direction = "BUY"
            reasons   = buy_why
            strength  = round((buy_score / 6) * 100)

        elif (sell_score >= min_score and sell_score > buy_score
                and sell_rsi_bb and not ema200_bullish):
            direction = "SELL"
            reasons   = sell_why
            strength  = round((sell_score / 6) * 100)

        else:
            direction = "NEUTRAL"
            strength  = round((max(buy_score, sell_score) / 6) * 100)
            neutral_reasons = []

            if buy_score >= min_score and buy_score > sell_score:
                if not buy_rsi_bb:
                    neutral_reasons.append("⚠️ RSI/BB confirmation නෑ — skip")
                if not ema200_bullish:
                    neutral_reasons.append("⚠️ EMA200 downtrend — BUY conflict")
            elif sell_score >= min_score and sell_score > buy_score:
                if not sell_rsi_bb:
                    neutral_reasons.append("⚠️ RSI/BB confirmation නෑ — skip")
                if ema200_bullish:
                    neutral_reasons.append("⚠️ EMA200 uptrend — SELL conflict")
            elif sym in VOLATILE_PAIRS and max(buy_score, sell_score) == 4:
                neutral_reasons.append(f"⚠️ {sym} 4/6 — volatile pair, 5/6 required")
            else:
                neutral_reasons.append("⚖️ No clear signal")

            reasons = neutral_reasons

        # ── RISK MANAGEMENT ──────────────────────────────────────────────────
        sl = tp1 = tp2 = rr = None
        if direction in ("BUY", "SELL"):
            sl_dist   = atr_v * ATR_SL_MULTI
            actual_sl = min(sl_dist, self._get_max_sl_dist())
            ratio     = ATR_TP_MULTI / ATR_SL_MULTI
            actual_tp = actual_sl * ratio

            if direction == "BUY":
                sl  = round(p - actual_sl,       5)
                tp1 = round(p + actual_tp * 0.6, 5)
                tp2 = round(p + actual_tp,       5)
            else:
                sl  = round(p + actual_sl,       5)
                tp1 = round(p - actual_tp * 0.6, 5)
                tp2 = round(p - actual_tp,       5)
            rr = round(ratio, 1)

        # ── SIGNAL VALIDITY WINDOW ───────────────────────────────────────────
        valid_until_lk  = (now_utc + timedelta(minutes=SIGNAL_VALID_MINUTES)
                           + timedelta(hours=5, minutes=30))
        valid_until_str = valid_until_lk.strftime("%I:%M %p") + " (LK)"

        return {
            "symbol":        self.symbol,
            "price":         p,
            "direction":     direction,
            "strength":      strength,
            "buy_score":     buy_score,
            "sell_score":    sell_score,
            "reasons":       reasons,
            "session":       session_name,
            "session_ok":    True,
            "news_blocked":  False,
            "valid_until":   valid_until_str,
            "pos_size_warn": POSITION_SIZE_WARNINGS.get(sym),
            "rsi":           rsi_now,
            "ema20":         ema20_v,
            "ema50":         ema50_v,
            "ema200":        ema200_v,
            "macd":          macd_v,
            "atr":           atr_v,
            "stop_loss":     sl,
            "take_profit1":  tp1,
            "take_profit2":  tp2,
            "risk_reward":   rr,
        }