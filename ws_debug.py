import json
import os
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

ENTRY_TRIGGER = 0.86   # when bid crosses this, submit buy
ENTRY_PRICE   = 0.90   # limit buy price
STOP_TRIGGER  = 0.80   # when bid drops to this, submit sell
STOP_PRICE    = 0.80   # limit sell price
SIZE          = 5      # shares per trade

# ================= GLOBALS =================

current_slug = None
yes_token = None
no_token = None

prev_bid = {}
current_position_token = None
position_size = 0
entry_submitted_this_market = False
last_tick_time = time.time()
last_pos_log_time = 0

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
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    event = r.json()
    tokens_raw = event["markets"][0]["clobTokenIds"]
    tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw
    return tokens[0], tokens[1]

# ================= POSITION POLLER =================

def poll_positions_loop():
    global current_position_token, position_size
    global entry_submitted_this_market, prev_bid, last_pos_log_time

    while True:
        try:
            response = requests.get(
                f"{DATA_API}/positions",
                params={"user": USER_ADDRESS, "sizeThreshold": 0},
                timeout=10,
            )
            positions = response.json()

            found = False
            for p in positions:
                if p.get("slug") == current_slug and float(p.get("size", 0)) > 0:
                    found = True
                    current_position_token = p.get("asset")
                    position_size = float(p.get("size"))

                    # Only log position every 30 seconds
                    now = time.time()
                    if now - last_pos_log_time >= 30:
                        print(f"[POS] {current_slug} | size={position_size} | avg={p.get('avgPrice')} | cur={p.get('curprice')}")
                        last_pos_log_time = now
                    break

            if not found:
                if current_position_token is not None:
                    prev_bid = {}
                    entry_submitted_this_market = False
                    print("[POS] Position closed — ready to re-enter")

                current_position_token = None
                position_size = 0

        except Exception as e:
            print(f"[POS ERR] {e}")

        time.sleep(2)

# ================= MARKET SWITCH =================

def switch_market(ws, slug):
    global current_slug, yes_token, no_token
    global prev_bid, entry_submitted_this_market
    global current_position_token, position_size

    try:
        yes_token, no_token = fetch_tokens(slug)
    except Exception as e:
        print(f"[SWITCH ERR] Could not fetch tokens for {slug}: {e}")
        return

    ws.send(json.dumps({
        "assets_ids": [yes_token, no_token],
        "operation": "subscribe"
    }))

    current_slug = slug
    prev_bid = {}
    entry_submitted_this_market = False
    current_position_token = None
    position_size = 0

    print(f"\n{'='*40}")
    print(f"MARKET: {slug}")
    print(f"{'='*40}")

# ================= MARKET HANDLER =================

def on_market_open(ws):
    switch_market(ws, get_current_slug())

def on_market_message(ws, message):
    global prev_bid, entry_submitted_this_market
    global last_tick_time

    try:
        data = json.loads(message)

        if not isinstance(data, dict) or data.get("event_type") != "book":
            return

        last_tick_time = time.time()

        # Switch to next market near boundary
        if seconds_to_next_boundary() <= 5:
            next_slug = get_next_slug()
            if next_slug != current_slug:
                switch_market(ws, next_slug)
            return

        asset = data.get("asset_id")
        bids = sorted(data.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
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
            and old < ENTRY_TRIGGER
            and best_bid >= ENTRY_TRIGGER
        ):
            side_label = "YES" if asset == yes_token else "NO"
            print(f"\n[ENTRY] {side_label} bid crossed {ENTRY_TRIGGER} ({old:.2f} -> {best_bid:.2f})")
            print(f"[ENTRY] Buying {SIZE} shares @ {ENTRY_PRICE}")

            try:
                client.create_and_post_order(
                    OrderArgs(
                        token_id=asset,
                        price=ENTRY_PRICE,
                        size=SIZE,
                        side=BUY,
                    )
                )
                entry_submitted_this_market = True
            except Exception as e:
                print(f"[ENTRY ERR] {e}")

        # ================= STOP =================
        if (
            current_position_token is not None
            and asset == current_position_token
            and old is not None
            and old > STOP_TRIGGER
            and best_bid <= STOP_TRIGGER
        ):
            side_label = "YES" if asset == yes_token else "NO"
            print(f"\n[STOP] {side_label} bid dropped to {best_bid:.2f} (trigger={STOP_TRIGGER})")
            print(f"[STOP] Selling {position_size} shares @ {STOP_PRICE}")

            try:
                client.create_and_post_order(
                    OrderArgs(
                        token_id=current_position_token,
                        price=STOP_PRICE,
                        size=position_size,
                        side=SELL,
                    )
                )
            except Exception as e:
                print(f"[STOP ERR] {e}")

        prev_bid[asset] = best_bid

    except Exception as e:
        print(f"[MSG ERR] {e}")

# ================= START =================

def start_trading_bot():
    print("Trading bot started")
    print(f"  Entry: trigger={ENTRY_TRIGGER}, price={ENTRY_PRICE}")
    print(f"  Stop:  trigger={STOP_TRIGGER}, price={STOP_PRICE}")
    print(f"  Size:  {SIZE} shares")

    threading.Thread(target=poll_positions_loop, daemon=True).start()

    def watchdog():
        while True:
            if time.time() - last_tick_time > 60:
                print("[WATCHDOG] No data for 60s — restarting process")
                os._exit(1)
            time.sleep(10)

    threading.Thread(target=watchdog, daemon=True).start()

    while True:
        try:
            print("Connecting to websocket...")
            market_ws = WebSocketApp(
                WS_MARKET,
                on_open=on_market_open,
                on_message=on_market_message,
                on_close=lambda ws, code, msg: print(f"[WS CLOSED] {code} {msg}"),
                on_error=lambda ws, err: print(f"[WS ERROR] {err}"),
            )
            market_ws.run_forever(ping_interval=20)
            print("Websocket disconnected — reconnecting in 3s...")
        except Exception as e:
            print(f"[WS CRASH] {e}")
        time.sleep(3)
