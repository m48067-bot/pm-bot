import requests, warnings
from datetime import datetime
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
BASE_URL = "https://gamma-api.polymarket.com/markets"

# --- Pacific date helper ---
def pacific_today():
    """Return YYYY-MM-DD string in Pacific time."""
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

# --- Shared helper ---
def _fetch_today_games(tag_id, prefix, limit=500):
    today = pacific_today()
    r = requests.get(BASE_URL,
                     params={"limit": limit, "closed": "false", "tag_id": tag_id},
                     timeout=20, verify=False)
    r.raise_for_status()
    markets = r.json()["data"]
    filtered = []
    for m in markets:
        slug = m.get("slug") or ""
        if slug.startswith(prefix) and slug.endswith(today):
            for ev in m.get("events", []):
                filtered.append((m, ev))
    return filtered

# --- Game condition logic ---
def is_close_game(ev):
    period = ev.get("period", "").lower()
    if period not in ("q4", "4th", "4q"):
        return False
    elapsed = ev.get("elapsed")
    if not elapsed:
        return False
    try:
        mins, secs = map(int, elapsed.split(":"))
    except Exception:
        return False
    if mins > 6 or (mins == 6 and secs > 0):
        return False
    score = ev.get("score")
    if not score or "-" not in score:
        return False
    try:
        a, b = map(int, score.split("-"))
    except Exception:
        return False
    return abs(a - b) <= 6

def has_reasonable_spread(m):
    try:
        bid = float(m.get("bestBid", 0))
    except Exception:
        return False
    return 0.10 <= bid <= 0.90

# --- Clutch (NFL/CFB) fetcher ---
def fetch_clutch_games(tag_id, prefix):
    today = pacific_today()
    r = requests.get(BASE_URL,
                     params={"limit": 500, "closed": "false", "tag_id": tag_id},
                     timeout=20, verify=False)
    markets = r.json()["data"]
    clutch = []
    for m in markets:
        slug = m.get("slug") or ""
        if slug.startswith(prefix) and slug.endswith(today) and has_reasonable_spread(m):
            for ev in m.get("events", []):
                if ev.get("live") and is_close_game(ev):
                    clutch.append((m, ev))
    return clutch

# --- Public interfaces ---
def fetch_live_games(tag_id_nfl=100639):
    return fetch_clutch_games(tag_id_nfl, "nfl")

def fetch_live_nba_games(tag_id_nba=745):
    today = pacific_today()
    r = requests.get(BASE_URL,
                     params={"limit": 500, "closed": "false", "tag_id": tag_id_nba},
                     timeout=20, verify=False)
    markets = r.json()["data"]
    games = []
    for m in markets:
        slug = (m.get("slug") or "").lower()
        if "nba" in slug and slug.endswith(today):
            for ev in m.get("events", []):
                if ev.get("live"):
                    games.append((m, ev))
    return games

def fetch_live_nhl_games(tag_id_nhl=899):
    today = pacific_today()
    r = requests.get(BASE_URL,
                     params={"limit": 500, "closed": "false", "tag_id": tag_id_nhl},
                     timeout=20, verify=False)
    markets = r.json()["data"]
    games = []
    for m in markets:
        slug = (m.get("slug") or "").lower()
        if "nhl" in slug and slug.endswith(today):
            for ev in m.get("events", []):
                if ev.get("live"):
                    games.append((m, ev))
    return games





