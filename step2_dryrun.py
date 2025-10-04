import requests, warnings, json
from datetime import date

warnings.filterwarnings("ignore")

BASE_URL = "https://gamma-api.polymarket.com/markets"

def fetch_today_cfb_markets(tag_id=100351, limit=500):
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

    # Only keep slugs starting with "cfb" and ending with today's date
    return [m for m in markets if (m.get("slug") or "").startswith("cfb") 
            and (m.get("slug") or "").endswith(today)]


if __name__ == "__main__":
    contests = fetch_today_cfb_markets()
    print(f"Found {len(contests)} CFB contests today\n")

    for i, m in enumerate(contests, start=1):
        print("=" * 80)
        print(f"[{i}] FULL MARKET DUMP:\n")
        print(json.dumps(m, indent=2))
        print()

