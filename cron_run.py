"""
cron_run.py — Hourly cron scan + News Momentum real-time watcher
================================================================
Mode 1 (Normal):    සෑම පැය 1 කට scan කරයි — technical signals
Mode 2 (News):     News window open වූ විගස විනාඩි 1 කට scan කරයි — momentum signals
                   News window (1–30 min after event) close වූ විගස normal mode ට හැරෙයි
"""

import time
import sys
from datetime import datetime, timezone, timedelta

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    FOREX_PAIRS, CANDLES_PERIOD,
)
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier
from news_filter       import check_news_conflict, get_high_impact_news

# ── Settings ──────────────────────────────────────────────────────────────────
NORMAL_SCAN_INTERVAL_MIN  = 60    # Normal market: පැය 1 කට scan
NEWS_SCAN_INTERVAL_SEC    = 60    # News window: විනාඩි 1 කට scan
QUALITY_MIN_SCORE         = 4
QUALITY_MIN_STRENGTH      = 60
NEWS_SIGNAL_COOLDOWN_MIN  = 10    # News signal: එකම pair ට විනාඩි 10 cooldown
NORMAL_SIGNAL_COOLDOWN_H  = 1     # Normal signal: පැය 1 cooldown

fetcher  = DataFetcher()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

# Sent signal tracking: {"EURUSD_BUY": datetime, ...}
_last_sent: dict[str, datetime] = {}


def _cooldown_ok(pair: str, direction: str, is_news: bool) -> bool:
    key     = f"{pair}_{direction}"
    last    = _last_sent.get(key)
    if last is None:
        return True
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    limit   = NEWS_SIGNAL_COOLDOWN_MIN * 60 if is_news else NORMAL_SIGNAL_COOLDOWN_H * 3600
    return elapsed >= limit


def _mark_sent(pair: str, direction: str):
    _last_sent[f"{pair}_{direction}"] = datetime.now(timezone.utc)


def _is_news_window_active() -> tuple[bool, str]:
    """ඕනෑම pair එකක news window open ද කියලා check කරයි."""
    for pair in FOREX_PAIRS:
        status, title = check_news_conflict(pair)
        if status == "NEWS_MOMENTUM":
            return True, f"{pair}: {title}"
    return False, ""


def _scan(label: str = "Scan") -> int:
    """
    සියලු pairs scan කර signals send කරයි.
    Returns: sent signal count
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 {label}  |  {now}")
    print(f"{'═'*52}")

    sent = 0

    for name, ticker in FOREX_PAIRS.items():
        print(f"  📊 {name} analyzing...")

        df = fetcher.get_candles(name, ticker, CANDLES_PERIOD)
        if df is None:
            print(f"     ⚠️  No data")
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ Error: {e}")
            continue

        d          = sig["direction"]
        s          = sig["strength"]
        score      = sig["buy_score"] if d == "BUY" else sig["sell_score"]
        is_news    = sig.get("news_momentum", False)
        news_tag   = " 📰" if is_news else ""

        if d == "NEUTRAL":
            reason = sig["reasons"][0] if sig["reasons"] else "No signal"
            print(f"     → NEUTRAL | {s:3d}% | {score}/6  ⚪ Skipped  [{reason}]")
            continue

        # Quality filter
        if score < QUALITY_MIN_SCORE or s < QUALITY_MIN_STRENGTH:
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⚠️  Below quality threshold")
            continue

        # Cooldown check
        if not _cooldown_ok(name, d, is_news):
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⏭️  Cooldown active")
            continue

        # Send!
        print(f"     → {d:7s} | {s:3d}% | {score}/6  ✅ SIGNAL{news_tag}")
        notifier.send_signal(sig)
        _mark_sent(name, d)
        sent += 1
        time.sleep(1)

    print(f"{'═'*52}")
    if sent == 0:
        print(f"  ⚪ No strong signals this scan.")
    else:
        print(f"  ✅ {sent} signal(s) sent.")
    print(f"{'═'*52}\n")
    return sent


def run_monitor():
    """
    Main loop:
      - News window නැත්නම්  → NORMAL mode (60 min interval)
      - News window ඇත්නම්  → NEWS mode   (1 min interval)
    """
    print("""
╔══════════════════════════════════════════╗
   🤖  FOREX SIGNAL BOT  v4.0
       News Momentum + Technical Signals
╚══════════════════════════════════════════╝
""")
    print(f"  ⚙️  Normal scan  : every {NORMAL_SCAN_INTERVAL_MIN} minutes")
    print(f"  ⚙️  News scan    : every {NEWS_SCAN_INTERVAL_SEC} seconds")
    print(f"  ⚙️  Pairs        : {', '.join(FOREX_PAIRS.keys())}")
    print(f"\n  Press Ctrl+C to stop\n")
    print("─" * 52)

    notifier.send(
        f"🤖 <b>Forex Bot v4.0 Started</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 News Momentum mode: <b>ACTIVE</b>\n"
        f"📊 Technical mode: <b>ACTIVE</b>\n"
        f"🔍 {len(FOREX_PAIRS)} pairs monitored\n"
        f"<i>News break → 60s scan. Normal → 60min scan.</i>"
    )

    last_normal_scan = datetime.now(timezone.utc) - timedelta(hours=1)  # first scan immediate

    while True:
        try:
            now_utc = datetime.now(timezone.utc)

            # ── NEWS MODE check ───────────────────────────────────────────
            news_active, news_info = _is_news_window_active()

            if news_active:
                print(f"\n  📰 NEWS WINDOW ACTIVE: {news_info}")
                _scan(label="News Momentum Scan")
                print(f"  ⏰ Next news scan in {NEWS_SCAN_INTERVAL_SEC}s...")
                time.sleep(NEWS_SCAN_INTERVAL_SEC)

            else:
                # ── NORMAL MODE: 60 min interval ─────────────────────────
                elapsed_min = (now_utc - last_normal_scan).total_seconds() / 60

                if elapsed_min >= NORMAL_SCAN_INTERVAL_MIN:
                    _scan(label="Hourly Cron Scan")
                    last_normal_scan = now_utc
                    next_time = (now_utc + timedelta(minutes=NORMAL_SCAN_INTERVAL_MIN)).strftime("%H:%M UTC")
                    print(f"  ⏰ Next normal scan at {next_time}")
                else:
                    remaining = int(NORMAL_SCAN_INTERVAL_MIN - elapsed_min)
                    print(f"  💤 Normal mode — next scan in {remaining} min  |  "
                          f"{now_utc.strftime('%H:%M UTC')}")

                # News check interval: 30 seconds (light — no API calls, only cached data)
                time.sleep(30)

        except KeyboardInterrupt:
            print("\n\n  🛑 Bot stopped.\n")
            notifier.send("🛑 <b>Forex Bot stopped.</b>")
            break

        except Exception as e:
            print(f"\n  ❌ Unexpected error: {e}")
            print("  Retrying in 60 seconds...")
            time.sleep(60)


if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN in ("YOUR_BOT_TOKEN", ""):
        print("\n  ❌ config.py හි TELEGRAM_BOT_TOKEN දාන්න!\n")
        sys.exit(1)
    if TELEGRAM_CHAT_ID in ("YOUR_CHAT_ID", ""):
        print("\n  ❌ config.py හි TELEGRAM_CHAT_ID දාන්න!\n")
        sys.exit(1)
    run_monitor()