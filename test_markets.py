import requests, warnings
from datetime import date

warnings.filterwarnings("ignore")

def fetch_mlb_markets(tag_id=100381, limit=250):
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": limit, "closed": "false", "tag_id": tag_id}
    r = requests.get(url, params=params, timeout=20, verify=False)
    r.raise_for_status()
    data = r.json()
    return data["data"] if isinstance(data, dict) else data

if __name__ == "__main__":
    today = date.today().strftime("%Y-%m-%d")  # e.g. "2025-09-27"
    mlb_markets = fetch_mlb_markets(limit=250)

    filtered = []
    for m in mlb_markets:
        slug = m.get("slug") or ""
        if not (slug.startswith("mlb") and slug.endswith(today)):
            continue  # skip non-today MLB games

        events = m.get("events", [])
        for ev in events:
            if ev.get("live") and ev.get("period") and "9th" not in ev["period"]:
                filtered.append((m, ev))

    print(f"Found {len(filtered)} live MLB contests (today, not in 9th inning)\n")

    for i, (m, ev) in enumerate(filtered, start=1):
        print("=" * 60)
        print(f"[{i}] {m.get('question')}")
        print(f"Slug: {m.get('slug')}")
        print(f"Condition ID: {m.get('conditionId')}")
        print(f"Live: {ev.get('live')}")
        print(f"Period: {ev.get('period')}")
        print(f"Score: {ev.get('score')}")
        print(f"Start Time: {ev.get('startTime')}")
        print()

