import requests
from datetime import datetime, timezone
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
            time.sleep(3) # avoid hitting rate limits if sending multiple messages

            return resp.status_code == 200
        except Exception as e:
            print(f"  Telegram error: {e}")
            return False

    def format_signal(self, sig: dict) -> str:
        d     = sig["direction"]
        s     = sig["strength"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"]
        now   = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M UTC")

        # Pair-specific decimal places
        sym = sig["symbol"]
        dec = 3 if "JPY" in sym else (2 if sym in ["GOLD", "BTCUSD"] else 5)
        fmt = lambda v: f"{v:.{dec}f}" if v else "—"

        if d == "BUY":
            icon   = "🟢"
            label  = "BUY"
        elif d == "SELL":
            icon   = "🔴"
            label  = "SELL"
        else:
            # NEUTRAL — short message, no trade setup
            return (
                f"⚪ <b>{sym}</b> — NEUTRAL\n"
                f"Strength: {s}%  |  {score}/6 signals\n"
                f"<i>Wait for clearer setup.</i>"
            )

        # Strength bar
        filled = max(0, min(5, round(s / 20)))
        bar    = "█" * filled + "░" * (5 - filled)

        # Reasons — short labels only
        reasons = "\n".join(f"  • {r}" for r in sig["reasons"])

        msg = (
            f"{icon} <b>{sym}  —  {label}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Entry : <b>{fmt(sig['price'])}</b>\n"
            f"🛑 SL    : <b>{fmt(sig['stop_loss'])}</b>\n"
            f"🎯 TP1   : <b>{fmt(sig['take_profit1'])}</b>\n"
            f"🎯 TP2   : <b>{fmt(sig['take_profit2'])}</b>\n"
            f"⚖️ R:R   : 1 : {sig['risk_reward']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Strength : {s}%  [{bar}]  {score}/6\n"
            f"🔍 Signals  :\n{reasons}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {now}\n"
            f"<i>⚠️ Demo/educational use only.</i>"
        )
        return msg

    def send_signal(self, sig: dict) -> bool:
        return self.send(self.format_signal(sig))

    def send_summary(self, signals: list) -> bool:
        buys  = [s for s in signals if s["direction"] == "BUY"]
        sells = [s for s in signals if s["direction"] == "SELL"]
        date  = datetime.now(timezone.utc).strftime("%d %b %Y")

        msg = (
            f"📋 <b>Daily Summary  —  {date}</b>\n"
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
        pair_list = "  •  ".join(pairs)
        msg = (
            f"🤖 <b>Forex Signal Bot v3 Started</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 {pair_list}\n"
            f"⏰ Daily signal: 05:35 AM (SL time)\n"
            f"✅ MT5-free  |  yfinance data\n"
            f"<i>Bot is live. Happy trading! 🚀</i>"
        )
        return self.send(msg)