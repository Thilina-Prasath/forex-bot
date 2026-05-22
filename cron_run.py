import sys
import os
from datetime import datetime, timezone

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FOREX_PAIRS
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

    # Validate
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ❌ Telegram credentials missing!")
        sys.exit(1)

    # Check for TwelveData Key
    twelvedata_key = os.environ.get("TWELVEDATA_KEY")
    if not twelvedata_key:
        print("  ❌ TWELVEDATA_KEY missing in environment variables!")
        print("  Get free key: https://twelvedata.com/")
        sys.exit(1)

    fetcher  = DataFetcher()
    notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    sent_count = 0
    pairs_list = list(FOREX_PAIRS.items())

    for name, ticker in pairs_list:
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

        print(f"     → {d:7s} | {s:3d}% | {score}/6", end="")

        # Filter and Send
        if d != "NEUTRAL" and score >= QUALITY_MIN_SCORE:
            notifier.send_signal(sig)
            sent_count += 1
            print(f"  ✅ Sent!")
        else:
            print(f"  ⚪ Skipped")

    print(f"\n{'═'*52}")
    if sent_count > 0:
        print(f"  ✅ {sent_count} signal(s) sent to Telegram!")
    else:
        print(f"  ⚪ No strong signals this scan.")
    print(f"{'═'*52}\n")


if __name__ == "__main__":
    main()