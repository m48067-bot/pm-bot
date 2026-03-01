import os
import json
import time
import threading
import requests
import pandas as pd
from websocket import WebSocketApp

import boto3

s3 = boto3.client("s3")
BUCKET = "pm-btc-data"   # replace if bucket name differs

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

lock = threading.Lock()
state = {}

# ================= TIME =================

def get_boundary(ts=None):
    if ts is None:
        ts = int(time.time())
    return ts - (ts % 300)

def get_slug(ts):
    return f"btc-updown-5m-{ts}"

# ================= TOKEN FETCH =================

def fetch_tokens(slug):
    url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
    r = requests.get(url)
    event = r.json()
    tokens_raw = event["markets"][0]["clobTokenIds"]
    tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw
    return tokens[0], tokens[1]

# ================= SUBSCRIBE MANAGEMENT =================

def subscribe_slug(ws, ts):
    slug = get_slug(ts)

    if slug in state:
        return

    try:
        yes, no = fetch_tokens(slug)
    except Exception as e:
        print("Token fetch error:", e)
        return

    state[slug] = {
        "slug_ts": ts,
        "yes_token": yes,
        "no_token": no,
        "yes_mid": 0,
        "no_mid": 0,
        "rows": [],
    }

    ws.send(json.dumps({
        "assets_ids": [yes, no],
        "operation": "subscribe"
    }))

    print("Subscribed:", slug)

# ================= SNAPSHOT LOOP =================

def snapshot_loop(ws):
    next_tick = time.time()

    while True:
        next_tick += 1
        sleep_time = next_tick - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

        now = int(time.time())
        current_boundary = get_boundary()
        next_boundary = current_boundary + 300

        with lock:

            # Ensure current + next always subscribed
            subscribe_slug(ws, current_boundary)
            subscribe_slug(ws, next_boundary)

            for slug in list(state.keys()):
                s = state[slug]
                rel = now - s["slug_ts"]

                # Collect -10 to 299
                if -10 <= rel <= 299:
                    s["rows"].append({
                        "slug": slug,
                        "relative_second": rel,
                        "utc_timestamp": now,
                        "yes_mid": s["yes_mid"],
                        "no_mid": s["no_mid"],
                    })

                # Write + cleanup
                if rel > 299:
                    write_parquet(slug, s["rows"])
                    del state[slug]

# ================= PARQUET =================

def write_parquet(slug, rows):
    if not rows:
        return

    df = pd.DataFrame(rows)
    local_path = os.path.join(DATA_DIR, f"{slug}.parquet")
    df.to_parquet(local_path, index=False)

    # Upload to S3
    s3.upload_file(local_path, BUCKET, f"{slug}.parquet")

    print(f"Saved & uploaded {slug} ({len(df)} rows)")

# ================= WEBSOCKET =================

def on_open(ws):
    print("WebSocket connected")

def on_message(ws, message):
    try:
        data = json.loads(message)

        if isinstance(data, list):
            return
        if data.get("event_type") != "book":
            return

        asset = data.get("asset_id")
        bids = sorted(data.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
        asks = sorted(data.get("asks", []), key=lambda x: float(x["price"]))

        if not bids or not asks:
            return

        bid = float(bids[0]["price"])
        ask = float(asks[0]["price"])
        mid = (bid + ask) / 2

        with lock:
            for s in state.values():
                if asset == s["yes_token"]:
                    s["yes_mid"] = mid
                elif asset == s["no_token"]:
                    s["no_mid"] = mid

    except Exception as e:
        print("WS error:", e)

# ================= MAIN =================

def start():
    ws = WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message
    )

    threading.Thread(target=snapshot_loop, args=(ws,), daemon=True).start()

    ws.run_forever(ping_interval=20)

if __name__ == "__main__":
    start()