import requests, warnings, json
from datetime import datetime
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
BASE_URL_EVENTS = "https://gamma-api.polymarket.com/events"

# --- Pacific date helper ---
def pacific_today():
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

# --- Tail-risk (clutch) logic ---
def is_close_game(ev):
    """4th quarter (any time), score diff ≤8."""
    period = ev.get("period", "").lower()
    if period not in ("q4", "4th", "4q", "q3", "3q"):
        return False

    elapsed = ev.get("elapsed")
    if not elapsed:
        return False
    try:
        mins, secs = map(int, elapsed.split(":"))
    except Exception:
        return False

    # Within last 5 minutes of the quarter
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

# --- Fetch & print live NFL clutch contests ---
def test_nfl_clutch(tag_id=450, limit=500):
    today = pacific_today()
    print(f"Pacific date: {today}")

    try:
        r = requests.get(
            BASE_URL_EVENTS,
            params={"tag_id": tag_id, "closed": "false", "limit": limit},
            timeout=20,
            verify=False
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] API request failed: {e}")
        return

    data = r.json()
    events = data["data"] if isinstance(data, dict) else data
    if not events:
        print("[WARN] No data returned from API.")
        return

    found = []
    for ev in events:
        slug = (ev.get("slug") or "").lower()
        if not (slug.startswith("nfl-") and slug.endswith(today)):
            continue
        if not ev.get("live") or ev.get("ended"):
            continue

        # Moneyline only
        moneyline_markets = [
            m for m in ev.get("markets", [])
            if not any(k in m.get("question", "").lower()
                       for k in ["spread", "total", "over", "under", "o/u"])
        ]
        if not moneyline_markets:
            continue

        if not is_close_game(ev):
            continue

        found.append({
            "slug": ev.get("slug"),
            "score": ev.get("score"),
            "period": ev.get("period"),
            "elapsed": ev.get("elapsed"),
            "markets": [m.get("question") for m in moneyline_markets]
        })

    print(f"\nFound {len(found)} live NFL contests matching relaxed clutch conditions:\n")
    print(json.dumps(found, indent=2) if found else "None found.")

if __name__ == "__main__":
    test_nfl_clutch()

