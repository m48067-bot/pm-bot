import os
import ssl
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

# ---- TLS Adapter to force TLSv1.2 (needed for some environments) ----
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_version"] = ssl.PROTOCOL_TLSv1_2
        return super(TLSAdapter, self).init_poolmanager(*args, **kwargs)

# ---- Polymarket Gamma API Base ----
BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_live_markets(limit: int = 100):
    """
    Fetch only markets that are currently active/open.
    Returns a list of market dicts.
    """
    session = requests.Session()
    session.mount("https://", TLSAdapter())

    all_markets = []
    cursor = None

    while True:
        params = {"limit": limit, "closed": "false"}
        if cursor:
            params["cursor"] = cursor

        resp = session.get(BASE_URL, params=params, verify=False, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict):  # API sometimes wraps in dict
            markets = data.get("data", [])
            all_markets.extend(markets)
            cursor = data.get("next_cursor")
            if not cursor:
                break
        elif isinstance(data, list):  # Or just raw list
            all_markets.extend(data)
            break
        else:
            raise ValueError(f"Unexpected response format: {type(data)}")

    return all_markets

def show_sample_markets(markets, n: int = 10):
    """
    Pretty-print the first n markets with key info.
    """
    for m in markets[:n]:
        print("=" * 60)
        print("Market:", m.get("question", "No question"))
        print("Slug:", m.get("slug"))
        print("Condition ID:", m.get("conditionId"))
        print("Status:", m.get("status"))
        print("Tokens:")
        for t in m.get("tokens", []):
            print(f"   Outcome: {t.get('outcome')} | Token ID: {t.get('token_id')}")
        print()

def main():
    load_dotenv()
    print("Fetching active Polymarket contests...\n")
    try:
        live_markets = fetch_live_markets(limit=100)
        print(f"Got {len(live_markets)} live markets\n")
        show_sample_markets(live_markets, n=10)
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()







