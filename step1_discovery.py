import requests, warnings
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_today_live_games(tag_id=100639, limit=250):
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
        if not (slug.startswith("nba") and slug.endswith(today)):
            continue

        for ev in m.get("events", []):
            if ev.get("live") and ev.get("period") and "9th" not in ev["period"] and "Final" not in ev["period"]:
                filtered.append((m, ev))

    return filtered

if __name__ == "__main__":
    games = fetch_today_live_games()
    print(f"Found {len(games)} live MLB games (today, not inn 9th or Final)\n")

    for i, (m, ev) in enumerate(games, start=1):
        print("=" * 60)
        print(f"[{i}] {m.get('question')}")
        print(f"Slug: {m.get('slug')}")
        print(f"Condition ID: {m.get('conditionId')}")
        print(f"clobTokenIds: {m.get('clobTokenIds')}")
        print(f"Live: {ev.get('live')}")
        print(f"Period: {ev.get('period')}")
        print(f"Score: {ev.get('score')}")
        print(f"Start Time: {ev.get('startTime')}")
        print()
