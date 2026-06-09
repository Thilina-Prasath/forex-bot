import sys
import os
from datetime import datetime, timezone, timedelta

from config            import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FOREX_PAIRS
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier

QUALITY_MIN_SCORE = 4
COOLDOWN_HOURS = 2
_last_sent: dict[str, datetime] = {}

def _is_in_cooldown(symbol: str, direction: str, now_utc: datetime) -> tuple[bool, int]:
    key = f"{symbol}_{direction}"
    last = _last_sent.get(key)
    if last and (now_utc - last) < timedelta(hours=COOLDOWN_HOURS):
        remaining = COOLDOWN_HOURS * 60 - int((now_utc - last).total_seconds() / 60)
        return True, remaining
    return False, 0

def main():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 High-Frequency Scan (5m)  |  {now_str}")
    print(f"{'═'*52}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ❌ Telegram credentials missing!")
        sys.exit(1)

    fetcher  = DataFetcher()
    notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    sent_count = 0

    for name, ticker in list(FOREX_PAIRS.items()):
        print(f"\n  📊 {name} analyzing...")

        # ── Yahoo Finance මඟින් විනාඩි 5 දත්ත ලබා ගැනීම ────────────────────
        df = fetcher.get_candles(name, ticker, interval="5m")
        if df is None:
            print(f"     ❌ No data")
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ Analysis error: {e}")
            continue

        d = sig["direction"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"] if d == "SELL" else max(sig["buy_score"], sig["sell_score"])
        strength = sig["strength"]

        if not sig.get("session_ok", True):
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  ⏸️  {sig.get('session', 'Off-session')}")
            continue

        if sig.get("news_blocked", False):
            reason = sig.get("reasons", ["🚨 News blocked"])[0]
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  {reason}")
            continue

        if d != "NEUTRAL":
            now_utc = datetime.now(timezone.utc)
            in_cd, rem = _is_in_cooldown(sig["symbol"], d, now_utc)
            if in_cd:
                print(f"     → {d:7s} | {strength:3d}% | {score}/6  🔁 Cooldown {rem}min remaining")
                continue

            notifier.send_signal(sig)
            _last_sent[f"{sig['symbol']}_{d}"] = now_utc
            sent_count += 1
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  ✅ Sent!  valid: {sig.get('valid_until', '')}")

        else:
            reasons = sig.get("reasons", [])
            block_reason = reasons[0] if reasons else "No clear signal"
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  ⚪ Skipped  [{block_reason}]")

    print(f"\n{'═'*52}")
    if sent_count > 0: print(f"  ✅ {sent_count} signal(s) sent to Telegram!")
    else: print(f"  ⚪ No strong signals this scan.")
    print(f"{'═'*52}\n")

if __name__ == "__main__":
    main()