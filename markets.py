import requests, warnings
from datetime import datetime
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
BASE_URL = "https://gamma-api.polymarket.com/markets"

# --- Pacific date helper ---
def pacific_today():
    """Return YYYY-MM-DD string in Pacific time."""
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

# --- Normalize Polymarket API response ---
def _normalize_response(r):
    """Ensure response is always a list of market dicts."""
    try:
        data = r.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        elif isinstance(data, list):
            return data
        else:
            print(f"[WARN] Unexpected API format: {type(data)}")
            return []
    except Exception as e:
        print(f"[ERROR] Could not parse JSON: {e}")
        return []

# --- Helper: Fetch today's markets by tag ---
def _fetch_today_games(tag_id, prefix, limit=500):
    today = date.today().strftime("%Y-%m-%d")
    r = requests.get(
        BASE_URL,
        params={"limit": limit, "closed": "false", "tag_id": tag_id},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    data = r.json()
    markets = data["data"] if isinstance(data, dict) else data

    filtered = []
    for m in markets:
        slug = m.get("slug") or ""
        if not (slug.startswith(prefix) and slug.endswith(today)):
            continue

        for ev in m.get("events", []):
            filtered.append((m, ev))
    return filtered

# --- Tail-risk logic ---
def is_close_game(ev):
    """
    Game rule: 4th quarter, ≤5:00 remaining, score diff ≤6.
    """
    period = ev.get("period", "").lower()
    if period not in ("q4", "4th", "4q", "1q"):
        return False

    elapsed = ev.get("elapsed")
    if not elapsed:
        return False

    try:
        mins, secs = map(int, elapsed.split(":"))
    except Exception:
        return False

    if mins > 14 or (mins == 5 and secs > 0):
        return False

    score = ev.get("score")
    if not score or "-" not in score:
        return False

    try:
        a, b = map(int, score.split("-"))
    except Exception:
        return False

    return abs(a - b) <= 6

def has_reasonable_spread(market):
    """
    Require bestBid between 0.10 and 0.90.
    """
    try:
        best_bid = float(market.get("bestBid", 0))
    except Exception:
        return False
    return 0.10 <= best_bid <= 0.90

# --- Main NFL fetcher ---
def fetch_clutch_games(tag_id, prefix):
    """
    Fetches all live NFL markets that meet tail-risk criteria.
    """
    today = date.today().strftime("%Y-%m-%d")
    r = requests.get(
        BASE_URL,
        params={"limit": 500, "closed": "false", "tag_id": tag_id},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    data = r.json()
    markets = data["data"] if isinstance(data, dict) else data

    clutch_markets = []
    for m in markets:
        slug = m.get("slug") or ""
        if not (slug.startswith(prefix) and slug.endswith(today)):
            continue
        if not has_reasonable_spread(m):
            continue
        for ev in m.get("events", []):
            if ev.get("live") and is_close_game(ev):
                clutch_markets.append((m, ev))

    return clutch_markets

def fetch_live_games(tag_id_nfl=100639):
    """
    Public interface used by maine.py — fetches only NFL tail-risk contests.
    """
    return fetch_clutch_games(tag_id_nfl, "nfl")

def fetch_live_nba_games(tag_id_nba=745):
    today = pacific_today()
    r = requests.get(
        BASE_URL,
        params={"limit": 500, "closed": "false", "tag_id": tag_id_nba},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    markets = _normalize_response(r)

    games = []
    for m in markets:
        slug = (m.get("slug") or "").lower()
        if "nba" in slug and slug.endswith(today):
            for ev in m.get("events", []):
                if ev.get("live"):
                    games.append((m, ev))
    return games


