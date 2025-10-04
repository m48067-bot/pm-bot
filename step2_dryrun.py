import requests, warnings, json
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"


def is_clutch_event(ev):
    """Return True if the event is in Q4/4th/4Q, <=5:00 elapsed, and within 6 points."""
    period = (ev.get("period") or "").lower()
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
    """Require bestBid between 0.05 and 0.95."""
    try:
        best_bid = float(market.get("bestBid", 0))
    except Exception:
        return False
    return 0.05 <= best_bid <= 0.95


def fetch_today_live_cfb_markets(tag_id=100351, limit=500):
    """Fetch today's live CFB contests meeting clutch-game filters."""
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
        if not (slug.startswith("cfb") and slug.endswith(today)):
            continue
        if not has_reasonable_spread(m):
            continue
        for ev in m.get("events", []):
            if ev.get("live") and is_clutch_event(ev):
                filtered.append((m, ev))
                break  # one qualifying event is enough
    return filtered


if __name__ == "__main__":
    contests = fetch_today_live_cfb_markets()
    print(f"Found {len(contests)} live CFB clutch contests today\n")

    for i, (m, ev) in enumerate(contests, start=1):
        print("=" * 80)
        print(f"[{i}] MARKET:\n")
        print(f"Question: {m.get('question')}")
        print(f"Slug: {m.get('slug')}")
        print(f"Score: {ev.get('score')}")
        print(f"Period: {ev.get('period')}")
        print(f"Elapsed: {ev.get('elapsed')}")
        print(f"bestBid: {m.get('bestBid')}")
        print(f"Liquidity: {m.get('liquidity')}")
        print()
