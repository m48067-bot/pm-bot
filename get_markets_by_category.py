# get_active_markets.py
import requests

BASE_URL = "https://gamma-api.polymarket.com/markets?limit=50"

def fetch_active_markets():
    try:
        r = requests.get(BASE_URL, timeout=20, verify=False)
        r.raise_for_status()
        markets = r.json()

        print(f"Fetched {len(markets)} markets")
        active = [m for m in markets if m.get("active") and not m.get("closed")]

        print(f"Active markets: {len(active)}\n")
        for m in active[:10]:  # just show 10
            print(f"- {m['question']}")
            print(f"  Slug: {m['slug']}")
            print(f"  Ends: {m['endDate']}")
            print("")
    except Exception as e:
        print("Request failed:", e)

if __name__ == "__main__":
    fetch_active_markets()










