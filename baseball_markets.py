# baseball_markets.py

import warnings
import requests

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_markets(limit=200):
    """Fetch active markets."""
    params = {"limit": limit, "closed": "false"}
    r = requests.get(BASE_URL, params=params, timeout=20, verify=False)
    r.raise_for_status()
    data = r.json()
    return data["data"] if isinstance(data, dict) else data

def filter_baseball(markets):
    """Filter contests that look like baseball (MLB, baseball in slug/question)."""
    results = []
    for m in markets:
        q = m.get("question", "").lower()
        slug = m.get("slug", "").lower()
        if "mlb" in slug or "baseball" in slug or "mlb" in q or "baseball" in q:
            results.append(m)
    return results

if __name__ == "__main__":
    markets = fetch_markets(limit=200)
    baseball = filter_baseball(markets)

    print(f"Found {len(baseball)} baseball contests\n")
    for m in baseball:
        print("=" * 60)
        print("Question:", m.get("question"))
        print("Slug:", m.get("slug"))
        print("Condition ID:", m.get("conditionId"))
        print("Status:", m.get("status"))
        print()
