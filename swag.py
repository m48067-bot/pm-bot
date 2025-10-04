import requests, warnings
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_today_games(tag_id=100381, limit=250):
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
        if slug.startswith("mlb") and slug.endswith(today):
            filtered.append(m)

    return filtered

if __name__ == "__main__":
    games = fetch_today_games()
    print(f"Found {len(games)} MLB games today\n")

    for i, m in enumerate(games, start=1):
        print("=" * 60)
        print(f"[{i}] {m.get('question')}")
        print(f"Slug: {m.get('slug')}")
        print(f"Condition ID: {m.get('conditionId')}")
        print(f"clobTokenIds: {m.get('clobTokenIds')}")
        print(f"Start Time: {m.get('startTime')}")
        print()
