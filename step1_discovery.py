import requests
import warnings
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_today_nba_games(tag_id=745, limit=500):
    """
    Broad NBA discovery for today's games:
    - Uses tag 745 (NBA)
    - Must end with today's date (YYYY-MM-DD)
    - Soft filters: no period/live restrictions
    """
    today = date.today().strftime("%Y-%m-%d")

    r = requests.get(
        BASE_URL,
        params={
            "limit": limit,
            "closed": "false",
            "tag_id": tag_id
        },
        timeout=20,
        verify=False
    )
    r.raise_for_status()
    data = r.json()
    markets = data["data"] if isinstance(data, dict) else data

    filtered = []
    for m in markets:
        slug = (m.get("slug") or "").lower()

        # Must contain "nba" and end with today's date
        if "nba" not in slug:
            continue
        if not slug.endswith(today):
            continue

        for ev in m.get("events", []):
            filtered.append((m, ev))

    return filtered


if __name__ == "__main__":
    games = fetch_today_nba_games()
    print(f"Found {len(games)} NBA-tag markets ending with today's date (tag 745)\n")

    for i, (m, ev) in enumerate(games, start=1):
        print("=" * 70)
        print(f"[{i}] {m.get('question')}")
        print(f"Slug: {m.get('slug')}")
        print(f"Condition ID: {m.get('conditionId')}")
        print(f"clobTokenIds: {m.get('clobTokenIds')}")
        print(f"Live: {ev.get('live')}")
        print(f"Period: {ev.get('period')}")
        print(f"Score: {ev.get('score')}")
        print(f"Start Time: {ev.get('startTime')}")
        print()
