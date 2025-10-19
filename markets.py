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


# --- Shared helper ---
def _fetch_today_games(tag_id, prefix, limit=500):
    today = pacific_today()
    r = requests.get(
        BASE_URL,
        params={"limit": limit, "closed": "false", "tag_id": tag_id},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    markets = _normalize_response(r)

    filtered = []
    for m in markets:
        slug = m.get("slug") or ""
        if slug.startswith(prefix) and slug.endswith(today):
            for ev in m.get("events", []):
                filtered.append((m, ev))
    return filtered


def is_close_game(ev):
    period = (ev.get("period") or "").lower()
    if period not in ("q4", "4th", "4q"):
        return False

    elapsed = ev.get("elapsed") or ""
    score = ev.get("score") or ""

    # Allow missing elapsed — just prioritize Q4 status
    mins = secs = 999
    try:
        if ":" in elapsed:
            mins, secs = map(int, elapsed.split(":"))
    except Exception:
        pass

    # Reject only if definitely early Q4 (more than ~7 min left)
    if mins > 7 or (mins == 7 and secs > 0):
        return False

    # Score diff logic
    if "-" not in score:
        return False
    try:
        a, b = map(int, score.split("-"))
    except Exception:
        return False

    return abs(a - b) <= 15


def fetch_clutch_games(tag_id, prefix):
    today = pacific_today()
    r = requests.get(
        BASE_URL,
        params={"limit": 500, "closed": "false", "tag_id": tag_id},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    markets = _normalize_response(r)

    clutch = []
    for m in markets:
        slug = m.get("slug") or ""
        if slug.startswith(prefix) and slug.endswith(today) and has_reasonable_spread(m):
            for ev in m.get("events", []):
                if ev.get("live") and is_close_game(ev):
                    clutch.append((m, ev))
                elif ev.get("live"):
                    # Debug visibility for why a contest was skipped
                    print(f"[SKIP] {m.get('question')} | Period={ev.get('period')} | Elapsed={ev.get('elapsed')} | Score={ev.get('score')}")
    return clutch


# --- Public interfaces ---
def fetch_live_games(tag_id_nfl=100639):
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


def fetch_live_nhl_games(tag_id_nhl=899):
    today = pacific_today()
    r = requests.get(
        BASE_URL,
        params={"limit": 500, "closed": "false", "tag_id": tag_id_nhl},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    markets = _normalize_response(r)

    games = []
    for m in markets:
        slug = (m.get("slug") or "").lower()
        if "nhl" in slug and slug.endswith(today):
            for ev in m.get("events", []):
                if ev.get("live"):
                    games.append((m, ev))
    return games


