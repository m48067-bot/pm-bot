import json
import time
import requests
import threading
from websocket import WebSocketApp
from initialize import client
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

# ================= CONFIG =================

WS_MARKET = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

DATA_API = "https://data-api.polymarket.com"
USER_ADDRESS = "0x7b9196eF079a8297BCCdd2Eb42c604255ED64Ae4"

ENTRY_TRIGGER = 0.52
ENTRY_PRICE   = 0.55

ENTRY_MODE = "same"  # "opposite" or "same"

STOP_TRIGGER = 0.27
STOP_PRICE   = 0.25

SIZE = 20

# ================= GLOBALS =================

current_slug = None
yes_token = None
no_token = None

prev_bid = {}
current_position_token = None
position_size = 0

entry_submitted_this_market = False

import os
last_tick_time = time.time()

# ================= TIME =================

def get_current_slug():
    now = int(time.time())
    rounded = now - (now % 300)
    return f"btc-updown-5m-{rounded}"

def get_next_slug():
    now = int(time.time())
    rounded = now - (now % 300)
    return f"btc-updown-5m-{rounded + 300}"

def seconds_to_next_boundary():
    now = int(time.time())
    rounded = now - (now % 300)
    return (rounded + 300) - now

# ================= TOKEN FETCH =================

def fetch_tokens(slug):
    url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
    r = requests.get(url)
    event = r.json()
    tokens_raw = event["markets"][0]["clobTokenIds"]
    tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw
    return tokens[0], tokens[1]

# ================= POSITION POLLER =================

def poll_positions_loop():
    global current_position_token, position_size
    global entry_submitted_this_market

    while True:
        try:
            url = f"{DATA_API}/positions"
            params = {
                "user": USER_ADDRESS,
                "sizeThreshold": 0
            }

            response = requests.get(url, params=params)
            positions = response.json()

            found = False

            for p in positions:
                if p.get("slug") == current_slug and float(p.get("size", 0)) > 0:
                    found = True
                    current_position_token = p.get("asset")
                    position_size = float(p.get("size"))

                    print("\n=== POSITION DETECTED ===")
                    print("Slug:", current_slug)
                    print("Token:", current_position_token)
                    print("Size:", position_size)
                    print("Avg:", p.get("avgPrice"))
                    print("Cur:", p.get("curprice"))
                    break

            if not found:
                if current_position_token is not None:
                    print("\n=== POSITION CLOSED ===")
                    print("Resetting entry logic — ready to trade again.")

                    entry_submitted_this_market = False

                current_position_token = None
                position_size = 0


        except Exception as e:
            print("Position poll error:", e)

        time.sleep(1)

# ================= MARKET SWITCH =================

def switch_market(ws, slug):
    global current_slug, yes_token, no_token
    global prev_bid, entry_submitted_this_market
    global current_position_token

    yes_token, no_token = fetch_tokens(slug)

    ws.send(json.dumps({
        "assets_ids": [yes_token, no_token],
        "operation": "subscribe"
    }))

    current_slug = slug
    prev_bid = {}
    entry_submitted_this_market = False
    current_position_token = None

    print("\n==============================")
    print(f"SWITCHED TO: {slug}")
    print("==============================")

# ================= MARKET HANDLER =================

def on_market_open(ws):
    switch_market(ws, get_current_slug())

def on_market_message(ws, message):
    global prev_bid, entry_submitted_this_market
    global last_tick_time

    last_tick_time = time.time()

    data = json.loads(message)

    if data.get("event_type") != "book":
        return

    # Early switch
    if seconds_to_next_boundary() <= 5:
        next_slug = get_next_slug()
        if next_slug != current_slug:
            switch_market(ws, next_slug)
        return

    asset = data.get("asset_id")

    bids = sorted(
        data.get("bids", []),
        key=lambda x: float(x["price"]),
        reverse=True
    )

    if not bids:
        return

    best_bid = float(bids[0]["price"])
    old = prev_bid.get(asset)

    # ================= ENTRY =================

    if (
        current_position_token is None
        and not entry_submitted_this_market
        and old is not None
        and seconds_to_next_boundary() > 30

    ):
        if old < ENTRY_TRIGGER and best_bid >= ENTRY_TRIGGER:

            if ENTRY_MODE == "opposite":
                if asset == yes_token:
                    opposite = no_token
                    print("\nYES triggered → buying NO")
                elif asset == no_token:
                    opposite = yes_token
                    print("\nNO triggered → buying YES")
                else:
                    return
                token_to_buy = opposite

            elif ENTRY_MODE == "same":
                if asset == yes_token:
                    print("\nYES triggered → buying YES")
                elif asset == no_token:
                    print("\nNO triggered → buying NO")
                else:
                    return
                token_to_buy = asset

            else:
                print("Invalid ENTRY_MODE")
                return

            print(f"ENTRY TRIGGER at {best_bid}")
            print(f"Submitting BUY @ {ENTRY_PRICE}")

            client.create_and_post_order(
                OrderArgs(
                    token_id=token_to_buy,
                    price=ENTRY_PRICE,
                    size=SIZE,
                    side=BUY,
                )
            )

            entry_submitted_this_market = True

    # ================= STOP =================

    if (
        current_position_token is not None
        and asset == current_position_token
        and old is not None
    ):
        if old > STOP_TRIGGER and best_bid <= STOP_TRIGGER:

            client.create_and_post_order(
                OrderArgs(
                    token_id=current_position_token,
                    price=STOP_PRICE,
                    size=position_size,
                    side=SELL,
                )
            )

    prev_bid[asset] = best_bid

# ================= START =================

def start_trading_bot():
    print("Trading bot started.")

    threading.Thread(target=poll_positions_loop, daemon=True).start()

    def watchdog():
        global last_tick_time
        while True:
            if time.time() - last_tick_time > 60:
                print("No market data for 60 seconds. Restarting process.")
                os._exit(1)
            time.sleep(10)

    threading.Thread(target=watchdog, daemon=True).start()

    while True:
        try:
            print("Connecting to market websocket...")

            market_ws = WebSocketApp(
                WS_MARKET,
                on_open=on_market_open,
                on_message=on_market_message,
                on_close=lambda ws, code, msg: print(f"Websocket closed: {code} {msg}"),
                on_error=lambda ws, err: print(f"Websocket error: {err}")
            )

            market_ws.run_forever(ping_interval=20)

            print("Websocket returned. Reconnecting...")

        except Exception as e:
            print("Websocket crash:", e)

        time.sleep(3)
