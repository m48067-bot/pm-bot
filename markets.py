import requests, warnings
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"


# --- Shared helper ---
def _fetch_today_games(tag_id, prefix, limit=500):
    """
    Fetch contests for today matching a given slug prefix (e.g., 'nfl' or 'cfb').
    """
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


# --- Game condition logic ---
def is_close_game(ev):
    """
    Game rule: Q4 or 4th, <=5:00 elapsed, score diff <= 6
    """
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
    if mins > 5 or (mins == 5 and secs > 0):
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
    Require bestBid between 0.05 and 0.95.
    """
    try:
        best_bid = float(market.get("bestBid", 0))
    except Exception:
        return False
    return 0.05 <= best_bid <= 0.95


# --- Combined live clutch fetcher ---
def fetch_clutch_games(tag_id, prefix):
    """
    Generic fetcher for live clutch games (NFL, CFB, etc.)
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


# --- Public interface used by maine.py ---
def fetch_live_games(tag_id_nfl=100639, tag_id_cfb=100351):
    """
    Fetch both NFL + CFB clutch contests using same filters.
    """
    nfl_clutch = fetch_clutch_games(tag_id_nfl, "nfl")
    cfb_clutch = fetch_clutch_games(tag_id_cfb, "cfb")
    return nfl_clutch + cfb_clutch


def fetch_nfl_games_today(tag_id=100639, limit=250):
    """
    Fetch all NFL contests scheduled today (no filters).
    """
    return [m for (m, ev) in _fetch_today_games(tag_id, "nfl", limit)]


def fetch_cfb_games_today(tag_id=100351, limit=500):
    """
    Fetch all CFB contests scheduled today (no filters).
    """
    return [m for (m, ev) in _fetch_today_games(tag_id, "cfb", limit)]




