import requests, json

r = requests.get("https://data-api.polymarket.com/markets?limit=2", timeout=15)
print("Status:", r.status_code)
j = r.json()
print("Markets returned:", len(j.get("data", [])))
if j.get("data"):
    first = j["data"][0]
    print(json.dumps({"question": first.get("question"), "slug": first.get("slug")}, indent=2))
