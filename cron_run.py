"""
cron_run.py — Hourly cron scan + News Momentum real-time watcher
================================================================
Mode 1 (Normal):    සෑම පැය 1 කට scan කරයි — technical signals
Mode 2 (News):      News window open වූ විගස විනාඩි 1 කට scan කරයි — momentum signals
                    News window (1–30 min after event) close වූ විගස normal mode ට හැරෙයි

Fixes:
  - is_news_scan ParameterError fix
  - News window ෙදිගටම same pair opposite direction block (30 min)
"""

import time
import sys
from datetime import datetime, timezone, timedelta

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    FOREX_PAIRS,
)

# Candle intervals
NORMAL_INTERVAL = "1h"   # Technical scan — EMA200 ට 60d×24h = 1440 candles
NEWS_INTERVAL   = "5m"   # News momentum — fast price movement detect

from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier
from news_filter       import check_news_conflict

# ── Settings ──────────────────────────────────────────────────────────────────
NORMAL_SCAN_INTERVAL_MIN  = 60    # Normal market: පැය 1 කට scan
NEWS_SCAN_INTERVAL_SEC    = 60    # News window: විනාඩි 1 කට scan
QUALITY_MIN_SCORE         = 4
QUALITY_MIN_STRENGTH      = 60
NEWS_SIGNAL_COOLDOWN_MIN  = 30    # News signal: same pair ANY direction — විනාඩි 30 block
NORMAL_SIGNAL_COOLDOWN_H  = 1     # Normal signal: පැය 1 cooldown

fetcher  = DataFetcher()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

# Sent signal tracking:
#   News:   {"EURUSD": datetime}          — pair level (BUY/SELL both blocked)
#   Normal: {"EURUSD_BUY": datetime}      — direction level
_news_last_sent:   dict[str, datetime] = {}
_normal_last_sent: dict[str, datetime] = {}


def _news_cooldown_ok(pair: str) -> bool:
    """News mode — same pair ට ANY direction 30 min block."""
    last = _news_last_sent.get(pair)
    if last is None:
        return True
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    return elapsed >= NEWS_SIGNAL_COOLDOWN_MIN * 60


def _normal_cooldown_ok(pair: str, direction: str) -> bool:
    """Normal mode — same pair + same direction 1 hour block."""
    key  = f"{pair}_{direction}"
    last = _normal_last_sent.get(key)
    if last is None:
        return True
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    return elapsed >= NORMAL_SIGNAL_COOLDOWN_H * 3600


def _mark_news_sent(pair: str):
    _news_last_sent[pair] = datetime.now(timezone.utc)


def _mark_normal_sent(pair: str, direction: str):
    _normal_last_sent[f"{pair}_{direction}"] = datetime.now(timezone.utc)


def _is_news_window_active() -> tuple[bool, str]:
    """ඕනෑම pair එකක news window open ද කියලා check කරයි."""
    for pair in FOREX_PAIRS:
        status, title = check_news_conflict(pair)
        if status == "NEWS_MOMENTUM":
            return True, f"{pair}: {title}"
    return False, ""


def _scan(label: str = "Scan", is_news_scan: bool = False) -> int:
    """
    සියලු pairs scan කර signals send කරයි.
    is_news_scan=True  → 5m candles, pair-level cooldown
    is_news_scan=False → 1h candles, direction-level cooldown
    Returns: sent signal count
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 {label}  |  {now}")
    print(f"{'═'*52}")

    sent     = 0
    interval = NEWS_INTERVAL if is_news_scan else NORMAL_INTERVAL

    for name, ticker in FOREX_PAIRS.items():
        print(f"  📊 {name} analyzing...")

        df = fetcher.get_candles(name, ticker, interval)
        if df is None:
            print(f"     ⚠️  No data")
            continue

        try:
            sig = ForexAnalyzer(name, df).generate()
        except Exception as e:
            print(f"     ❌ Error: {e}")
            continue

        d       = sig["direction"]
        s       = sig["strength"]
        score   = sig["buy_score"] if d == "BUY" else sig["sell_score"]
        is_news = sig.get("news_momentum", False)
        tag     = " 📰" if is_news else ""

        if d == "NEUTRAL":
            reason = sig["reasons"][0] if sig["reasons"] else "No signal"
            print(f"     → NEUTRAL | {s:3d}% | {score}/6  ⚪ Skipped  [{reason}]")
            continue

        # Quality filter
        if score < QUALITY_MIN_SCORE or s < QUALITY_MIN_STRENGTH:
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⚠️  Below quality threshold")
            continue

        # ── Cooldown check ────────────────────────────────────────────────
        if is_news_scan:
            # News mode: same pair BUY ආවා නම් SELL ද block — 30 min
            if not _news_cooldown_ok(name):
                remaining = int(NEWS_SIGNAL_COOLDOWN_MIN - (
                    datetime.now(timezone.utc) - _news_last_sent[name]
                ).total_seconds() / 60)
                print(f"     → {d:7s} | {s:3d}% | {score}/6  ⏭️  News cooldown ({remaining}min left)")
                continue
        else:
            # Normal mode: same pair + same direction 1 hour block
            if not _normal_cooldown_ok(name, d):
                print(f"     → {d:7s} | {s:3d}% | {score}/6  ⏭️  Cooldown active")
                continue

        # ── Send signal ───────────────────────────────────────────────────
        print(f"     → {d:7s} | {s:3d}% | {score}/6  ✅ SIGNAL{tag}")
        notifier.send_signal(sig)

        if is_news_scan:
            _mark_news_sent(name)
        else:
            _mark_normal_sent(name, d)

        sent += 1
        time.sleep(1)

    print(f"{'═'*52}")
    print(f"  {'✅ ' + str(sent) + ' signal(s) sent.' if sent else '⚪ No strong signals this scan.'}")
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
   🤖  FOREX SIGNAL BOT  v4.1
       News Momentum + Technical Signals
╚══════════════════════════════════════════╝
""")
    print(f"  ⚙️  Normal scan     : every {NORMAL_SCAN_INTERVAL_MIN} minutes")
    print(f"  ⚙️  News scan       : every {NEWS_SCAN_INTERVAL_SEC} seconds")
    print(f"  ⚙️  News cooldown   : {NEWS_SIGNAL_COOLDOWN_MIN} min (any direction)")
    print(f"  ⚙️  Normal cooldown : {NORMAL_SIGNAL_COOLDOWN_H} hour (same direction)")
    print(f"  ⚙️  Pairs           : {', '.join(FOREX_PAIRS.keys())}")
    print(f"\n  Press Ctrl+C to stop\n")
    print("─" * 52)

    notifier.send(
        f"🤖 <b>Forex Bot v4.1 Started</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 News Momentum mode: <b>ACTIVE</b>\n"
        f"📊 Technical mode: <b>ACTIVE</b>\n"
        f"🔍 {len(FOREX_PAIRS)} pairs monitored\n"
        f"🛡️ News cooldown: <b>30 min</b> (flip protection)\n"
        f"<i>News break → 60s scan. Normal → 60min scan.</i>"
    )

    last_normal_scan = datetime.now(timezone.utc) - timedelta(hours=1)

    while True:
        try:
            now_utc = datetime.now(timezone.utc)

            # ── NEWS MODE ─────────────────────────────────────────────────
            news_active, news_info = _is_news_window_active()

            if news_active:
                print(f"\n  📰 NEWS WINDOW ACTIVE: {news_info}")
                _scan(label="News Momentum Scan", is_news_scan=True)
                print(f"  ⏰ Next news scan in {NEWS_SCAN_INTERVAL_SEC}s...")
                time.sleep(NEWS_SCAN_INTERVAL_SEC)

            else:
                # ── NORMAL MODE ───────────────────────────────────────────
                elapsed_min = (now_utc - last_normal_scan).total_seconds() / 60

                if elapsed_min >= NORMAL_SCAN_INTERVAL_MIN:
                    _scan(label="Hourly Cron Scan", is_news_scan=False)
                    last_normal_scan = now_utc
                    next_time = (now_utc + timedelta(minutes=NORMAL_SCAN_INTERVAL_MIN)).strftime("%H:%M UTC")
                    print(f"  ⏰ Next normal scan at {next_time}")
                else:
                    remaining = int(NORMAL_SCAN_INTERVAL_MIN - elapsed_min)
                    print(f"  💤 Normal mode — next scan in {remaining} min  |  "
                          f"{now_utc.strftime('%H:%M UTC')}")

                # News check: 30s (cached data only — API calls නෑ)
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