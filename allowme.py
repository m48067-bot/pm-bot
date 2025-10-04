import requests
import warnings
from datetime import date
import json

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_today_live_games(tag_id=100639, limit=250):
    """
    Fetch live NFL contests happening today.
    Uses tag_id=100639 for NFL.
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
        if not (slug.startswith("nfl") and slug.endswith(today)):
            continue

        for ev in m.get("events", []):
            if ev.get("live"):
                filtered.append((m, ev))  # keep both market + event info

    return filtered


if __name__ == "__main__":
    games = fetch_today_live_games()
    print(f"Found {len(games)} live NFL games today\n")

    for i, (m, ev) in enumerate(games, start=1):
        print("=" * 100)
        print(f"[{i}] {m.get('question')}")
        print("\n--- Full Market JSON ---")
        print(json.dumps(m, indent=2))
        print("\n--- Full Event JSON ---")
        print(json.dumps(ev, indent=2))
        print("\n")

