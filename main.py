import time
import sys
import schedule
from datetime import datetime, timezone

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    FOREX_PAIRS, SIGNAL_TIME_UTC, MIN_SCORE,
    CANDLES_PERIOD,
)
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier


fetcher  = DataFetcher()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)



def run_analysis():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  Analysis started  |  {now}")
    print(f"{'═'*52}")

    all_signals  = []
    sent_signals = 0

    for name, ticker in FOREX_PAIRS.items():
        print(f"\n  📊 {name} analyzing...")

        df = fetcher.get_candles(name, ticker, CANDLES_PERIOD)
        if df is None:
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ Analysis error: {e}")
            continue

        all_signals.append(sig)
        d = sig["direction"]
        s = sig["strength"]
        p = sig["price"]

        print(f"     → {d:7s} | Strength: {s:3d}% | Price: {p}")

        # ── Only send BUY / SELL — skip NEUTRAL ──
        if d != "NEUTRAL":
            notifier.send_signal(sig)
            sent_signals += 1
            print(f"     ✅ Signal sent to Telegram!")
        else:
            print(f"     ⚪ Neutral — skipped")

        time.sleep(1)

    # Summary
    notifier.send_summary(all_signals)
    buys  = sum(1 for s in all_signals if s["direction"] == "BUY")
    sells = sum(1 for s in all_signals if s["direction"] == "SELL")
    print(f"\n  ✅ Done  |  BUY:{buys}  SELL:{sells}  (Sent: {sent_signals})")
    print(f"{'═'*52}\n")

    return all_signals


#  SINGLE PAIR

def analyze_one(name: str, ticker: str):
    print(f"\n  📊 Analyzing: {name}...")

    df = fetcher.get_candles(name, ticker, CANDLES_PERIOD)
    if df is None:
        print(f"  ❌ No data for {name}")
        return

    sig = ForexAnalyzer(name, df).generate()
    notifier.send_signal(sig)

    print(f"  Direction : {sig['direction']}")
    print(f"  Strength  : {sig['strength']}%")
    print(f"  Price     : {sig['price']}")
    if sig["stop_loss"]:
        print(f"  SL  → {sig['stop_loss']}")
        print(f"  TP1 → {sig['take_profit1']}")
        print(f"  TP2 → {sig['take_profit2']}")
    print(f"  ✅ Sent to Telegram\n")



#  SCHEDULER

def start_scheduler():
    print(f"\n  ⏰ Scheduler starting...")
    print(f"     Signal time : {SIGNAL_TIME_UTC} UTC  (SL ≈ 05:35 AM)")
    print(f"     Press Ctrl+C to stop\n")

    notifier.send_startup(list(FOREX_PAIRS.keys()))
    schedule.every().day.at(SIGNAL_TIME_UTC).do(run_analysis)

    print(f"  ✅ Next run: {schedule.next_run()}\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n\n  🛑 Scheduler stopped.\n")



#  MENU
def validate_config() -> bool:
    errors = []
    if TELEGRAM_BOT_TOKEN in ("YOUR_BOT_TOKEN", ""):
        errors.append("TELEGRAM_BOT_TOKEN not set in config.py")
    if TELEGRAM_CHAT_ID in ("YOUR_CHAT_ID", ""):
        errors.append("TELEGRAM_CHAT_ID not set in config.py")
    if errors:
        print("\n  ❌ CONFIG ERRORS:")
        for e in errors:
            print(f"     • {e}")
        print("\n  config.py edit කරලා token + chat_id දාන්න.\n")
        return False
    return True


def print_banner():
    print("""
╔══════════════════════════════════════════╗
   🤖  FOREX SIGNAL BOT  v3.0
       MT5-FREE  |  yfinance  |  Telegram
╚══════════════════════════════════════════╝
""")


def print_menu():
    print("""
  ┌───────────────────────────────────┐
  │  1.  Analyze ALL pairs NOW        │
  │  2.  Analyze single pair          │
  │  3.  Start daily auto-scheduler   │
  │  4.  Test Telegram connection     │
  │  5.  Exit                         │
  └───────────────────────────────────┘
""")


def main():
    print_banner()

    if not validate_config():
        sys.exit(1)

    pairs_list = list(FOREX_PAIRS.items())

    while True:
        print_menu()
        choice = input("  Choice (1-5): ").strip()

        if choice == "1":
            run_analysis()

        elif choice == "2":
            print("\n  Available pairs:")
            for i, (name, _) in enumerate(pairs_list, 1):
                print(f"    {i}. {name}")
            raw = input("\n  Pair number: ").strip()
            try:
                name, ticker = pairs_list[int(raw) - 1]
                analyze_one(name, ticker)
            except (ValueError, IndexError):
                print("  ❌ Invalid selection\n")

        elif choice == "3":
            start_scheduler()

        elif choice == "4":
            print("\n  📡 Testing Telegram...")
            ok = notifier.send(
                "✅ <b>Forex Bot v3 — Connection Test</b>\n\n"
                "Bot is connected!\n"
                "<i>MT5-free | yfinance data</i>"
            )
            print("  ✅ Success! Check Telegram.\n" if ok else "  ❌ Failed. Check config.py\n")

        elif choice == "5":
            print("\n  👋 Goodbye!\n")
            break

        else:
            print("  ❌ Invalid choice.\n")


if __name__ == "__main__":
    main()