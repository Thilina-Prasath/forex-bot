import sys
from datetime import datetime, timezone
import os

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    FOREX_PAIRS, CANDLES_PERIOD
)
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier

def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f" 🚀 Hourly Cron Scan Started  |  {now}")
    print(f"{'═'*52}")

    # Render Environment Variables වලින් Token ගැනීම (ආරක්ෂිත ක්‍රමය)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)

    if not token or not chat_id:
        print(" ❌ Error: Telegram Token or Chat ID is missing!")
        sys.exit(1)

    fetcher = DataFetcher()
    notifier = TelegramNotifier(token, chat_id)
    
    sent_signals_count = 0

    # හැම Pair එකක්ම චෙක් කිරීම
    for name, ticker in FOREX_PAIRS.items():
        print(f" 📊 Analyzing {name}...", end="")

        df = fetcher.get_candles(name, ticker, CANDLES_PERIOD)
        if df is None:
            print(" ❌ No Data")
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f" ❌ Error: {e}")
            continue

        d = sig["direction"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"]

        # ⚠️ STRICT FILTER: Loss අවම කිරීමට නීති
        # 1. BUY හෝ SELL විය යුතුයි.
        # 2. Indicators 6න් 4ක් වත් අනිවාර්යයෙන්ම එකඟ විය යුතුයි (Score >= 4).
        
        if d != "NEUTRAL" and score >= 4:
            notifier.send_signal(sig)
            sent_signals_count += 1
            print(f"  ✅ Sent! ({d} | Score: {score}/6)")
        else:
            print(f"  ⚪ Skipped (Not strong enough)")

    print(f"\n{'═'*52}")
    if sent_signals_count > 0:
        print(f" ✅ Successfully sent {sent_signals_count} HIGH QUALITY signals!")
    else:
        print(" ⚖️ No strong setups right now. Waiting for the next hour.")
    print(" 👋 Cron Job finished successfully. Shutting down...\n")


if __name__ == "__main__":
    main()