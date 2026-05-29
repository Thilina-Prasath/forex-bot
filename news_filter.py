"""
news_filter.py — High Impact News detection.
Forex Factory calendar API use කරලා
trade කිරීමට 30 min කලින් සහ පසු block කරනවා.
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
                # ── Bug fix: fetch fail වුණොත් empty list cache කරනවා ──────
                # නැතිනම් හැම call ගානේම API hit කරනවා
                print(f"  ⚠️  News API status {r.status_code} — signals unblocked.")
                _cached_news = []
                _last_fetch  = now

        except Exception as e:
            print(f"  ⚠️  News fetch error: {e} — signals unblocked.")
            # ── Bug fix: exception හිදීත් cache set කරනවා ──────────────────
            _cached_news = []
            _last_fetch  = now

    return _cached_news or []


def check_news_conflict(symbol: str, buffer_minutes: int = 30) -> tuple[bool, str]:
    """
    Symbol ට අදාළ HIGH impact news ±buffer_minutes ඇතුළත තිඛෙනවාද?

    Returns:
        (True, news_title)  — blocked
        (False, "")         — clear to trade
    """
    news_data = get_high_impact_news()
    if not news_data:
        return False, ""

    sym = symbol.upper()

    # ── Target currencies for this symbol ───────────────────────────────────
    # GOLD/BTC = USD news affects them
    # Forex pairs = both currencies (e.g. EURUSD → EUR + USD)
    if sym in ("GOLD", "XAUUSD", "BTCUSD"):
        target_curs = {"USD"}
    elif len(sym) == 6:
        target_curs = {sym[:3], sym[3:]}
    else:
        target_curs = {sym}

    now_utc = datetime.now(timezone.utc)

    for item in news_data:
        # HIGH impact පමණක් — medium/low ignore
        if item.get("impact") != "High":
            continue

        # ── Bug fix: country field case-insensitive match ────────────────────
        country = (item.get("country") or "").upper()
        if country not in target_curs:
            continue

        # ── Date parse ───────────────────────────────────────────────────────
        dt_str = item.get("date") or item.get("datetime") or ""
        if not dt_str:
            continue

        try:
            # Handles ISO format: "2026-05-29T08:30:00-04:00"
            news_dt = datetime.fromisoformat(dt_str).astimezone(timezone.utc)
        except ValueError:
            # Fallback: try without timezone
            try:
                news_dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                continue

        diff_mins = abs((now_utc - news_dt).total_seconds()) / 60.0

        if diff_mins <= buffer_minutes:
            title = item.get("title") or item.get("name") or "High Impact News"
            return True, f"{country} — {title}"

    return False, ""