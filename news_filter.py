"""
news_filter.py — High Impact News detection.
Forex Factory calendar API use කරලා
නිව්ස් එකට පෙර විනාඩි 15 සහ පසු විනාඩි 1ක් පමණක් Block කරනවා (Spread ආරක්ෂාවට).
විනාඩි 1 සිට විනාඩි 30 දක්වා "News Momentum" වින්ඩෝවක් සක්‍රීය කරයි.
"""

import requests
from datetime import datetime, timezone
import time

_cached_news  = None
_last_fetch   = 0.0
CACHE_TTL_SEC = 1800  # 30 minutes

def get_high_impact_news() -> list:
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
            else:
                _cached_news = []
                _last_fetch  = now
        except Exception:
            _cached_news = []
            _last_fetch  = now

    return _cached_news or []

# ── වෙනස මෙතනයි (safe_delay: int = 1) ──────────────────────────────────────
def check_news_conflict(symbol: str, pre_buffer: int = 15, post_buffer: int = 30, safe_delay: int = 1) -> tuple[str, str]:
    """
    Returns:
        ("BLOCKED", title)       — අතිශය අවදානම් (නිව්ස් එකට පෙර විනාඩි 15 සිට පසු විනාඩි 1 දක්වා)
        ("NEWS_MOMENTUM", title) — Trend එක දිගටම යනවාදැයි බැලීමට අවසර (විනාඩි 1 සිට 30 දක්වා)
        ("CLEAR", "")            — සාමාන්‍ය වෙළඳපොළ
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

        time_since_news = (now_utc - news_dt).total_seconds() / 60.0

        if -pre_buffer <= time_since_news < safe_delay:
            title = item.get("title") or item.get("name") or "High Impact News"
            return "BLOCKED", f"{country} — {title}"
            
        elif safe_delay <= time_since_news <= post_buffer:
            title = item.get("title") or item.get("name") or "High Impact News"
            return "NEWS_MOMENTUM", f"{country} — {title}"

    return "CLEAR", ""