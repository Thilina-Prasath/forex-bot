import sys
import os
from datetime import datetime, timezone

from config            import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FOREX_PAIRS
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier

# Signal quality filter
QUALITY_MIN_SCORE = 4


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 Hourly Cron Scan  |  {now}")
    print(f"{'═'*52}")

    # Validate Telegram credentials
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ❌ Telegram credentials missing!")
        sys.exit(1)

    # Validate TwelveData key
    if not os.environ.get("TWELVEDATA_KEY"):
        print("  ❌ TWELVEDATA_KEY missing in environment variables!")
        print("  Get free key: https://twelvedata.com/")
        sys.exit(1)

    fetcher  = DataFetcher()
    notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    sent_count = 0

    for name, ticker in list(FOREX_PAIRS.items()):
        print(f"\n  📊 {name} analyzing...")

        df = fetcher.get_candles(name, ticker)
        if df is None:
            print(f"     ❌ No data")
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ Analysis error: {e}")
            continue

        d     = sig["direction"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"]
        s     = sig["strength"]

        # ── CASE 1: Off-session ──────────────────────────────────────────
        if not sig.get("session_ok", True):
            session_msg = sig.get("session", "Off-session")
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⏸️  {session_msg}")
            continue

        # ── CASE 1b: News blocked ─────────────────────────────────────────
        if sig.get("news_blocked", False):
            reason = sig.get("reasons", ["🚨 News blocked"])[0]
            print(f"     → {d:7s} | {s:3d}% | {score}/6  {reason}")
            continue

        # ── CASE 2: Signal valid — send to Telegram ──────────────────────
        if d != "NEUTRAL" and score >= QUALITY_MIN_SCORE:
            notifier.send_signal(sig)
            sent_count += 1
            session_msg = sig.get("session", "")
            valid_until = sig.get("valid_until", "")
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ✅ Sent!  [{session_msg}]  valid: {valid_until}")

        # ── CASE 3: NEUTRAL හෝ score low — block හේතුව print කරනවා ──────
        else:
            reasons = sig.get("reasons", [])

            # Block හේතුව classify කරනවා
            if d != "NEUTRAL" and score >= QUALITY_MIN_SCORE:
                # Should not reach here — safety fallback
                block_reason = "Unknown filter"
            elif d == "NEUTRAL":
                # Analyzer NEUTRAL return කළා — reasons ඇතුළෙ හේතුව
                if reasons:
                    block_reason = reasons[0]
                else:
                    block_reason = "No clear signal"
            else:
                # Score low (< MIN_SCORE)
                block_reason = f"Score too low ({score}/{QUALITY_MIN_SCORE} required)"

            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⚪ Skipped  [{block_reason}]")

    print(f"\n{'═'*52}")
    if sent_count > 0:
        print(f"  ✅ {sent_count} signal(s) sent to Telegram!")
    else:
        print(f"  ⚪ No strong signals this scan.")
    print(f"{'═'*52}\n")


if __name__ == "__main__":
    main()