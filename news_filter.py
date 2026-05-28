import requests
from datetime import datetime, timezone
import time

# නිව්ස් දත්ත හැම තත්පරේම ගන්නේ නැතුව, පැයකට සැරයක් ගන්න Cache එකක්
_cached_news = None
_last_fetch = 0

def get_high_impact_news():
    global _cached_news, _last_fetch
    now = time.time()
    
    # විනාඩි 30කට සැරයක් අලුත් නිව්ස් දත්ත ලබා ගැනීම
    if _cached_news is None or (now - _last_fetch) > 1800:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            # Forex Factory හි සජීවී දත්ත API එක
            r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", headers=headers, timeout=10)
            if r.status_code == 200:
                _cached_news = r.json()
                _last_fetch = now
        except Exception as e:
            print(f"News fetch error: {e}")
            
    return _cached_news or []

def check_news_conflict(symbol, buffer_minutes=30):
    """
    අදාළ මුදල් ඒකකයට (Pair) ඉදිරි විනාඩි 30 ඇතුළත හෝ 
    පසුගිය විනාඩි 30 ඇතුළත ලොකු නිව්ස් එකක් තිබුණාද යන්න පරීක්ෂා කරයි.
    """
    news_data = get_high_impact_news()
    if not news_data:
        return False, ""
        
    # අදාළ මුදල් ඒකක දෙක වෙන් කරගැනීම (උදා: EURUSD -> EUR සහ USD)
    if symbol in ["GOLD", "XAUUSD", "BTCUSD"]:
        target_curs = ["USD"]
    else:
        target_curs = [symbol[:3], symbol[3:]]
    
    now_utc = datetime.now(timezone.utc)
    
    for item in news_data:
        # රතු පාට ෆෝල්ඩරයේ (High Impact) නිව්ස් පමණක් තේරීම
        if item.get("impact") == "High" and item.get("country") in target_curs:
            try:
                # නිව්ස් වෙලාව UTC වෙලාවට හැරවීම
                dt_str = item.get("date")
                news_dt = datetime.fromisoformat(dt_str).astimezone(timezone.utc)
                
                # දැනට තියෙන වෙලාව සහ නිව්ස් වෙලාව අතර පරතරය විනාඩි වලින්
                diff_mins = abs((now_utc - news_dt).total_seconds()) / 60.0
                
                # විනාඩි 30 සීමාවේ නිව්ස් එකක් තිබේ නම්, එය Block කිරීම
                if diff_mins <= buffer_minutes:
                    return True, item.get("title")
            except:
                continue
                
    return False, ""