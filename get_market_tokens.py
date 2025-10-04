# get_markets_by_category.py
import requests

BASE_URL = "https://clob.polymarket.com"

def fetch_all_markets(limit=200):
    """Fetch all markets across all pages."""
    url = f"{BASE_URL}/markets?limit={limit}"
    all_markets = []
    while url:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        all_markets.extend(data.get("data", []))

        cursor = data.get("next_cursor")
        if cursor:
            url = f"{BASE_URL}/markets?limit={limit}&cursor={cursor}"
        else:
            url = None
    return all_markets

def main():
    print("Fetching all markets...")
    markets = fetch_all_markets()
    print(f"Total markets fetched: {len(markets)}")

    print("\nBaseball-related markets:")
    for m in markets:
        question = m.get("question", "")
        category = m.get("category", "")
        if "baseball" in question.lower() or "mlb" in question.lower() or category.lower() == "sports":
            print(f"- {question}")
            print(f"  Slug: {m.get('slug')}")
            print(f"  Ends: {m.get('endDate')}")
            print(f"  Active: {m.get('active')}  Closed: {m.get('closed')}")
            print("")

if __name__ == "__main__":
    main()










