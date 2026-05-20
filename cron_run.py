"""
Forex Signal Bot — Cron Runner v4
───────────────────────────────────
Render Cron Job විදිහට run වෙනවා.
Alpha Vantage free API use කරනවා (cloud compatible).

Free API limits:
  • 25 requests/day
  • 5 requests/minute → pairs අතර 13s delay

render.yaml schedule: "2 */4 * * *" = හැම පැය 4 කට
"""

import sys
import time
from datetime import datetime, timezone

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FOREX_PAIRS, ALPHA_VANTAGE_KEY
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier


# Signal quality filter
QUALITY_MIN_SCORE = 4   # 6 න් 4+


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 Cron Scan  |  {now}")
    print(f"{'═'*52}")

    # Validate
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ❌ Telegram credentials missing!")
        sys.exit(1)

    if ALPHA_VANTAGE_KEY in ("YOUR_AV_KEY", "", None):
        print("  ❌ ALPHA_VANTAGE_KEY missing in environment variables!")
        print("  Get free key: https://www.alphavantage.co/support/#api-key")
        sys.exit(1)

    fetcher  = DataFetcher()
    notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    sent_count = 0
    pairs_list = list(FOREX_PAIRS.items())

    for i, (name, ticker) in enumerate(pairs_list):
        print(f"\n  📊 {name} analyzing...")

        df = fetcher.get_candles(name, ticker)
        if df is None:
            print(f"     ❌ No data")
            # Wait before next request even on failure
            if i < len(pairs_list) - 1:
                time.sleep(13)
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ Analysis error: {e}")
            if i < len(pairs_list) - 1:
                time.sleep(13)
            continue

        d     = sig["direction"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"]
        s     = sig["strength"]

        print(f"     → {d:7s} | {s:3d}% | {score}/6", end="")

        if d != "NEUTRAL" and score >= QUALITY_MIN_SCORE:
            notifier.send_signal(sig)
            sent_count += 1
            print(f"  ✅ Sent!")
        else:
            print(f"  ⚪ Skipped")

        # Alpha Vantage free: 5 requests/minute → wait 13s between requests
        if i < len(pairs_list) - 1:
            print(f"     ⏳ Waiting 13s (API rate limit)...")
            time.sleep(13)

    print(f"\n{'═'*52}")
    if sent_count > 0:
        print(f"  ✅ {sent_count} signal(s) sent to Telegram!")
    else:
        print(f"  ⚪ No strong signals this scan.")
    print(f"{'═'*52}\n")


if __name__ == "__main__":
    main()