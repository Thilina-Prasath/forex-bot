import sys
import os
from datetime import datetime, timezone, timedelta

from config            import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FOREX_PAIRS
from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier

# Signal quality filter
QUALITY_MIN_SCORE = 4

# ── Cooldown tracker (in-memory, resets on restart) ─────────────────────────
# Same pair + same direction = skip for COOLDOWN_HOURS
COOLDOWN_HOURS = 2
_last_sent: dict[str, datetime] = {}


def _is_in_cooldown(symbol: str, direction: str, now_utc: datetime) -> tuple[bool, int]:
    """Check if the pair+direction is in cooldown. Returns (is_cooldown, remaining_minutes)."""
    key = f"{symbol}_{direction}"
    last = _last_sent.get(key)
    if last and (now_utc - last) < timedelta(hours=COOLDOWN_HOURS):
        remaining = COOLDOWN_HOURS * 60 - int((now_utc - last).total_seconds() / 60)
        return True, remaining
    return False, 0


def main():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 Hourly Cron Scan  |  {now_str}")
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

        d = sig["direction"]
        # Score for display
        if d == "BUY":
            score = sig["buy_score"]
        elif d == "SELL":
            score = sig["sell_score"]
        else:
            score = max(sig["buy_score"], sig["sell_score"])
        strength = sig["strength"]

        # ── CASE 1: Off-session ──────────────────────────────────────────
        if not sig.get("session_ok", True):
            session_msg = sig.get("session", "Off-session")
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  ⏸️  {session_msg}")
            continue

        # ── CASE 2: News blocked ─────────────────────────────────────────
        if sig.get("news_blocked", False):
            reason = sig.get("reasons", ["🚨 News blocked"])[0]
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  {reason}")
            continue

        # ── CASE 3: Signal valid — check cooldown & send ─────────────────
        if d != "NEUTRAL" and score >= QUALITY_MIN_SCORE:
            now_utc = datetime.now(timezone.utc)
            in_cd, rem = _is_in_cooldown(sig["symbol"], d, now_utc)
            if in_cd:
                print(f"     → {d:7s} | {strength:3d}% | {score}/6  🔁 Cooldown {rem}min remaining")
                continue

            # Send signal
            notifier.send_signal(sig)
            _last_sent[f"{sig['symbol']}_{d}"] = now_utc
            sent_count += 1
            session_msg = sig.get("session", "")
            valid_until = sig.get("valid_until", "")
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  ✅ Sent!  [{session_msg}]  valid: {valid_until}")

        # ── CASE 4: NEUTRAL හෝ score low — block හේතුව print කරන්න ──────
        else:
            reasons = sig.get("reasons", [])
            if d != "NEUTRAL" and score >= QUALITY_MIN_SCORE:
                block_reason = "Unknown filter"
            elif d == "NEUTRAL":
                block_reason = reasons[0] if reasons else "No clear signal"
            else:
                block_reason = f"Score too low ({score}/{QUALITY_MIN_SCORE} required)"
            print(f"     → {d:7s} | {strength:3d}% | {score}/6  ⚪ Skipped  [{block_reason}]")

    print(f"\n{'═'*52}")
    if sent_count > 0:
        print(f"  ✅ {sent_count} signal(s) sent to Telegram!")
    else:
        print(f"  ⚪ No strong signals this scan.")
    print(f"{'═'*52}\n")


if __name__ == "__main__":
    main()