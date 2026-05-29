import requests
from datetime import datetime, timezone, timedelta
import time

class TelegramNotifier:

    def __init__(self, token: str, chat_id: str):
        self.token   = token
        self.chat_id = chat_id
        self.api     = f"https://api.telegram.org/bot{token}"

    def send(self, text: str) -> bool:
        try:
            resp = requests.post(
                f"{self.api}/sendMessage",
                json={
                    "chat_id":    self.chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )
            time.sleep(3)

            if resp.status_code != 200:
                print(f"     ❌ Telegram Rejected: {resp.text}")
                return False

            return True
        except Exception as e:
            print(f"  Telegram error: {e}")
            return False

    def format_signal(self, sig: dict) -> str:
        d     = sig["direction"]
        s     = sig["strength"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"]

        # UTC + ලංකා වෙලාව දෙකම show කරනවා
        now_utc = datetime.now(timezone.utc)
        now_lk  = now_utc + timedelta(hours=5, minutes=30)
        time_str = (
            f"{now_lk.strftime('%d %b %Y  %I:%M %p')} LK  "
            f"({now_utc.strftime('%H:%M')} UTC)"
        )

        # Session info
        session_name = sig.get("session", "Unknown")

        # Pair-specific decimal places
        sym = sig["symbol"]
        dec = 3 if "JPY" in sym else (2 if sym in ["GOLD", "BTCUSD"] else 5)
        fmt = lambda v: f"{v:.{dec}f}" if v is not None else "—"

        # ── OFF-SESSION message ──────────────────────────────────────────────
        if not sig.get("session_ok", True):
            reason = sig["reasons"][0] if sig["reasons"] else "Off-session"
            return (
                f"⏸️ <b>{sym}</b> — Signal Skipped\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🕐 {time_str}\n"
                f"📍 Session: {reason}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>ලංකා වෙලාව 1:30 PM – 9:00 PM ට signal බලන්න.</i>"
            )

        # ── NEUTRAL message ──────────────────────────────────────────────────
        if d == "NEUTRAL":
            reasons_text = "\n".join(
                f"  • {r.replace('<','&lt;').replace('>','&gt;')}"
                for r in sig["reasons"]
            )
            return (
                f"⚪ <b>{sym}</b> — NEUTRAL\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 {score}/6 signals  |  Strength: {s}%\n"
                f"🔍 Reason:\n{reasons_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🕐 {time_str}\n"
                f"<i>⏳ Clearer setup එන්නකල් wait කරන්න.</i>"
            )

        # ── BUY / SELL message ───────────────────────────────────────────────
        icon  = "🟢" if d == "BUY" else "🔴"

        filled = max(0, min(5, round(s / 20)))
        bar    = "█" * filled + "░" * (5 - filled)

        clean_reasons = "\n".join(
            f"  • {r.replace('<','&lt;').replace('>','&gt;')}"
            for r in sig["reasons"]
        )

        # ── ENTRY VALIDITY WINDOW (Change 2) ────────────────────────────────
        # Telegram message ලැබුණු වහාම enter කළ යුතුයි.
        # valid_until වෙලාවෙන් පසු signal expired — trade නොගන්න.
        valid_until = sig.get("valid_until", "—")

        msg = (
            f"{icon} <b>{sym}  —  {d}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Entry : <b>{fmt(sig['price'])}</b>\n"
            f"🛑 SL    : <b>{fmt(sig['stop_loss'])}</b>\n"
            f"🎯 TP1   : <b>{fmt(sig['take_profit1'])}</b>\n"
            f"🎯 TP2   : <b>{fmt(sig['take_profit2'])}</b>\n"
            f"⚖️ R:R   : 1 : {sig['risk_reward']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Strength : {s}%  [{bar}]  {score}/6\n"
            f"📍 Session  : {session_name}\n"
            f"🔍 Signals  :\n{clean_reasons}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {time_str}\n"
            f"⚡ <b>Valid until: {valid_until}</b>\n"
            f"❌ <b>මේ වෙලාවෙන් පසු skip කරන්න!</b>\n"
            + (f"━━━━━━━━━━━━━━━━━━━━\n{sig.get('pos_size_warn')}\n"
               if sig.get("pos_size_warn") else "")
            + f"<i>⚠️ Demo/educational use only.</i>"
        )
        return msg

    def send_signal(self, sig: dict) -> bool:
        # Session බාහිර signals send නොකරනවා (off-session NEUTRAL skip)
        if not sig.get("session_ok", True):
            print(f"  ⏸️  {sig['symbol']} — Off-session, signal not sent.")
            return False
        return self.send(self.format_signal(sig))

    def send_summary(self, signals: list) -> bool:
        buys  = [s for s in signals if s["direction"] == "BUY"]
        sells = [s for s in signals if s["direction"] == "SELL"]

        now_utc = datetime.now(timezone.utc)
        now_lk  = now_utc + timedelta(hours=5, minutes=30)
        date_str = now_lk.strftime("%d %b %Y")

        msg = (
            f"📋 <b>Daily Summary  —  {date_str}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 BUY  : <b>{len(buys)}</b>   🔴 SELL : <b>{len(sells)}</b>\n"
        )

        if buys:
            msg += "\n🟢 <b>BUY:</b>\n"
            for s in sorted(buys, key=lambda x: x["strength"], reverse=True):
                msg += f"  • <b>{s['symbol']}</b>  {s['strength']}%  @ {s['price']}\n"

        if sells:
            msg += "\n🔴 <b>SELL:</b>\n"
            for s in sorted(sells, key=lambda x: x["strength"], reverse=True):
                msg += f"  • <b>{s['symbol']}</b>  {s['strength']}%  @ {s['price']}\n"

        if not buys and not sells:
            msg += "\n<i>No strong signals today. Market is ranging.</i>\n"

        msg += "\n<i>⚠️ Educational only. DYOR.</i>"
        return self.send(msg)

    def send_error(self, msg: str) -> bool:
        return self.send(f"⚠️ <b>Bot Error:</b>\n<code>{msg}</code>")

    def send_startup(self, pairs: list) -> bool:
        now_lk = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        pair_list = "  •  ".join(pairs)
        msg = (
            f"🤖 <b>Forex Signal Bot v4 Started</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 {pair_list}\n"
            f"⏰ Active session: 1:30 PM – 9:00 PM LK\n"
            f"⚡ Signal validity: 3 minutes only\n"
            f"✅ Session filter  |  RSI/BB mandatory  |  EMA200 aligned\n"
            f"<i>Bot is live. Trade safe! 🚀</i>"
        )
        return self.send(msg)