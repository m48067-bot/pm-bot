import requests, warnings, json
from datetime import datetime, date
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
BASE_URL = "https://gamma-api.polymarket.com/markets"
BASE_URL_EVENTS = "https://gamma-api.polymarket.com/events"  # ✅ add for /events logic

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

# --- Helper: Fetch today's markets by tag (legacy use) ---
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
    """4th quarter, ≤5:00 remaining, score diff ≤6."""
    period = ev.get("period", "").lower()
    if period not in ("q4", "4th", "4q", "3q", "q3"):
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

    return abs(a - b) <= 8

def has_reasonable_spread(market):
    """Require bestBid between 0.10 and 0.90."""
    try:
        best_bid = float(market.get("bestBid", 0))
    except Exception:
        return False
    return 0.10 <= best_bid <= 0.90

# --- NEW: Fetch live NFL moneyline markets (via /events endpoint) ---
def fetch_live_nfl_markets(tag_id=450, limit=500):
    """
    Fetch today's live NFL moneyline markets (non-spread/total) from /events.
    Returns flattened markets for direct trading use.
    """
    today = pacific_today()
    r = requests.get(
        BASE_URL_EVENTS,
        params={"tag_id": tag_id, "closed": "false", "limit": limit},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    data = r.json()
    events = data["data"] if isinstance(data, dict) else data

    market_list = []
    for ev in events:
        slug = (ev.get("slug") or "").lower()
        if not (slug.startswith("nfl-") and slug.endswith(today)):
            continue
        if not ev.get("live") or ev.get("ended"):
            continue

        # ✅ Keep only moneyline markets (exclude spreads/totals)
        moneyline_markets = [
            m for m in ev.get("markets", [])
            if not any(
                k in m.get("question", "").lower()
                for k in ["spread", "total", "over", "under", "o/u"]
            )
        ]

        # ✅ Apply clutch logic (4Q, ≤5 min, ≤6 points)
        if not is_close_game(ev):
            continue

        for m in moneyline_markets:
            m["_event_meta"] = {
                "slug": ev.get("slug"),
                "score": ev.get("score"),
                "period": ev.get("period"),
                "elapsed": ev.get("elapsed"),
                "live": ev.get("live")
            }
            market_list.append(m)

    print(f"Pacific date: {today}")
    print(f"Found {len(market_list)} live NFL clutch moneyline markets\n")
    return market_list

# --- NBA Fetcher (unchanged) ---
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

# --- Public interface used by maine.py ---
def fetch_live_games():
    """Default interface used by maine.py for NFL clutch bot."""
    return fetch_live_nfl_markets()

