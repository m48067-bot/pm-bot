import requests, warnings, json
from datetime import datetime
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
BASE_URL = "https://gamma-api.polymarket.com/events"

def pacific_today():
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

def fetch_today_nfl_moneyline(tag_id=450, limit=500):
    """Fetch today's NFL events and keep only moneyline markets."""
    today = pacific_today()
    r = requests.get(
        BASE_URL,
        params={"tag_id": tag_id, "closed": "false", "limit": limit},
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    data = r.json()
    events = data["data"] if isinstance(data, dict) else data

    filtered = []
    for ev in events:
        slug = (ev.get("slug") or "").lower()
        if not (slug.startswith("nfl-") and slug.endswith(today)):
            continue

        # ✅ Keep only moneyline markets (no spread/total/over/under)
        moneyline_markets = [
            m for m in ev.get("markets", [])
            if not any(
                k in m.get("question", "").lower()
                for k in ["spread", "total", "over", "under", "o/u"]
            )
        ]

        if moneyline_markets:
            ev["markets"] = moneyline_markets  # replace with filtered markets only
            filtered.append(ev)

    print(f"Pacific date: {today}")
    print(f"Found {len(filtered)} NFL events with moneyline markets\n")
    print(json.dumps(filtered, indent=2))

if __name__ == "__main__":
    fetch_today_nfl_moneyline()
