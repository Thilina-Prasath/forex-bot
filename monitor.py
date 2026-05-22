import time
import sys
from datetime import datetime, timezone, date

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    FOREX_PAIRS, CANDLES_PERIOD,
)
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier


# ─── Settings ────────────────────────────────────────────────────────
SCAN_INTERVAL_HOURS  = 4      
QUALITY_MIN_SCORE    = 4      # 6 න් minimum 4 — strong signal only
QUALITY_MIN_STRENGTH = 60     # minimum 60% strength

# ─────────────────────────────────────────────────────────────────────

fetcher  = DataFetcher()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

# Format: { "EURUSD": {"direction": "BUY", "date": date(2026,5,19)} }
sent_today: dict = {}


def already_sent(pair: str, direction: str) -> bool:
    """Same pair + same direction today """
    if pair not in sent_today:
        return False
    entry = sent_today[pair]
    return entry["direction"] == direction and entry["date"] == date.today()


def mark_sent(pair: str, direction: str):
    sent_today[pair] = {"direction": direction, "date": date.today()}


def is_quality_signal(sig: dict) -> bool:
    
    if sig["direction"] == "NEUTRAL":
        return False

    score = sig["buy_score"] if sig["direction"] == "BUY" else sig["sell_score"]

    return (
        score    >= QUALITY_MIN_SCORE and
        sig["strength"] >= QUALITY_MIN_STRENGTH
    )


def scan_all_pairs() -> list:
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  🔍 Scanning...  |  {now}")

    found = []

    for name, ticker in FOREX_PAIRS.items():
        df = fetcher.get_candles(name, ticker, CANDLES_PERIOD)
        if df is None:
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ {name}: {e}")
            continue

        d = sig["direction"]
        s = sig["strength"]
        score = sig["buy_score"] if d == "BUY" else sig["sell_score"]

        print(f"     {name:8s} → {d:7s} | {s:3d}% | {score}/6", end="")

        if is_quality_signal(sig):
            if already_sent(name, d):
                print("  ⏭️  (already sent today)")
            else:
                print("  🚀 SIGNAL!")
                found.append(sig)
                mark_sent(name, d)
        else:
            print()

        time.sleep(0.5)

    return found


def run_monitor():
    """
    Main loop — continuous monitoring.
    """
    print("""
╔══════════════════════════════════════════╗
   🤖  FOREX REAL-TIME MONITOR  v3.1
       Signal detected → Instant Telegram
╚══════════════════════════════════════════╝
""")
    print(f"  ⚙️  Scan interval  : Every {SCAN_INTERVAL_HOURS} hours")
    print(f"  ⚙️  Quality filter : Score {QUALITY_MIN_SCORE}/6+  |  Strength {QUALITY_MIN_STRENGTH}%+")
    print(f"  ⚙️  Pairs          : {', '.join(FOREX_PAIRS.keys())}")
    print(f"\n  Press Ctrl+C to stop\n")
    print("─" * 52)

    # Startup notification
    notifier.send(
        f"🤖 <b>Forex Monitor Started</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 Scanning every <b>{SCAN_INTERVAL_HOURS}h</b>\n"
        f"⭐ Quality filter: <b>{QUALITY_MIN_SCORE}/6+ score</b>\n"
        f"📊 Pairs: {' · '.join(FOREX_PAIRS.keys())}\n"
        f"<i>You'll be notified instantly when a strong signal appears.</i>"
    )

    scan_count = 0

    while True:
        try:
            scan_count += 1
            print(f"\n  [{scan_count}] Scan #{scan_count}")

            signals = scan_all_pairs()

            if signals:
                print(f"\n  ✅ {len(signals)} signal(s) found — sending to Telegram...")
                for sig in signals:
                    notifier.send_signal(sig)
                    print(f"     📤 Sent: {sig['symbol']} {sig['direction']} {sig['strength']}%")
            else:
                print(f"  ⚪ No strong signals this scan.")

            # Next scan time
            next_scan = datetime.now(timezone.utc)
            from datetime import timedelta
            next_time = (next_scan + timedelta(hours=SCAN_INTERVAL_HOURS)).strftime("%H:%M UTC")
            print(f"\n  ⏰ Next scan at {next_time}  (sleeping {SCAN_INTERVAL_HOURS}h...)")
            print("─" * 52)

            time.sleep(SCAN_INTERVAL_HOURS * 3600)

        except KeyboardInterrupt:
            print("\n\n  🛑 Monitor stopped.\n")
            notifier.send("🛑 <b>Forex Monitor stopped.</b>")
            break

        except Exception as e:
            print(f"\n  ❌ Unexpected error: {e}")
            print("  Retrying in 5 minutes...")
            time.sleep(300)


if __name__ == "__main__":
    # Config validation
    if TELEGRAM_BOT_TOKEN in ("YOUR_BOT_TOKEN", ""):
        print("\n  ❌ config.py හි TELEGRAM_BOT_TOKEN දාන්න!\n")
        sys.exit(1)
    if TELEGRAM_CHAT_ID in ("YOUR_CHAT_ID", ""):
        print("\n  ❌ config.py හි TELEGRAM_CHAT_ID දාන්න!\n")
        sys.exit(1)

    run_monitor()