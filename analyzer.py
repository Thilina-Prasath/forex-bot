"""
Indicators (6 points max) & News Momentum Logic
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
VOLATILE_PAIRS     = {"GOLD", "XAUUSD", "BTCUSD"}
VOLATILE_MIN_SCORE = 5

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

SESSION_LABELS = {"sydney": "Sydney 🇦🇺", "tokyo": "Tokyo 🇯🇵", "london": "London 🇬🇧", "ny": "New York 🇺🇸"}

def _in_session(session: str, hour_utc: int) -> bool:
    if session == "sydney": return hour_utc >= 22 or hour_utc < 7
    start, end = SESSION_RANGES[session]
    return start <= hour_utc < end

def get_session_status(symbol: str, dt_utc: datetime = None) -> tuple[bool, str]:
    if dt_utc is None: dt_utc = datetime.now(timezone.utc)
    hour = dt_utc.hour
    sym  = symbol.upper().replace("XAUUSD", "GOLD")
    active_sessions = PAIR_ACTIVE_SESSIONS.get(sym, ["london", "ny"])
    active_now = [s for s in active_sessions if _in_session(s, hour)]

    if active_now: return True, " + ".join(SESSION_LABELS[s] for s in active_now)
    next_session  = active_sessions[0]
    next_utc_hour = 22 if next_session == "sydney" else SESSION_RANGES[next_session][0]
    next_open     = dt_utc.replace(hour=next_utc_hour, minute=0, second=0, microsecond=0)
    if next_open <= dt_utc: next_open += timedelta(days=1)

    wait = next_open - dt_utc
    wait_h = int(wait.total_seconds() // 3600)
    wait_m = int((wait.total_seconds() % 3600) // 60)
    return False, f"Off-session ⏸️  ({wait_h}h {wait_m}m)"

def _empty_result(symbol, price, reason, session_ok, session_name, news_blocked=False):
    return {
        "symbol": symbol, "price": price, "direction": "NEUTRAL", "strength": 0, "buy_score": 0, "sell_score": 0,
        "reasons": [reason], "session": session_name, "session_ok": session_ok, "news_blocked": news_blocked,
        "valid_until": None, "pos_size_warn": None, "rsi": None, "ema20": None, "ema50": None, "ema200": None,
        "macd": None, "atr": None, "stop_loss": None, "take_profit1": None, "take_profit2": None, "risk_reward": None,
    }

class ForexAnalyzer:
    def __init__(self, symbol: str, df: pd.DataFrame):
        self.symbol = symbol
        self.df     = df.copy()

    def _ema(self, period): return self.df["Close"].ewm(span=period, adjust=False).mean()
    
    def _rsi(self):
        delta = self.df["Close"].diff()
        gain, loss  = delta.clip(lower=0), -delta.clip(upper=0)
        rs = gain.ewm(com=RSI_PERIOD-1, min_periods=RSI_PERIOD).mean() / loss.ewm(com=RSI_PERIOD-1, min_periods=RSI_PERIOD).mean().replace(0, np.nan)
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
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        return tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    def _adx(self, period: int = 14) -> float:
        h, l, c = self.df["High"], self.df["Low"], self.df["Close"]
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        up, down = h.diff(), -l.diff()
        pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=self.df.index)
        mdm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=self.df.index)
        tr14, pdm14, mdm14 = tr.rolling(period).sum(), pdm.rolling(period).sum(), mdm.rolling(period).sum()
        pdi, mdi = 100 * pdm14 / tr14.replace(0, np.nan), 100 * mdm14 / tr14.replace(0, np.nan)
        dx = 100 * abs(pdi - mdi) / (pdi + mdi).replace(0, np.nan)
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

    def generate(self) -> dict:
        now_utc = datetime.now(timezone.utc)
        price   = round(float(self.df["Close"].iloc[-1]), 5)
        sym     = self.symbol.upper()

        session_ok, session_name = get_session_status(self.symbol, now_utc)
        if not session_ok:
            return _empty_result(self.symbol, price, f"⏸️ {session_name}", False, session_name)

        news_status, news_title = check_news_conflict(self.symbol)
        is_news_momentum = False

        if news_status == "BLOCKED":
            return _empty_result(self.symbol, price, f"🚨 News Blocked: {news_title}", True, session_name, True)
        elif news_status == "NEWS_MOMENTUM":
            is_news_momentum = True

        try: adx_val = self._adx()
        except Exception: adx_val = 30.0

        if not is_news_momentum and adx_val < 20:
            return _empty_result(self.symbol, price, f"⚠️ ADX {adx_val} < 20 — ranging market", True, session_name)

        ema20  = self._ema(EMA_FAST)
        ema50  = self._ema(EMA_SLOW)
        ema200 = self._ema(EMA_TREND)
        rsi    = self._rsi()
        macd_l, macd_s, macd_h = self._macd()
        bb_up, _, bb_lo = self._bollinger()
        atr    = self._atr()

        c = self.df["Close"]
        p, p1, p2, p3 = round(float(c.iloc[-1]), 5), round(float(c.iloc[-2]), 5), round(float(c.iloc[-3]), 5), round(float(c.iloc[-4]), 5)
        rsi_now, rsi_prev, rsi_prev2 = round(float(rsi.iloc[-1]), 2), round(float(rsi.iloc[-2]), 2), round(float(rsi.iloc[-3]), 2)
        ema20_v, ema50_v, ema200_v = round(float(ema20.iloc[-1]), 5), round(float(ema50.iloc[-1]), 5), round(float(ema200.iloc[-1]), 5)
        macd_v, sig_v, hist_now, hist_pre = round(float(macd_l.iloc[-1]), 6), round(float(macd_s.iloc[-1]), 6), round(float(macd_h.iloc[-1]), 6), round(float(macd_h.iloc[-2]), 6)
        bbu_v, bbl_v, atr_v = round(float(bb_up.iloc[-1]), 5), round(float(bb_lo.iloc[-1]), 5), round(float(atr.iloc[-1]), 5)

        # ── NEWS MOMENTUM LOGIC (Breakout Riding) ────────────────────────────
        news_momentum_buy = False
        news_momentum_sell = False

        if is_news_momentum and adx_val >= 30:
            # ADX 30 ට වැඩියි කියන්නේ නිව්ස් එක නිසා මාකට් එක වේගයෙන් යනවා.
            if p > ema20_v and p > p1 and rsi_now > 50:
                news_momentum_buy = True
            elif p < ema20_v and p < p1 and rsi_now < 50:
                news_momentum_sell = True

        # ── STANDARD LOGIC ───────────────────────────────────────────────────
        buy_score, sell_score, buy_why, sell_why = 0, 0, [], []
        min_score = VOLATILE_MIN_SCORE if sym in VOLATILE_PAIRS else MIN_SCORE

        if p > ema200_v: buy_score += 1; buy_why.append("EMA200 ✅ Uptrend")
        else: sell_score += 1; sell_why.append("EMA200 ❌ Downtrend")
        if ema20_v > ema50_v: buy_score += 1; buy_why.append("EMA20>50 ✅ Bullish")
        else: sell_score += 1; sell_why.append("EMA20<50 ❌ Bearish")

        if rsi_now < 40: buy_score += 1; buy_why.append(f"RSI {rsi_now} ✅ Oversold")
        elif rsi_now > 60: sell_score += 1; sell_why.append(f"RSI {rsi_now} ❌ Overbought")
        elif 40 <= rsi_now <= 50 and (rsi_now > rsi_prev > rsi_prev2): buy_score += 1; buy_why.append(f"RSI {rsi_now} ✅ Rising from low")
        elif 50 <= rsi_now <= 60 and (rsi_now < rsi_prev < rsi_prev2): sell_score += 1; sell_why.append(f"RSI {rsi_now} ❌ Falling from high")

        if macd_v > sig_v and hist_now > hist_pre and macd_v > 0: buy_score += 1; buy_why.append("MACD ✅ Bullish + above zero")
        elif macd_v > sig_v and hist_now > hist_pre: buy_score += 1; buy_why.append("MACD ✅ Bullish momentum")
        elif macd_v < sig_v and hist_now < hist_pre and macd_v < 0: sell_score += 1; sell_why.append("MACD ❌ Bearish + below zero")
        elif macd_v < sig_v and hist_now < hist_pre: sell_score += 1; sell_why.append("MACD ❌ Bearish momentum")

        bb_range = bbu_v - bbl_v
        bb_pct = (p - bbl_v) / bb_range if bb_range != 0 else 0.5
        if p <= bbl_v: buy_score += 1; buy_why.append("BB ✅ Below lower band")
        elif p >= bbu_v: sell_score += 1; sell_why.append("BB ❌ Above upper band")
        elif bb_pct < 0.30: buy_score += 1; buy_why.append("BB ✅ Lower zone")
        elif bb_pct > 0.70: sell_score += 1; sell_why.append("BB ❌ Upper zone")

        if p > p1 > p2 > p3: buy_score += 1; buy_why.append("Momentum ✅ 4 bull candles")
        elif p > p1 > p2: buy_score += 1; buy_why.append("Momentum ✅ 3 bull candles")
        elif p < p1 < p2 < p3: sell_score += 1; sell_why.append("Momentum ❌ 4 bear candles")
        elif p < p1 < p2: sell_score += 1; sell_why.append("Momentum ❌ 3 bear candles")

        p20 = round(float(self.df["Close"].iloc[-21]), 5) if len(self.df) > 21 else p
        macro_bullish, macro_bearish = p > p20, p < p20
        buy_rsi_bb = any("RSI" in r or "BB" in r for r in buy_why)
        sell_rsi_bb = any("RSI" in r or "BB" in r for r in sell_why)

        # ── FINAL DECISION ───────────────────────────────────────────────────
        if news_momentum_buy:
            direction, reasons, strength = "BUY", [f"🔥 News Breakout ({news_title})", f"ADX {adx_val} >= 30 ✅"], 100
        elif news_momentum_sell:
            direction, reasons, strength = "SELL", [f"🔥 News Breakout ({news_title})", f"ADX {adx_val} >= 30 ✅"], 100
        elif buy_score >= min_score and buy_score > sell_score and buy_rsi_bb and ema200_bullish and macro_bullish:
            direction, reasons, strength = "BUY", buy_why, round((buy_score / 6) * 100)
        elif sell_score >= min_score and sell_score > buy_score and sell_rsi_bb and not ema200_bullish and macro_bearish:
            direction, reasons, strength = "SELL", sell_why, round((sell_score / 6) * 100)
        else:
            direction, strength = "NEUTRAL", round((max(buy_score, sell_score) / 6) * 100)
            reasons = []
            if buy_score >= min_score and buy_score > sell_score:
                if not buy_rsi_bb: reasons.append("⚠️ RSI/BB confirmation නෑ")
                elif not ema200_bullish: reasons.append("⚠️ EMA200 downtrend")
                elif not macro_bullish: reasons.append("⚠️ Macro downtrend (20h)")
            elif sell_score >= min_score and sell_score > buy_score:
                if not sell_rsi_bb: reasons.append("⚠️ RSI/BB confirmation නෑ")
                elif ema200_bullish: reasons.append("⚠️ EMA200 uptrend")
                elif not macro_bearish: reasons.append("⚠️ Macro uptrend (20h)")
            elif sym in VOLATILE_PAIRS and max(buy_score, sell_score) == 4: reasons.append(f"⚠️ {sym} 4/6 — 5/6 required")
            else: reasons.append("⚖️ Waiting for setup")

        # ── RISK MANAGEMENT ──────────────────────────────────────────────────
        sl = tp1 = tp2 = rr = None
        if direction in ("BUY", "SELL"):
            # News Breakout සඳහා 5m/1m චාට් එකට ගැළපෙන පරිදි SL ටිකක් විශාල කරයි
            sl_multiplier = 3.0 if is_news_momentum else ATR_SL_MULTI
            sl_dist = atr_v * sl_multiplier
            
            actual_sl = max(min(sl_dist, self._get_max_sl_dist()), self._get_min_sl_dist())
            ratio = ATR_TP_MULTI / ATR_SL_MULTI
            actual_tp = actual_sl * ratio

            if direction == "BUY":
                sl, tp1, tp2 = round(p - actual_sl, 5), round(p + actual_tp * 0.6, 5), round(p + actual_tp, 5)
            else:
                sl, tp1, tp2 = round(p + actual_sl, 5), round(p - actual_tp * 0.6, 5), round(p - actual_tp, 5)
            rr = round(ratio, 1)

        valid_until_str = (now_utc + timedelta(minutes=SIGNAL_VALID_MINUTES) + timedelta(hours=5, minutes=30)).strftime("%I:%M %p") + " (LK)"

        return {
            "symbol": self.symbol, "price": p, "direction": direction, "strength": strength, "buy_score": buy_score, "sell_score": sell_score,
            "reasons": reasons, "session": session_name, "session_ok": True, "news_blocked": False, "valid_until": valid_until_str,
            "pos_size_warn": POSITION_SIZE_WARNINGS.get(sym), "rsi": rsi_now, "ema20": ema20_v, "ema50": ema50_v, "ema200": ema200_v,
            "macd": macd_v, "atr": atr_v, "adx": adx_val, "stop_loss": sl, "take_profit1": tp1, "take_profit2": tp2, "risk_reward": rr,
        }