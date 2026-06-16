"""
analyzer.py — Indicators (6 points) + News Momentum Logic
Fixed:  ema200_bullish undefined bug
New:    10-second news price-movement watch
        News momentum without ADX>=30 requirement
        Cleaner signal flow
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

SIGNAL_VALID_MINUTES = 5
VOLATILE_PAIRS       = {"GOLD", "XAUUSD", "BTCUSD"}
VOLATILE_MIN_SCORE   = 5

POSITION_SIZE_WARNINGS = {
    "GOLD":   "⚠️ GOLD — Max 0.01 Troy Oz only!",
    "XAUUSD": "⚠️ GOLD — Max 0.01 Troy Oz only!",
    "BTCUSD": "⚠️ BTC  — Max 0.001 lot use කරන්න!",
}

SESSION_RANGES = {"sydney": None, "tokyo": (0, 9), "london": (8, 17), "ny": (13, 22)}

PAIR_ACTIVE_SESSIONS = {
    "AUDUSD": ["sydney", "tokyo", "london"], "AUDJPY": ["sydney", "tokyo"],
    "AUDNZD": ["sydney", "tokyo"], "NZDUSD": ["sydney", "tokyo"],
    "USDJPY": ["tokyo",  "london"], "EURJPY": ["tokyo",  "london"],
    "GBPJPY": ["tokyo",  "london"], "EURUSD": ["london", "ny"],
    "GBPUSD": ["london", "ny"], "EURGBP": ["london", "ny"],
    "USDCHF": ["london", "ny"], "USDCAD": ["london", "ny"],
    "GOLD":   ["london", "ny"], "XAUUSD": ["london", "ny"],
    "BTCUSD": ["london", "ny"],
}

SESSION_LABELS = {
    "sydney": "Sydney 🇦🇺", "tokyo": "Tokyo 🇯🇵",
    "london": "London 🇬🇧",  "ny":    "New York 🇺🇸",
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
        return True, " + ".join(SESSION_LABELS[s] for s in active_now)

    next_session  = active_sessions[0]
    next_utc_hour = 22 if next_session == "sydney" else SESSION_RANGES[next_session][0]
    next_open     = dt_utc.replace(hour=next_utc_hour, minute=0, second=0, microsecond=0)
    if next_open <= dt_utc:
        next_open += timedelta(days=1)

    wait   = next_open - dt_utc
    wait_h = int(wait.total_seconds() // 3600)
    wait_m = int((wait.total_seconds() % 3600) // 60)
    label  = SESSION_LABELS.get(next_session, next_session)
    return False, f"Off-session ⏸️  ({label} opens in {wait_h}h {wait_m}m)"


def _empty_result(symbol, price, reason, session_ok, session_name, news_blocked=False):
    return {
        "symbol": symbol, "price": price, "direction": "NEUTRAL",
        "strength": 0, "buy_score": 0, "sell_score": 0,
        "reasons": [reason], "session": session_name,
        "session_ok": session_ok, "news_blocked": news_blocked,
        "valid_until": None, "pos_size_warn": None,
        "rsi": None, "ema20": None, "ema50": None, "ema200": None,
        "macd": None, "atr": None, "adx": None,
        "stop_loss": None, "take_profit1": None, "take_profit2": None,
        "risk_reward": None, "news_momentum": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  NEWS MOMENTUM WATCHER
#  News break වෙලා price direction දිගටම යනවාද කියලා
#  candle history ඇතුළෙන් "10-second equivalent" ලෙස last 3 candles check කරයි
# ─────────────────────────────────────────────────────────────────────────────
def _detect_news_direction(closes: list[float], rsi_now: float, ema20: float) -> str:
    """
    News break වෙලා price direction confirm කරයි.

    Logic:
      - Last 3 closes continuously rising  AND price > EMA20 AND RSI > 45  → BUY
      - Last 3 closes continuously falling AND price < EMA20 AND RSI < 55  → SELL
      - Otherwise → NEUTRAL (momentum clear නෑ)

    closes: [oldest ... newest] — අවම 4 values ඕනේ
    """
    if len(closes) < 4:
        return "NEUTRAL"

    p, p1, p2, p3 = closes[-1], closes[-2], closes[-3], closes[-4]

    rising  = p > p1 and p1 > p2
    falling = p < p1 and p1 < p2

    if rising and p > ema20 and rsi_now > 45:
        return "BUY"
    if falling and p < ema20 and rsi_now < 55:
        return "SELL"
    return "NEUTRAL"


# ─────────────────────────────────────────────────────────────────────────────
class ForexAnalyzer:
    def __init__(self, symbol: str, df: pd.DataFrame):
        self.symbol = symbol
        self.df     = df.copy()

    # ── Indicators ───────────────────────────────────────────────────────────
    def _ema(self, period):
        return self.df["Close"].ewm(span=period, adjust=False).mean()

    def _rsi(self):
        delta = self.df["Close"].diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        rs    = (
            gain.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
            / loss.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean().replace(0, np.nan)
        )
        return 100 - (100 / (1 + rs))

    def _macd(self):
        line = self._ema(12) - self._ema(26)
        sig  = line.ewm(span=9, adjust=False).mean()
        return line, sig, line - sig

    def _bollinger(self, period=20, std=2.0):
        sma = self.df["Close"].rolling(window=period).mean()
        sd  = self.df["Close"].rolling(window=period).std()
        return sma + sd * std, sma, sma - sd * std

    def _atr(self):
        h, l, c = self.df["High"], self.df["Low"], self.df["Close"]
        tr = pd.concat(
            [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
        ).max(axis=1)
        return tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    def _adx(self, period: int = 14) -> float:
        h, l, c = self.df["High"], self.df["Low"], self.df["Close"]
        tr   = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        up   = h.diff()
        down = -l.diff()
        pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=self.df.index)
        mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=self.df.index)
        tr14, pdm14, mdm14 = (
            tr.rolling(period).sum(),
            pdm.rolling(period).sum(),
            mdm.rolling(period).sum(),
        )
        pdi = 100 * pdm14 / tr14.replace(0, np.nan)
        mdi = 100 * mdm14 / tr14.replace(0, np.nan)
        dx  = 100 * abs(pdi - mdi) / (pdi + mdi).replace(0, np.nan)
        return round(float(dx.rolling(period).mean().iloc[-1]), 2)

    def _get_min_sl_dist(self) -> float:
        sym = self.symbol.upper()
        if "JPY"  in sym: return 0.10
        if "GOLD" in sym or "XAU" in sym: return 5.0
        if "BTC"  in sym: return 100.0
        return 0.0010

    def _get_max_sl_dist(self) -> float:
        sym = self.symbol.upper()
        if "JPY"  in sym: return 1.00
        if "GOLD" in sym or "XAU" in sym: return 20.0
        if "BTC"  in sym: return 400.0
        return 0.0100

    # ── Main generate ────────────────────────────────────────────────────────
    def generate(self) -> dict:
        now_utc = datetime.now(timezone.utc)
        price   = round(float(self.df["Close"].iloc[-1]), 5)
        sym     = self.symbol.upper()

        # 1. Session check
        session_ok, session_name = get_session_status(self.symbol, now_utc)
        if not session_ok:
            return _empty_result(self.symbol, price,
                                 f"⏸️ {session_name}", False, session_name)

        # 2. News check
        news_status, news_title = check_news_conflict(self.symbol)
        is_news_momentum = (news_status == "NEWS_MOMENTUM")

        if news_status == "BLOCKED":
            return _empty_result(self.symbol, price,
                                 f"🚨 News Blocked: {news_title}",
                                 True, session_name, True)

        # 3. Indicators
        try:
            adx_val = self._adx()
        except Exception:
            adx_val = 30.0

        ema20  = self._ema(EMA_FAST)
        ema50  = self._ema(EMA_SLOW)
        ema200 = self._ema(EMA_TREND)
        rsi    = self._rsi()
        macd_l, macd_s, macd_h = self._macd()
        bb_up, _, bb_lo = self._bollinger()
        atr    = self._atr()

        c = self.df["Close"]
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

        # ── FIX: ema200_bullish define කරනවා ────────────────────────────────
        ema200_bullish = p > ema200_v

        # ── Macro trend (last 20 candles) ────────────────────────────────────
        p20          = round(float(c.iloc[-21]), 5) if len(c) > 21 else p
        macro_bullish = p > p20
        macro_bearish = p < p20

        # ── ADX ranging filter (normal signals only) ─────────────────────────
        if not is_news_momentum and adx_val < 20:
            return _empty_result(self.symbol, price,
                                 f"⚠️ ADX {adx_val} < 20 — ranging market",
                                 True, session_name)

        # ════════════════════════════════════════════════════════════════════
        #  NEWS MOMENTUM PATH
        #  News break වෙලා price direction confirm කර signal දෙයි.
        #  ADX >= 30 requirement නෑ — news just broke නිසා ADX lag කරයි.
        # ════════════════════════════════════════════════════════════════════
        if is_news_momentum:
            closes_list = [round(float(c.iloc[i]), 5) for i in range(-5, 0)]
            news_dir    = _detect_news_direction(closes_list, rsi_now, ema20_v)

            if news_dir != "NEUTRAL":
                # SL/TP calculations
                sl_dist  = max(min(atr_v * 2.5, self._get_max_sl_dist()), self._get_min_sl_dist())
                tp_dist  = sl_dist * (ATR_TP_MULTI / ATR_SL_MULTI)
                rr_ratio = round(ATR_TP_MULTI / ATR_SL_MULTI, 1)

                if news_dir == "BUY":
                    sl  = round(p - sl_dist, 5)
                    tp1 = round(p + tp_dist * 0.6, 5)
                    tp2 = round(p + tp_dist,       5)
                else:
                    sl  = round(p + sl_dist, 5)
                    tp1 = round(p - tp_dist * 0.6, 5)
                    tp2 = round(p - tp_dist,       5)

                valid_until = (
                    now_utc + timedelta(minutes=SIGNAL_VALID_MINUTES)
                    + timedelta(hours=5, minutes=30)
                ).strftime("%I:%M %p") + " (LK)"

                return {
                    "symbol": self.symbol, "price": p,
                    "direction": news_dir, "strength": 90,
                    "buy_score":  6 if news_dir == "BUY"  else 0,
                    "sell_score": 6 if news_dir == "SELL" else 0,
                    "reasons": [
                        f"📰 News Momentum: {news_title}",
                        f"📈 Price {'rising' if news_dir == 'BUY' else 'falling'} after news",
                        f"RSI {rsi_now} {'> 45 ✅' if news_dir == 'BUY' else '< 55 ✅'}",
                        f"Price {'>' if news_dir == 'BUY' else '<'} EMA20 ✅",
                        f"ADX {adx_val} (momentum building)",
                    ],
                    "session": session_name, "session_ok": True,
                    "news_blocked": False, "news_momentum": True,
                    "valid_until": valid_until,
                    "pos_size_warn": POSITION_SIZE_WARNINGS.get(sym),
                    "rsi": rsi_now, "ema20": ema20_v, "ema50": ema50_v, "ema200": ema200_v,
                    "macd": macd_v, "atr": atr_v, "adx": adx_val,
                    "stop_loss": sl, "take_profit1": tp1, "take_profit2": tp2,
                    "risk_reward": rr_ratio,
                }
            else:
                # News window open ඒත් direction clear නෑ — NEUTRAL return
                return _empty_result(
                    self.symbol, price,
                    f"📰 News window open ({news_title}) — direction unclear",
                    True, session_name,
                )

        # ════════════════════════════════════════════════════════════════════
        #  STANDARD TECHNICAL PATH
        # ════════════════════════════════════════════════════════════════════
        buy_score, sell_score = 0, 0
        buy_why,   sell_why   = [], []
        min_score = VOLATILE_MIN_SCORE if sym in VOLATILE_PAIRS else MIN_SCORE

        # 1. EMA200 trend
        if p > ema200_v:
            buy_score  += 1; buy_why.append("EMA200 ✅ Uptrend")
        else:
            sell_score += 1; sell_why.append("EMA200 ❌ Downtrend")

        # 2. EMA20 vs EMA50
        if ema20_v > ema50_v:
            buy_score  += 1; buy_why.append("EMA20>50 ✅ Bullish")
        else:
            sell_score += 1; sell_why.append("EMA20<50 ❌ Bearish")

        # 3. RSI
        if rsi_now < 40:
            buy_score  += 1; buy_why.append(f"RSI {rsi_now} ✅ Oversold")
        elif rsi_now > 60:
            sell_score += 1; sell_why.append(f"RSI {rsi_now} ❌ Overbought")
        elif 40 <= rsi_now <= 50 and (rsi_now > rsi_prev > rsi_prev2):
            buy_score  += 1; buy_why.append(f"RSI {rsi_now} ✅ Rising from low")
        elif 50 <= rsi_now <= 60 and (rsi_now < rsi_prev < rsi_prev2):
            sell_score += 1; sell_why.append(f"RSI {rsi_now} ❌ Falling from high")

        # 4. MACD
        if   macd_v > sig_v and hist_now > hist_pre and macd_v > 0:
            buy_score  += 1; buy_why.append("MACD ✅ Bullish + above zero")
        elif macd_v > sig_v and hist_now > hist_pre:
            buy_score  += 1; buy_why.append("MACD ✅ Bullish momentum")
        elif macd_v < sig_v and hist_now < hist_pre and macd_v < 0:
            sell_score += 1; sell_why.append("MACD ❌ Bearish + below zero")
        elif macd_v < sig_v and hist_now < hist_pre:
            sell_score += 1; sell_why.append("MACD ❌ Bearish momentum")

        # 5. Bollinger Bands
        bb_range = bbu_v - bbl_v
        bb_pct   = (p - bbl_v) / bb_range if bb_range != 0 else 0.5
        if   p <= bbl_v:    buy_score  += 1; buy_why.append("BB ✅ Below lower band")
        elif p >= bbu_v:    sell_score += 1; sell_why.append("BB ❌ Above upper band")
        elif bb_pct < 0.30: buy_score  += 1; buy_why.append("BB ✅ Lower zone")
        elif bb_pct > 0.70: sell_score += 1; sell_why.append("BB ❌ Upper zone")

        # 6. Price momentum (candles)
        if   p > p1 > p2 > p3: buy_score  += 1; buy_why.append("Momentum ✅ 4 bull candles")
        elif p > p1 > p2:       buy_score  += 1; buy_why.append("Momentum ✅ 3 bull candles")
        elif p < p1 < p2 < p3:  sell_score += 1; sell_why.append("Momentum ❌ 4 bear candles")
        elif p < p1 < p2:        sell_score += 1; sell_why.append("Momentum ❌ 3 bear candles")

        # ── Confirmation flags ───────────────────────────────────────────────
        buy_rsi_bb  = any("RSI" in r or "BB" in r for r in buy_why)
        sell_rsi_bb = any("RSI" in r or "BB" in r for r in sell_why)

        # ── Final decision ───────────────────────────────────────────────────
        if buy_score >= min_score and buy_score > sell_score and buy_rsi_bb and ema200_bullish and macro_bullish:
            direction = "BUY";  reasons = buy_why;  strength = round((buy_score  / 6) * 100)
        elif sell_score >= min_score and sell_score > buy_score and sell_rsi_bb and not ema200_bullish and macro_bearish:
            direction = "SELL"; reasons = sell_why; strength = round((sell_score / 6) * 100)
        else:
            direction = "NEUTRAL"
            strength  = round((max(buy_score, sell_score) / 6) * 100)
            reasons   = []

            if buy_score >= min_score and buy_score > sell_score:
                if not buy_rsi_bb:      reasons.append("⚠️ RSI/BB confirmation නෑ — skip")
                elif not ema200_bullish: reasons.append("⚠️ EMA200 downtrend — skip")
                elif not macro_bullish:  reasons.append("⚠️ Macro downtrend (20 candles) — skip")
            elif sell_score >= min_score and sell_score > buy_score:
                if not sell_rsi_bb:    reasons.append("⚠️ RSI/BB confirmation නෑ — skip")
                elif ema200_bullish:    reasons.append("⚠️ EMA200 uptrend — skip")
                elif not macro_bearish: reasons.append("⚠️ Macro uptrend (20 candles) — skip")
            elif sym in VOLATILE_PAIRS and max(buy_score, sell_score) == 4:
                reasons.append(f"⚠️ {sym} 4/6 — volatile pair, 5/6 required")
            else:
                reasons.append("⚖️ No clear signal")

        # ── Risk management ──────────────────────────────────────────────────
        sl = tp1 = tp2 = rr = None
        if direction in ("BUY", "SELL"):
            sl_dist   = max(min(atr_v * ATR_SL_MULTI, self._get_max_sl_dist()), self._get_min_sl_dist())
            tp_dist   = sl_dist * (ATR_TP_MULTI / ATR_SL_MULTI)
            rr        = round(ATR_TP_MULTI / ATR_SL_MULTI, 1)

            if direction == "BUY":
                sl  = round(p - sl_dist, 5)
                tp1 = round(p + tp_dist * 0.6, 5)
                tp2 = round(p + tp_dist, 5)
            else:
                sl  = round(p + sl_dist, 5)
                tp1 = round(p - tp_dist * 0.6, 5)
                tp2 = round(p - tp_dist, 5)

        valid_until_str = (
            now_utc + timedelta(minutes=SIGNAL_VALID_MINUTES)
            + timedelta(hours=5, minutes=30)
        ).strftime("%I:%M %p") + " (LK)"

        return {
            "symbol": self.symbol, "price": p,
            "direction": direction, "strength": strength,
            "buy_score": buy_score, "sell_score": sell_score,
            "reasons": reasons, "session": session_name,
            "session_ok": True, "news_blocked": False, "news_momentum": False,
            "valid_until": valid_until_str,
            "pos_size_warn": POSITION_SIZE_WARNINGS.get(sym),
            "rsi": rsi_now, "ema20": ema20_v, "ema50": ema50_v, "ema200": ema200_v,
            "macd": macd_v, "atr": atr_v, "adx": adx_val,
            "stop_loss": sl, "take_profit1": tp1, "take_profit2": tp2,
            "risk_reward": rr,
        }