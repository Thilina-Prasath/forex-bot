"""
cron_run.py — Hourly cron scan + News Momentum real-time watcher + AUTO TRADING
================================================================================
Mode 1 (Normal):   සෑම පැය 1 කට scan කරයි — Telegram වෙත පමණක් යවයි (No Auto-Trade)
Mode 2 (News):     News window open වූ විගස විනාඩි 1 කට scan කරයි.
                   6/6 Score + Valid SL/TP නම් පමණක් MT5 Auto-Trade කරයි.
                   එක news window එකකට MAX 1 trade (correlated pairs block)
"""

import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    FOREX_PAIRS,
)

NORMAL_INTERVAL = "1h"
NEWS_INTERVAL   = "5m"

from data_fetcher      import DataFetcher
from analyzer          import ForexAnalyzer
from telegram_notifier import TelegramNotifier
from news_filter       import check_news_conflict

# ── Settings ──────────────────────────────────────────────────────────────────
NORMAL_SCAN_INTERVAL_MIN  = 60
NEWS_SCAN_INTERVAL_SEC    = 60
QUALITY_MIN_SCORE         = 4
QUALITY_MIN_STRENGTH      = 60
NEWS_SIGNAL_COOLDOWN_MIN  = 30
NORMAL_SIGNAL_COOLDOWN_H  = 1
AUTO_TRADE_COOLDOWN_MIN   = 15

# ── NEW: Max 1 auto-trade per news window ──────────────────────────────────────
MAX_CONCURRENT_AUTO_TRADES = 1   # Same news window එකේදී 1 trade විතරයි

# ── MT5 Credentials ───────────────────────────────────────────────────────────
MT5_LOGIN    = 336414528
MT5_PASSWORD = "Tp#@76502003"
MT5_SERVER   = "XMGlobal-MT5 9"

fetcher  = DataFetcher()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

_news_last_sent:    dict[str, datetime] = {}
_normal_last_sent:  dict[str, datetime] = {}
_last_auto_trade:   dict[str, datetime] = {}

# NEW: current news window trade tracking
_current_news_window_start: datetime | None = None
_trades_in_current_window:  int = 0


def _news_cooldown_ok(pair: str) -> bool:
    last = _news_last_sent.get(pair)
    if last is None: return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= (NEWS_SIGNAL_COOLDOWN_MIN * 60)


def _normal_cooldown_ok(pair: str, direction: str) -> bool:
    key  = f"{pair}_{direction}"
    last = _normal_last_sent.get(key)
    if last is None: return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= (NORMAL_SIGNAL_COOLDOWN_H * 3600)


def _mark_news_sent(pair: str):
    _news_last_sent[pair] = datetime.now(timezone.utc)


def _mark_normal_sent(pair: str, direction: str):
    _normal_last_sent[f"{pair}_{direction}"] = datetime.now(timezone.utc)


def _is_news_window_active() -> tuple[bool, str]:
    for pair in FOREX_PAIRS:
        status, title = check_news_conflict(pair)
        if status == "NEWS_MOMENTUM":
            return True, f"{pair}: {title}"
    return False, ""


def _validate_sl_tp(symbol: str, direction: str, price: float,
                    sl: float, tp: float) -> tuple[bool, str]:
    """
    SL/TP valid දැයි check කරයි.
    0.0 / None / wrong-side values → invalid කියා return කරයි.
    """
    if not sl or not tp or sl == 0.0 or tp == 0.0:
        return False, "SL or TP is zero/missing"

    info = mt5.symbol_info(symbol)
    if info is None:
        return False, "Symbol info unavailable"

    min_stop = info.trade_stops_level * info.point
    if min_stop == 0:
        min_stop = info.point * 10  # fallback

    if direction == "BUY":
        if sl >= price:
            return False, f"BUY SL ({sl}) must be below price ({price:.5f})"
        if tp <= price:
            return False, f"BUY TP ({tp}) must be above price ({price:.5f})"
        if (price - sl) < min_stop:
            return False, f"SL too close to price (min distance: {min_stop:.5f})"
    else:  # SELL
        if sl <= price:
            return False, f"SELL SL ({sl}) must be above price ({price:.5f})"
        if tp >= price:
            return False, f"SELL TP ({tp}) must be below price ({price:.5f})"
        if (sl - price) < min_stop:
            return False, f"SL too close to price (min distance: {min_stop:.5f})"

    return True, "OK"


# ── Auto Trading Execution Engine ─────────────────────────────────────────────
def execute_trade(symbol: str, direction: str, sig: dict) -> bool:
    """
    6/6 News signals සඳහා පමණක් MT5 Order දමන ශ්‍රිතය.
    SL/TP valid නොවේ නම් trade skip කරයි.
    """
    global _trades_in_current_window

    now = datetime.now(timezone.utc)

    # ── 1. Per-pair cooldown ──────────────────────────────────────────────────
    last_trade = _last_auto_trade.get(symbol)
    if last_trade and (now - last_trade).total_seconds() < (AUTO_TRADE_COOLDOWN_MIN * 60):
        rem = int(AUTO_TRADE_COOLDOWN_MIN - ((now - last_trade).total_seconds() / 60))
        print(f"     🛡️  Trade Blocked for {symbol} (15m Cooldown: {rem}m left)")
        return False

    # ── 2. Max 1 trade per news window ────────────────────────────────────────
    if _trades_in_current_window >= MAX_CONCURRENT_AUTO_TRADES:
        print(f"     🚫 Trade Blocked: Max {MAX_CONCURRENT_AUTO_TRADES} auto-trade(s) per news window reached")
        notifier.send(
            f"🚫 <b>{symbol} {direction} — Auto-Trade Blocked</b>\n"
            f"Max 1 trade per news window already placed.\n"
            f"📊 Signal: {sig.get('strength', 0)}% | {sig.get('buy_score' if direction=='BUY' else 'sell_score', 0)}/6"
        )
        return False

    # ── 3. SL/TP extraction ───────────────────────────────────────────────────
    sl_val = sig.get("stop_loss")       # analyzer.py key: "stop_loss"
    tp_val = sig.get("take_profit1")    # analyzer.py key: "take_profit1"

    if not sl_val or not tp_val:
        print(f"     ❌ Trade Skipped: SL or TP not found in signal dict")
        notifier.send(
            f"⚠️ <b>{symbol} {direction} — Auto-Trade Skipped</b>\n"
            f"SL/TP signal data missing — cannot place safe trade."
        )
        return False

    sl_val = float(sl_val)
    tp_val = float(tp_val)

    # ── 4. MT5 tick & price ───────────────────────────────────────────────────
    lot_size = 0.02 if symbol in ["GOLD", "BTCUSD", "XAUUSD"] else 0.05
    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"     ❌ Trade Failed: Tick data missing for {symbol}")
        return False

    price      = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    # ── 5. SL/TP validation ───────────────────────────────────────────────────
    valid, reason = _validate_sl_tp(symbol, direction, price, sl_val, tp_val)
    if not valid:
        print(f"     ❌ Trade Skipped: Invalid SL/TP — {reason}")
        notifier.send(
            f"⚠️ <b>{symbol} {direction} — Auto-Trade Skipped</b>\n"
            f"Invalid SL/TP: {reason}"
        )
        return False

    # ── 6. Round to symbol digits ─────────────────────────────────────────────
    info   = mt5.symbol_info(symbol)
    digits = info.digits if info else 5
    sl_val = round(sl_val, digits)
    tp_val = round(tp_val, digits)

    # ── 7. Place order ────────────────────────────────────────────────────────
    request = {
        "action":      mt5.TRADE_ACTION_DEAL,
        "symbol":      symbol,
        "volume":      float(lot_size),
        "type":        order_type,
        "price":       price,
        "sl":          sl_val,
        "tp":          tp_val,
        "deviation":   20,
        "magic":       234000,
        "comment":     "AutoNews_6/6",
        "type_time":   mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(f"     🚀 Placing AUTO {direction} | {symbol} | Lot:{lot_size} | SL:{sl_val} | TP:{tp_val}")
    result = mt5.order_send(request)

    if result is None:
        print(f"     ❌ Trade Failed: order_send returned None. Error: {mt5.last_error()}")
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"     ❌ Trade Failed: {result.comment} (Code:{result.retcode})")
        return False

    # ── 8. Success ────────────────────────────────────────────────────────────
    _last_auto_trade[symbol]   = now
    _trades_in_current_window += 1
    print(f"     💵 ✅ AUTO-TRADE SUCCESS! Ticket:{result.order} | SL:{sl_val} | TP:{tp_val}")
    notifier.send(
        f"✅ <b>AUTO-TRADE PLACED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 {symbol} — {direction}\n"
        f"📥 Entry : {price}\n"
        f"🛑 SL    : {sl_val}\n"
        f"🎯 TP    : {tp_val}\n"
        f"🎫 Ticket: {result.order}"
    )
    return True


def _scan(label: str = "Scan", is_news_scan: bool = False) -> int:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'═'*52}")
    print(f"  🚀 {label}  |  {now_str}")
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
        score   = sig["buy_score"] if d == "BUY" else (sig["sell_score"] if d == "SELL" else max(sig["buy_score"], sig["sell_score"]))
        is_news = sig.get("news_momentum", False)
        tag     = " 📰" if is_news else ""

        if d == "NEUTRAL":
            reason = sig["reasons"][0] if sig["reasons"] else "No signal"
            print(f"     → NEUTRAL | {s:3d}% | {score}/6  ⚪ [{reason}]")
            continue

        if score < QUALITY_MIN_SCORE or s < QUALITY_MIN_STRENGTH:
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⚠️  Below threshold")
            continue

        if is_news_scan:
            if not _news_cooldown_ok(name):
                rem = int(NEWS_SIGNAL_COOLDOWN_MIN - ((datetime.now(timezone.utc) - _news_last_sent[name]).total_seconds() / 60))
                print(f"     → {d:7s} | {s:3d}% | {score}/6  ⏭️  News cooldown ({rem}min left)")
                continue
        else:
            if not _normal_cooldown_ok(name, d):
                print(f"     → {d:7s} | {s:3d}% | {score}/6  ⏭️  Cooldown active")
                continue

        print(f"     → {d:7s} | {s:3d}% | {score}/6  ✅ SIGNAL{tag}")

        # 1. Telegram always
        notifier.send_signal(sig)

        # 2. Auto-trade: news + 6/6 only
        if is_news_scan and score >= 6:
            execute_trade(name, d, sig)
        elif is_news_scan:
            print(f"     ℹ️  Score {score}/6 < 6 → Telegram Only")
        else:
            print(f"     ℹ️  Normal signal → Telegram Only (Manual Trade)")

        if is_news_scan:
            _mark_news_sent(name)
        else:
            _mark_normal_sent(name, d)

        sent += 1
        time.sleep(1)

    print(f"{'═'*52}")
    print(f"  {'✅ ' + str(sent) + ' signal(s).' if sent else '⚪ No strong signals.'}")
    print(f"{'═'*52}\n")
    return sent


def run_monitor():
    global _current_news_window_start, _trades_in_current_window

    print("--------------------------------------------------")
    print("  FOREX SIGNAL BOT v5.1 (AUTO-TRADE + SAFE)       ")
    print("  Max 1 Trade/Window | SL/TP Validated            ")
    print("--------------------------------------------------")

    print("  🔌 Connecting to MT5...")
    if not mt5.initialize():
        print("  ❌ MT5 initialize() failed.")
        sys.exit(1)

    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if authorized:
        print(f"  ✅ MT5 Connected! (Account: {MT5_LOGIN})")
    else:
        print(f"  ❌ MT5 Login failed! Error: {mt5.last_error()}")
        sys.exit(1)

    print("─" * 52)
    print(f"  ⚙️  Normal scan   : every {NORMAL_SCAN_INTERVAL_MIN}m (Telegram Only)")
    print(f"  ⚙️  News scan     : every {NEWS_SCAN_INTERVAL_SEC}s (Auto-Trade 6/6)")
    print(f"  ⚙️  Max trades    : {MAX_CONCURRENT_AUTO_TRADES} per news window")
    print(f"  ⚙️  Per-pair lock : {AUTO_TRADE_COOLDOWN_MIN} minutes")
    print(f"  ⚙️  SL/TP check  : ENABLED (skip if invalid)")
    print(f"  ⚙️  Pairs         : {', '.join(FOREX_PAIRS.keys())}")
    print(f"\n  Press Ctrl+C to stop\n")
    print("─" * 52)

    notifier.send(
        f"🤖 <b>Forex Bot v5.1 Started</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 MT5: <b>CONNECTED</b>\n"
        f"🛡️ Max 1 trade per news window: <b>ACTIVE</b>\n"
        f"✅ SL/TP validation: <b>ACTIVE</b>\n"
        f"📰 Auto-Trade (6/6 only): <b>ACTIVE</b>\n"
    )

    last_normal_scan    = datetime.now(timezone.utc) - timedelta(hours=1)
    prev_news_active    = False

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            news_active, news_info = _is_news_window_active()

            # ── News window transition tracking ───────────────────────────────
            if news_active and not prev_news_active:
                # New news window started → reset trade counter
                _current_news_window_start = now_utc
                _trades_in_current_window  = 0
                print(f"\n  📰 NEW NEWS WINDOW STARTED: {news_info}")
                print(f"  🔄 Trade counter reset → 0/{MAX_CONCURRENT_AUTO_TRADES}")

            if not news_active and prev_news_active:
                print(f"\n  ✅ News window closed. Trades placed: {_trades_in_current_window}")

            prev_news_active = news_active

            if news_active:
                print(f"\n  📰 NEWS WINDOW ACTIVE [{_trades_in_current_window}/{MAX_CONCURRENT_AUTO_TRADES} trades]: {news_info}")
                _scan(label="News Momentum Scan", is_news_scan=True)
                print(f"  ⏰ Next news scan in {NEWS_SCAN_INTERVAL_SEC}s...")
                time.sleep(NEWS_SCAN_INTERVAL_SEC)
            else:
                elapsed_min = (now_utc - last_normal_scan).total_seconds() / 60

                if elapsed_min >= NORMAL_SCAN_INTERVAL_MIN:
                    _scan(label="Hourly Cron Scan", is_news_scan=False)
                    last_normal_scan = now_utc
                    next_time = (now_utc + timedelta(minutes=NORMAL_SCAN_INTERVAL_MIN)).strftime("%H:%M UTC")
                    print(f"  ⏰ Next normal scan at {next_time}")
                    time.sleep(60)  # scan ට පස්සේ loop restart block
                else:
                    remaining = int(NORMAL_SCAN_INTERVAL_MIN - elapsed_min)
                    print(f"  💤 Next scan in {remaining}m | {now_utc.strftime('%H:%M UTC')}")
                    time.sleep(60)

        except KeyboardInterrupt:
            print("\n\n  🛑 Bot stopped.\n")
            notifier.send("🛑 <b>Forex Bot stopped.</b>")
            mt5.shutdown()
            break

        except Exception as e:
            print(f"\n  ❌ Unexpected error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run_monitor()
