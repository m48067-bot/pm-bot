import requests
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo
import json

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def dump_full_nhl_json(tag_id=899, limit=500):
    """
    Pulls the complete raw JSON for NHL markets (tag 899) ending with today's
    date in Pacific Time. Prints the full object with no filtering.
    """
    pacific_today = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

    r = requests.get(
        BASE_URL,
        params={"limit": limit, "closed": "false", "tag_id": tag_id},
        timeout=30,
        verify=False
    )
    r.raise_for_status()
    data = r.json()

    # Filter by 'nhl' slug and today's Pacific date, but dump everything
    markets = data["data"] if isinstance(data, dict) else data
    filtered = []
    for m in markets:
        slug = (m.get("slug") or "").lower()
        if "nhl" in slug and slug.endswith(pacific_today):
            filtered.append(m)

    print(f"Pacific date: {pacific_today}")
    print(f"Dumping full JSON for {len(filtered)} NHL markets (tag {tag_id})...\n")

    print(json.dumps(filtered, indent=2))

if __name__ == "__main__":
    dump_full_nhl_json()

