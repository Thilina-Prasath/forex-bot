"""
cron_run.py — Hourly cron scan + News Momentum real-time watcher + AUTO TRADING
================================================================================
Mode 1 (Normal):   සෑම පැය 1 කට scan කරයි — Telegram වෙත පමණක් යවයි (No Auto-Trade)
Mode 2 (News):     News window open වූ විගස විනාඩි 1 කට scan කරයි.
                   6/6 Score එකක් ආවොත් පමණක් MT5 Auto-Trade කරයි + Telegram යවයි.
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

# Candle intervals
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

NEWS_SIGNAL_COOLDOWN_MIN  = 30    # Telegram වෙත එකම සිග්නල් එක නැවත යැවීම වැළැක්වීමේ කාලය
NORMAL_SIGNAL_COOLDOWN_H  = 1     

AUTO_TRADE_COOLDOWN_MIN   = 15    # එකම Pair එකට නැවත Auto-Trade වීම වැළැක්වීමේ තර්කණය (15 Min Lock)

# ── MT5 Credentials ───────────────────────────────────────────────────────────
MT5_LOGIN    = 336414528
MT5_PASSWORD = "Tp#@76502003"
MT5_SERVER   = "XMGlobal-MT5 9"

fetcher  = DataFetcher()
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

_news_last_sent:   dict[str, datetime] = {}
_normal_last_sent: dict[str, datetime] = {}
_last_auto_trade:  dict[str, datetime] = {} # Auto-trade Tracking Memory


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


# ── Auto Trading Execution Engine ─────────────────────────────────────────────
def execute_trade(symbol: str, direction: str, sl: float, tp: float) -> bool:
    """6/6 News signals සඳහා පමණක් MT5 Order දමන ශ්‍රිතය"""
    
    now = datetime.now(timezone.utc)
    last_trade = _last_auto_trade.get(symbol)

    # ආරක්ෂිත 15-Minute Cooldown පරීක්ෂාව
    if last_trade and (now - last_trade).total_seconds() < (AUTO_TRADE_COOLDOWN_MIN * 60):
        rem = int(AUTO_TRADE_COOLDOWN_MIN - ((now - last_trade).total_seconds() / 60))
        print(f"     🛡️  Trade Blocked for {symbol} (15m Cooldown active: {rem}m left)")
        return False

    lot_size = 0.02 if symbol in ["GOLD", "BTCUSD", "XAUUSD"] else 0.05

    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"     ❌ Trade Failed: Tick data missing for {symbol}")
        return False
        
    price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": price,
        "sl": float(sl),           
        "tp": float(tp),           
        "deviation": 20, 
        "magic": 234000,
        "comment": "AutoNews_6/6",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(f"     🚀 Placing AUTO {direction} on {symbol} | Lot: {lot_size} | SL: {sl} | TP: {tp}")
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"     ❌ Trade Failed: {result.comment} (Code: {result.retcode})")
        return False
    else:
        _last_auto_trade[symbol] = now # ට්‍රේඩ් එක සාර්ථක නම් පමණක් වෙලාව සටහන් කරයි
        print(f"     💵 ✅ AUTO-TRADE SUCCESS! Ticket: {result.order}")
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
        score   = max(sig["buy_score"], sig["sell_score"]) # Display Bug Fixed
        is_news = sig.get("news_momentum", False)
        tag     = " 📰" if is_news else ""

        if d == "NEUTRAL":
            reason = sig["reasons"][0] if sig["reasons"] else "No signal"
            print(f"     → NEUTRAL | {s:3d}% | {score}/6  ⚪ Skipped  [{reason}]")
            continue

        # Basic Quality Filter
        if score < QUALITY_MIN_SCORE or s < QUALITY_MIN_STRENGTH:
            print(f"     → {d:7s} | {s:3d}% | {score}/6  ⚠️  Below quality threshold")
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

        # ── Signal Notification & Decision Engine ─────────────────────────────
        print(f"     → {d:7s} | {s:3d}% | {score}/6  ✅ SIGNAL{tag}")
        
        # 1. පියවර: වර්ග දෙකේම සිග්නල් Telegram වෙත අනිවාර්යයෙන්ම යවයි
        notifier.send_signal(sig)

        # 2. පියවර: Auto-Trade තීරණය (News scan එකක් + Score එක හරියටම 6/6 නම් පමණක් Execution කරයි)
        if is_news_scan and score >= 6:
            sl_val = sig.get("sl", 0.0)
            tp_val = sig.get("tp1", 0.0)  # TP1 භාවිත කරයි (ආරක්ෂිතම ලාභය සඳහා)
            execute_trade(name, d, sl_val, tp_val)
        elif is_news_scan and score < 6:
            print(f"     ℹ️  News Score {score}/6 (Auto-Trade requires 6/6) -> Telegram Only")
        else:
            print(f"     ℹ️  Normal Market Signal -> Telegram Only (Manual Trade)")

        if is_news_scan:
            _mark_news_sent(name)
        else:
            _mark_normal_sent(name, d)

        sent += 1
        time.sleep(1)

    print(f"{'═'*52}")
    print(f"  {'✅ ' + str(sent) + ' signal(s) processed.' if sent else '⚪ No strong signals this scan.'}")
    print(f"{'═'*52}\n")
    return sent


def run_monitor():
    print("--------------------------------------------------")
    print("  FOREX SIGNAL BOT v5.0 (AUTO-TRADE)              ")
    print("  News Momentum + Technical Signals               ")
    print("--------------------------------------------------")
    
    print("  🔌 Connecting to MT5...")
    if not mt5.initialize():
        print("  ❌ MT5 initialize() failed.")
        sys.exit(1)
        
    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if authorized:
        print(f"  ✅ MT5 Connected Successfully! (Account: {MT5_LOGIN})")
    else:
        print(f"  ❌ MT5 Login failed! Error Code: {mt5.last_error()}")
        sys.exit(1)
    
    print("─" * 52)
    print(f"  ⚙️  Normal scan     : every {NORMAL_SCAN_INTERVAL_MIN}m (Telegram Only)")
    print(f"  ⚙️  News scan       : every {NEWS_SCAN_INTERVAL_SEC}s (Auto-Trade on 6/6)")
    print(f"  ⚙️  Auto Lock       : {AUTO_TRADE_COOLDOWN_MIN} minutes per symbol")
    print(f"  ⚙️  Pairs           : {', '.join(FOREX_PAIRS.keys())}")
    print(f"\n  Press Ctrl+C to stop\n")
    print("─" * 52)

    notifier.send(
        f"🤖 <b>Forex Bot v5.0 (Smart Engine) Started</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 MT5 Connection: <b>SUCCESS</b>\n"
        f"📰 News Mode (Auto 6/6): <b>ACTIVE</b>\n"
        f"📊 Normal Mode (Telegram): <b>ACTIVE</b>\n"
        f"🛡️ Safety Lock: <b>15 Minutes</b>\n"
    )

    last_normal_scan = datetime.now(timezone.utc) - timedelta(hours=1)

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            news_active, news_info = _is_news_window_active()

            if news_active:
                print(f"\n  📰 NEWS WINDOW ACTIVE: {news_info}")
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
                else:
                    remaining = int(NORMAL_SCAN_INTERVAL_MIN - elapsed_min)
                    print(f"  💤 Normal mode — next scan in {remaining} min  |  "
                          f"{now_utc.strftime('%H:%M UTC')}")

                time.sleep(30)

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