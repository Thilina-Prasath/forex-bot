"""
news_filter.py — High Impact News detection.
Forex Factory calendar API use කරලා
trade කිරීමට 30 min කලින් සහ 5 min පසු block කරනවා.
විනාඩි 5 සිට 30 දක්වා කාලය News Momentum (Pullback) සඳහා වෙන් කරයි.
"""

import requests
from datetime import datetime, timezone
import time

# ── Cache: 30 min වරක් API call ─────────────────────────────────────────────
_cached_news  = None
_last_fetch   = 0.0
CACHE_TTL_SEC = 1800  # 30 minutes


def get_high_impact_news() -> list:
    """
    Forex Factory calendar fetch කරනවා.
    30 min cache — API rate limit avoid කිරීම.
    """
    global _cached_news, _last_fetch
    now = time.time()

    if _cached_news is None or (now - _last_fetch) > CACHE_TTL_SEC:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:
                _cached_news = r.json()
                _last_fetch  = now
                print(f"  📰 News cache updated — {len(_cached_news)} events loaded.")
            else:
                print(f"  ⚠️  News API status {r.status_code} — signals unblocked.")
                _cached_news = []
                _last_fetch  = now

        except Exception as e:
            print(f"  ⚠️  News fetch error: {e} — signals unblocked.")
            _cached_news = []
            _last_fetch  = now

    return _cached_news or []


def check_news_conflict(symbol: str, pre_buffer: int = 30, post_buffer: int = 30, safe_delay: int = 5) -> tuple[str, str]:
    """
    Returns:
        ("BLOCKED", title)       — News is within -30 to +5 mins (Spread too high)
        ("NEWS_MOMENTUM", title) — News was 5 to 30 mins ago (Look for Pullbacks)
        ("CLEAR", "")            — No news conflict
    """
    news_data = get_high_impact_news()
    if not news_data:
        return "CLEAR", ""

    sym = symbol.upper()

    if sym in ("GOLD", "XAUUSD", "BTCUSD"):
        target_curs = {"USD"}
    elif len(sym) == 6:
        target_curs = {sym[:3], sym[3:]}
    else:
        target_curs = {sym}

    now_utc = datetime.now(timezone.utc)

    for item in news_data:
        if item.get("impact") != "High":
            continue

        country = (item.get("country") or "").upper()
        if country not in target_curs:
            continue

        dt_str = item.get("date") or item.get("datetime") or ""
        if not dt_str:
            continue

        try:
            news_dt = datetime.fromisoformat(dt_str).astimezone(timezone.utc)
        except ValueError:
            try:
                news_dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue

        # (+) means news is in the past, (-) means news is in the future
        time_since_news = (now_utc - news_dt).total_seconds() / 60.0

        if -pre_buffer <= time_since_news < safe_delay:
            # Block trades 30 mins before until 5 mins after
            title = item.get("title") or item.get("name") or "High Impact News"
            return "BLOCKED", f"{country} — {title}"
            
        elif safe_delay <= time_since_news <= post_buffer:
            # Open News Momentum Window (5 to 30 mins after news)
            title = item.get("title") or item.get("name") or "High Impact News"
            return "NEWS_MOMENTUM", f"{country} — {title}"

    return "CLEAR", ""