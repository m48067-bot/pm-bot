import requests, json

URL = "https://gamma-api.polymarket.com/markets?limit=3&closed=false&order=id&ascending=false"

r = requests.get(URL, timeout=15)
print("HTTP Status:", r.status_code)

# Gamma returns JSON; sometimes it's {"data":[...]} and sometimes it's a list
j = r.json()
data = j.get("data") if isinstance(j, dict) else j
if not isinstance(data, list):
    print("Unexpected payload:", type(j).__name__, j)
else:
    print("Markets returned:", len(data))
    if data:
        first = data[0]
        print(json.dumps({
            "question": first.get("question"),
            "slug": first.get("slug")
        }, indent=2))
