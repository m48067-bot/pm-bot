import requests, json
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL_EVENTS = "https://gamma-api.polymarket.com/events"
today = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")

r = requests.get(BASE_URL_EVENTS, params={"tag_id": 450, "closed": "false", "limit": 500}, verify=False)
r.raise_for_status()

data = r.json()
events = data["data"] if isinstance(data, dict) and "data" in data else data
print(f"Found {len(events)} raw NFL events\n")

for ev in events:
    slug = ev.get("slug")
    print(f"{slug} | live={ev.get('live')} | ended={ev.get('ended')} | period={ev.get('period')} | elapsed={ev.get('elapsed')} | score={ev.get('score')}")
