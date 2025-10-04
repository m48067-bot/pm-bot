import requests, warnings
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

# --- generic fetcher ---
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


# --- NFL specific ---
def fetch_live_games(tag_id=100639, limit=250):
    """
    Fetch all live NFL contests happening today.
    """
    today_games = _fetch_today_games(tag_id, "nfl", limit)
    live = [(m, ev) for (m, ev) in today_games if ev.get("live")]
    return live


def is_close_game(ev):
    """
    NFL rule: Q4, <=5:00 elapsed, score diff <= 6
    """
    if ev.get("period") != "Q4":
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
    if abs(a - b) > 6:
        return False

    return True


def fetch_nfl_games_today(tag_id=100639, limit=250):
    """
    Fetch all NFL contests scheduled today (no live/close filters).
    """
    return [m for (m, ev) in _fetch_today_games(tag_id, "nfl", limit)]


# --- CFB specific ---
def fetch_cfb_games_today(tag_id=100351, limit=500):
    """
    Fetch all CFB contests scheduled today (no live/close filters).
    """
    return [m for (m, ev) in _fetch_today_games(tag_id, "cfb", limit)]


def is_cfb_clutch_game(ev):
    """
    CFB rule: 4th quarter, <=5:00 elapsed, score diff <= 6
    """
    if ev.get("period") != "4th":
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
    if abs(a - b) > 6:
        return False

    return True

def has_reasonable_spread(market):
    """
    Require bestBid to be between 0.05 and 0.95
    """
    try:
        best_bid = float(market.get("bestBid", 0))
    except Exception:
        return False
    return 0.05 <= best_bid <= 0.95


