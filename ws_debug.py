import json
import gzip
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

ENTRY_PRICE   = 0.60   # limit buy price
SIZE          = 6      # shares per trade
TRIGGER_PRICE = 0.52   # first side to hit this bid triggers entry
SL_TRIGGER    = 0.75   # stop loss: other side bid hits this
SL_PRICE      = 0.85   # stop loss: buy other side at this price
STOP_ARM      = 0.85   # arm stop when our side bid hits this (deep profit)
STOP_TRIGGER  = 0.40   # stop fires when OTHER side bid hits this
STOP_PRICE    = 0.45   # limit buy price for stop reversal
STOP_SIZE     = 12     # shares for stop reversal

# Late reversal detection (last 30s of prev contest)
REVERSAL_DEAD_THRESHOLD = 0.10  # side must have been at or below this
REVERSAL_JUMP_THRESHOLD = 0.30  # then jumps to this or above → reversal
REVERSAL_SIZE = 12              # shares to buy on reversal (6 cover + 6 long)

# Tiebreaker order when vote is tied
TIEBREAKER_ORDER = ["htx", "coinbase", "bitstamp", "bitfinex", "okx", "bybit", "cryptodotcom", "kraken"]
EXCHANGES = ["kraken", "coinbase", "bitstamp", "okx", "bitfinex", "bybit", "cryptodotcom", "htx"]

# ================= GLOBALS =================

current_slug = None
yes_token = None
no_token = None
active_ws = None
switch_lock = threading.Lock()
switched_early = False  # True once we switch to next contest before boundary

current_position_token = None
position_size = 0
entry_done = False
last_entry_side = None  # "YES" or "NO" — what we bought this contest
contest_hit_5c = False  # True if our side's bid hit ≤ 0.05 this contest

# Stop/reversal state
stop_armed = False      # True once our side hits STOP_ARM
stop_done = False       # True once stop has fired
sl_done = False         # True once stop-loss has fired

# Previous contest tracking (keep watching after early switch)
prev_yes_token = None
prev_no_token = None
prev_entry_side = None
prev_hit_5c = False
prev_slug = None
prev_yes_bid = None    # track prev contest book for reversal detection
prev_no_bid = None
prev_reversal_done = False  # True once reversal has fired
prev_sl_done = False   # True once prev contest SL has fired

# Streak tracking: flip strategy after 3 consecutive 5c hits
fade_mode = False  # True = fade the misprice signal, False = follow it
consecutive_losses = 0
LOSS_STREAK_FLIP = 3

last_tick_time = time.time()
last_pos_log_time = 0
last_heartbeat_time = 0
last_vote_log_time = 0
last_signal_log_time = 0
pos_miss_count = 0

latest_yes_bid = None
latest_no_bid = None

MIN_ORDER_SIZE = 5   # Polymarket minimum
POS_MISS_THRESHOLD = 3  # consecutive misses before declaring closed

# Exchange prices and strikes — each exchange has its own
ex_prices = {ex: None for ex in EXCHANGES}
ex_strikes = {ex: None for ex in EXCHANGES}
ex_ticks = {ex: 0 for ex in EXCHANGES}

# PM-Chainlink RTDS — the actual settlement feed
RTDS_WS = "wss://ws-live-data.polymarket.com"
pm_cl_price = None       # latest Chainlink price
pm_cl_strike = None      # locked at boundary tick (ts % 300 == 0)
pm_cl_strike_locked = False  # True once real boundary tick received this contest

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

# ================= EXCHANGE WS FEEDS =================

def start_kraken_ws():
    def on_open(ws):
        ws.send(json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": ["BTC/USD"]}}))
        ws.send(json.dumps({"method": "subscribe", "params": {"channel": "ticker", "symbol": ["BTC/USD"]}}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            ch = data.get("channel")
            if ch == "trade" and "data" in data:
                trades = data["data"]
                if trades:
                    ex_prices["kraken"] = float(trades[-1]["price"])
                    ex_ticks["kraken"] += 1
            elif ch == "ticker" and "data" in data:
                ex_prices["kraken"] = float(data["data"][0]["last"])
                ex_ticks["kraken"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://ws.kraken.com/v2", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_coinbase_ws():
    def on_open(ws):
        ws.send(json.dumps({"type": "subscribe", "channels": [{"name": "ticker", "product_ids": ["BTC-USD"]}]}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("type") == "ticker":
                ex_prices["coinbase"] = float(data["price"])
                ex_ticks["coinbase"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://ws-feed.exchange.coinbase.com", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_bitstamp_ws():
    def on_open(ws):
        ws.send(json.dumps({"event": "bts:subscribe", "data": {"channel": "live_trades_btcusd"}}))
        ws.send(json.dumps({"event": "bts:subscribe", "data": {"channel": "live_ticker_btcusd"}}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if isinstance(data, dict) and "data" in data:
                d = data["data"]
                if isinstance(d, dict):
                    p = d.get("price") or d.get("last_price")
                    if p is not None:
                        p = float(p)
                        if p > 1000:
                            ex_prices["bitstamp"] = p
                            ex_ticks["bitstamp"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://ws.bitstamp.net", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_okx_ws():
    def on_open(ws):
        ws.send(json.dumps({"op": "subscribe", "args": [
            {"channel": "trades", "instId": "BTC-USDT"},
            {"channel": "tickers", "instId": "BTC-USDT"},
        ]}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "data" in data and isinstance(data["data"], list):
                ch = data.get("arg", {}).get("channel")
                if ch == "trades":
                    ex_prices["okx"] = float(data["data"][-1]["px"])
                    ex_ticks["okx"] += 1
                elif ch == "tickers":
                    ex_prices["okx"] = float(data["data"][0]["last"])
                    ex_ticks["okx"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://ws.okx.com:8443/ws/v5/public", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_bitfinex_ws():
    chan_map = {}
    def on_open(ws):
        ws.send(json.dumps({"event": "subscribe", "channel": "trades", "symbol": "tBTCUSD"}))
        ws.send(json.dumps({"event": "subscribe", "channel": "ticker", "symbol": "tBTCUSD"}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if isinstance(data, dict) and data.get("event") == "subscribed":
                chan_map[data["chanId"]] = data["channel"]
                return
            if isinstance(data, list) and len(data) >= 2:
                chan_type = chan_map.get(data[0], "")
                if chan_type == "trades":
                    if data[1] in ("te", "tu") and isinstance(data[2], list):
                        ex_prices["bitfinex"] = float(data[2][3])
                        ex_ticks["bitfinex"] += 1
                    elif isinstance(data[1], list) and len(data[1]) > 0:
                        last_trade = data[1][-1] if isinstance(data[1][0], list) else data[1]
                        ex_prices["bitfinex"] = float(last_trade[3])
                        ex_ticks["bitfinex"] += 1
                elif chan_type == "ticker":
                    if isinstance(data[1], list) and len(data[1]) >= 7:
                        ex_prices["bitfinex"] = float(data[1][6])
                        ex_ticks["bitfinex"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://api-pub.bitfinex.com/ws/2", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_bybit_ws():
    def on_open(ws):
        ws.send(json.dumps({"op": "subscribe", "args": ["publicTrade.BTCUSDT", "tickers.BTCUSDT"]}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            topic = data.get("topic", "")
            if topic == "publicTrade.BTCUSDT" and "data" in data:
                trades = data["data"]
                if trades:
                    ex_prices["bybit"] = float(trades[-1]["p"])
                    ex_ticks["bybit"] += 1
            elif topic == "tickers.BTCUSDT" and "data" in data:
                ex_prices["bybit"] = float(data["data"]["lastPrice"])
                ex_ticks["bybit"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://stream.bybit.com/v5/public/spot", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_cryptodotcom_ws():
    def on_open(ws):
        ws.send(json.dumps({"id": 1, "method": "subscribe", "params": {"channels": ["trade.BTC_USD", "ticker.BTC_USD"]}}))
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "result" in data:
                result = data["result"]
                ch = result.get("channel", "")
                if "data" in result and result["data"]:
                    if "trade" in ch:
                        ex_prices["cryptodotcom"] = float(result["data"][-1]["p"])
                        ex_ticks["cryptodotcom"] += 1
                    elif "ticker" in ch:
                        item = result["data"][-1] if isinstance(result["data"], list) else result["data"]
                        if "a" in item:
                            ex_prices["cryptodotcom"] = float(item["a"])
                            ex_ticks["cryptodotcom"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://stream.crypto.com/exchange/v1/market", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

def start_htx_ws():
    def on_open(ws):
        ws.send(json.dumps({"sub": "market.btcusdt.trade.detail", "id": "htx1"}))
        ws.send(json.dumps({"sub": "market.btcusdt.ticker", "id": "htx2"}))
    def on_message(ws, message):
        try:
            if isinstance(message, bytes):
                message = gzip.decompress(message).decode("utf-8")
            data = json.loads(message)
            if "ping" in data:
                ws.send(json.dumps({"pong": data["ping"]}))
                return
            if "tick" in data:
                tick = data["tick"]
                if "data" in tick:
                    trades = tick["data"]
                    if trades:
                        ex_prices["htx"] = float(trades[-1]["price"])
                        ex_ticks["htx"] += 1
                elif "close" in tick:
                    ex_prices["htx"] = float(tick["close"])
                    ex_ticks["htx"] += 1
        except: pass
    while True:
        try:
            ws = WebSocketApp("wss://api.huobi.pro/ws", on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

# ================= PM-CHAINLINK RTDS FEED =================

def start_pm_chainlink_ws():
    """Polymarket's Chainlink BTC/USD — the actual settlement feed.
    When we see a tick at exactly ts % 300 == 0, that's the real strike."""
    global pm_cl_price, pm_cl_strike, pm_cl_strike_locked
    def on_open(ws):
        ws.send(json.dumps({
            "action": "subscribe",
            "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*",
                               "filters": "{\"symbol\":\"btc/usd\"}"}]
        }))
        def ping_loop():
            while True:
                try: ws.send("PING")
                except: break
                time.sleep(5)
        threading.Thread(target=ping_loop, daemon=True).start()
    def on_message(ws, message):
        global pm_cl_price, pm_cl_strike, pm_cl_strike_locked
        try:
            data = json.loads(message)
            if data.get("topic") != "crypto_prices_chainlink":
                return
            payload = data.get("payload", {})
            if payload.get("symbol") != "btc/usd" or "value" not in payload:
                return
            v = float(payload["value"])
            pm_cl_price = v
            # Boundary tick — lock in the real strike
            ts_sec = payload.get("timestamp", 0) // 1000
            if ts_sec > 0 and ts_sec % 300 == 0 and not pm_cl_strike_locked:
                pm_cl_strike = v
                pm_cl_strike_locked = True
                # Overwrite all exchange strikes with the real Chainlink strike
                for ex in EXCHANGES:
                    ex_strikes[ex] = v
                print(f"[STRIKE] Chainlink boundary tick: ${v:,.2f} @ ts={ts_sec}")
        except: pass
    while True:
        try:
            ws = WebSocketApp(RTDS_WS, on_open=on_open, on_message=on_message,
                on_error=lambda _w, _e: None, on_close=lambda _w, _c, _m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

# ================= STRIKE FETCHING =================

def fetch_all_strikes(contest_ts, slug):
    """Fetch real 5m candle opens from all exchanges. Retry until found or contest changes."""
    for attempt in range(30):
        if current_slug != slug:
            return
        threads = []
        fetchers = [
            ("kraken", _fetch_strike_kraken),
            ("coinbase", _fetch_strike_coinbase),
            ("bitstamp", _fetch_strike_bitstamp),
            ("okx", _fetch_strike_okx),
            ("bitfinex", _fetch_strike_bitfinex),
            ("bybit", _fetch_strike_bybit),
            ("cryptodotcom", _fetch_strike_cryptodotcom),
            ("htx", _fetch_strike_htx),
        ]
        # Only fetch strikes we don't have yet
        for name, fn in fetchers:
            if ex_strikes[name] is None:
                t = threading.Thread(target=fn, args=(contest_ts,), daemon=True)
                t.start()
                threads.append(t)
        for t in threads:
            t.join(timeout=3)

        # Count how many we have
        have = sum(1 for ex in EXCHANGES if ex_strikes[ex] is not None)
        if have == len(EXCHANGES):
            return  # Got them all
        if attempt < 15:
            time.sleep(1)
        else:
            time.sleep(3)

def _fetch_strike_kraken(ts):
    try:
        r = requests.get("https://api.kraken.com/0/public/OHLC",
            params={"pair": "XBTUSD", "interval": 5}, timeout=3)
        for c in r.json()["result"]["XXBTZUSD"]:
            if int(c[0]) == ts:
                ex_strikes["kraken"] = float(c[1]); return
    except: pass

def _fetch_strike_coinbase(ts):
    try:
        start = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(ts - 600))
        end = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(ts + 300))
        r = requests.get("https://api.exchange.coinbase.com/products/BTC-USD/candles",
            params={"granularity": 300, "start": start, "end": end}, timeout=3)
        for c in r.json():
            if int(c[0]) == ts:
                ex_strikes["coinbase"] = float(c[3]); return
            elif int(c[0]) == ts - 300:
                ex_strikes["coinbase"] = float(c[4])
    except: pass

def _fetch_strike_bitstamp(ts):
    try:
        r = requests.get("https://www.bitstamp.net/api/v2/ohlc/btcusd/",
            params={"step": 300, "limit": 10}, timeout=3)
        for c in r.json()["data"]["ohlc"]:
            if int(c["timestamp"]) == ts:
                ex_strikes["bitstamp"] = float(c["open"]); return
    except: pass

def _fetch_strike_okx(ts):
    try:
        r = requests.get("https://www.okx.com/api/v5/market/candles",
            params={"instId": "BTC-USDT", "bar": "5m", "limit": 5}, timeout=3)
        for c in r.json()["data"]:
            if int(c[0]) // 1000 == ts:
                ex_strikes["okx"] = float(c[1]); return
    except: pass

def _fetch_strike_bitfinex(ts):
    try:
        r = requests.get("https://api-pub.bitfinex.com/v2/candles/trade:5m:tBTCUSD/hist",
            params={"limit": 10, "sort": -1}, timeout=3)
        for c in r.json():
            if int(c[0]) // 1000 == ts:
                ex_strikes["bitfinex"] = float(c[1]); return
    except: pass

def _fetch_strike_bybit(ts):
    try:
        r = requests.get("https://api.bybit.com/v5/market/kline",
            params={"category": "spot", "symbol": "BTCUSDT", "interval": "5", "limit": 10}, timeout=3)
        for c in r.json()["result"]["list"]:
            if int(c[0]) // 1000 == ts:
                ex_strikes["bybit"] = float(c[1]); return
    except: pass

def _fetch_strike_cryptodotcom(ts):
    try:
        r = requests.get("https://api.crypto.com/exchange/v1/public/get-candlestick",
            params={"instrument_name": "BTC_USD", "timeframe": "5m", "count": 10}, timeout=3)
        for c in r.json()["result"]["data"]:
            if int(c["t"]) // 1000 == ts:
                ex_strikes["cryptodotcom"] = float(c["o"]); return
    except: pass

def _fetch_strike_htx(ts):
    try:
        r = requests.get("https://api.huobi.pro/market/history/kline",
            params={"symbol": "btcusdt", "period": "5min", "size": 10}, timeout=3)
        for c in r.json()["data"]:
            if int(c["id"]) == ts:
                ex_strikes["htx"] = float(c["open"]); return
    except: pass

# ================= POSITION POLLER =================

def poll_positions_loop():
    global position_size, last_pos_log_time
    while True:
        try:
            response = requests.get(
                f"{DATA_API}/positions",
                params={"user": USER_ADDRESS, "sizeThreshold": 0},
                timeout=10,
            )
            positions = response.json()
            for p in positions:
                if p.get("slug") == current_slug and float(p.get("size", 0)) >= 1:
                    position_size = float(p.get("size"))
                    now = time.time()
                    if now - last_pos_log_time >= 30:
                        print(f"[POS] {current_slug} | size={position_size} | avg={p.get('avgPrice')} | cur={p.get('curprice')}")
                        last_pos_log_time = now
                    break
        except Exception as e:
            print(f"[POS ERR] {e}")
        time.sleep(2)

# # ================= CONSENSUS VOTE (DISABLED) =================
# def get_consensus_vote():
#     """Single source: PM-Chainlink price vs Chainlink strike."""
#     if pm_cl_price is None:
#         return None, "no CL price"
#     if not pm_cl_strike_locked:
#         return None, "waiting for CL strike"
#     strike = pm_cl_strike
#     diff = pm_cl_price - strike
#     if abs(diff) < MIN_DIFF:
#         return None, f"CL diff={diff:+.2f} below MIN_DIFF (Y={latest_yes_bid} N={latest_no_bid})"
#     if diff > 0 and latest_yes_bid is not None and latest_yes_bid < 0.50:
#         return "BUY_NO", f"BUY_NO CL=${pm_cl_price:,.2f} stk=${strike:,.2f} diff={diff:+.2f} Y={latest_yes_bid:.2f}"
#     elif diff < 0 and latest_no_bid is not None and latest_no_bid < 0.50:
#         return "BUY_YES", f"BUY_YES CL=${pm_cl_price:,.2f} stk=${strike:,.2f} diff={diff:+.2f} N={latest_no_bid:.2f}"
#     else:
#         return None, f"CL diff={diff:+.2f} no misprice (Y={latest_yes_bid} N={latest_no_bid})"

# # ================= OUTCOME TRACKING (DISABLED) =================
# def _record_outcome(side, hit_5c, slug):
#     global fade_mode, consecutive_losses
#     mode_str = "FADE" if fade_mode else "FOLLOW"
#     if hit_5c:
#         consecutive_losses += 1
#         print(f"[OUTCOME] 5c HIT | bought {side} | {slug} | losses={consecutive_losses}/{LOSS_STREAK_FLIP} | mode={mode_str}")
#         if consecutive_losses >= LOSS_STREAK_FLIP:
#             fade_mode = not fade_mode
#             consecutive_losses = 0
#     else:
#         consecutive_losses = 0

# ================= MARKET SWITCH =================

def switch_market(ws, slug):
    global current_slug, yes_token, no_token
    global entry_done, last_entry_side
    global current_position_token, position_size, pos_miss_count
    global latest_yes_bid, latest_no_bid
    global fade_mode, consecutive_losses, contest_hit_5c
    global prev_yes_token, prev_no_token, prev_entry_side, prev_hit_5c, prev_slug
    global prev_yes_bid, prev_no_bid, prev_reversal_done, prev_sl_done
    global pm_cl_strike_locked
    global stop_armed, stop_done, sl_done

    with switch_lock:
        if slug == current_slug:
            return

        # --- Finalize the PREVIOUS previous contest ---
        if prev_entry_side is not None:
            prev_entry_side = None

        # --- Save current contest as "previous" so we keep watching it ---
        prev_yes_token = yes_token
        prev_no_token = no_token
        prev_entry_side = last_entry_side
        prev_hit_5c = contest_hit_5c
        prev_slug = current_slug
        prev_yes_bid = latest_yes_bid
        prev_no_bid = latest_no_bid
        prev_reversal_done = False
        prev_sl_done = sl_done  # carry over SL state — if already fired, don't fire again

        try:
            new_yes, new_no = fetch_tokens(slug)
        except Exception as e:
            print(f"[SWITCH ERR] Could not fetch tokens for {slug}: {e}")
            return

        yes_token, no_token = new_yes, new_no

        # Subscribe to new contest + keep old contest subscribed for reversal detection
        sub_ids = [yes_token, no_token]
        if prev_yes_token and prev_no_token:
            sub_ids.extend([prev_yes_token, prev_no_token])
        ws.send(json.dumps({
            "assets_ids": sub_ids,
            "operation": "subscribe"
        }))

        current_slug = slug
        entry_done = False
        last_entry_side = None
        contest_hit_5c = False
        stop_armed = False
        stop_done = False
        sl_done = False
        pm_cl_strike_locked = False  # allow new boundary tick to lock strike
        current_position_token = None
        position_size = 0
        pos_miss_count = 0
        latest_yes_bid = None
        latest_no_bid = None

        # Set pseudo-strike from PM-Chainlink current price
        if pm_cl_price is not None:
            for ex in EXCHANGES:
                ex_strikes[ex] = pm_cl_price
            print(f"\n{'='*50}")
            print(f"MARKET: {slug}")
            print(f"YES: {yes_token[:12]}... NO: {no_token[:12]}...")
            print(f"Pseudo-strike (CL): ${pm_cl_price:,.2f}")
            print(f"{'='*50}")
        else:
            for ex in EXCHANGES:
                ex_strikes[ex] = None
            print(f"\n{'='*50}")
            print(f"MARKET: {slug}")
            print(f"YES: {yes_token[:12]}... NO: {no_token[:12]}...")
            print(f"Pseudo-strike: waiting for CL feed...")
            print(f"{'='*50}")

        # Fetch initial book state via REST
        try:
            for token, label in [(yes_token, "YES"), (no_token, "NO")]:
                r = requests.get(
                    f"https://clob.polymarket.com/book",
                    params={"token_id": token},
                    timeout=5,
                )
                book = r.json()
                bids = book.get("bids", [])
                if bids:
                    best = max(float(b["price"]) for b in bids)
                    print(f"[BOOK] {label} best_bid={best:.2f}")
                    if token == yes_token:
                        latest_yes_bid = best
                    else:
                        latest_no_bid = best
                else:
                    print(f"[BOOK] {label} no bids")
        except Exception as e:
            print(f"[BOOK ERR] {e}")

        # Try entry immediately
        try_trigger_entry()

# ================= ENTRY LOGIC =================

def try_trigger_entry():
    """First side whose bid hits TRIGGER_PRICE → limit buy that side @ ENTRY_PRICE."""
    global entry_done, current_position_token, last_entry_side

    if entry_done:
        return

    if latest_yes_bid is not None and latest_yes_bid >= TRIGGER_PRICE:
        side, token, label = "YES", yes_token, "YES"
    elif latest_no_bid is not None and latest_no_bid >= TRIGGER_PRICE:
        side, token, label = "NO", no_token, "NO"
    else:
        return

    entry_done = True
    current_position_token = token
    last_entry_side = side
    print(f"\n{'!'*60}")
    print(f"[ENTRY] {label} bid hit {TRIGGER_PRICE} → buying {SIZE} {label} @ {ENTRY_PRICE}")
    print(f"{'!'*60}")
    try:
        client.create_and_post_order(
            OrderArgs(token_id=token, price=ENTRY_PRICE, size=SIZE, side=BUY)
        )
    except Exception as e:
        print(f"[ENTRY ERR] {e}")


def check_sl():
    """Stop loss: if other side bid hits SL_TRIGGER (0.25), buy other side @ SL_PRICE (0.20)."""
    global sl_done

    if not entry_done or sl_done or stop_done or last_entry_side is None:
        return

    other_bid = latest_no_bid if last_entry_side == "YES" else latest_yes_bid
    if other_bid is None or other_bid < SL_TRIGGER:
        return

    sl_done = True
    other_side = "NO" if last_entry_side == "YES" else "YES"
    other_token = no_token if last_entry_side == "YES" else yes_token

    print(f"\n{'!'*60}")
    print(f"[SL] {other_side} bid hit {other_bid:.2f} >= {SL_TRIGGER} → buying {SIZE} {other_side} @ {SL_PRICE}")
    print(f"{'!'*60}")
    try:
        client.create_and_post_order(
            OrderArgs(token_id=other_token, price=SL_PRICE, size=SIZE, side=BUY)
        )
    except Exception as e:
        print(f"[SL ERR] {e}")


def check_stop():
    """Profit protection: if our side hits STOP_ARM (0.85), arm the stop.
    When armed, if OTHER side hits STOP_TRIGGER (0.40), cancel all orders
    and reverse into the other side with STOP_SIZE @ STOP_PRICE."""
    global stop_armed, stop_done, sl_done

    if not entry_done or stop_done or last_entry_side is None:
        return

    our_bid = latest_yes_bid if last_entry_side == "YES" else latest_no_bid
    other_bid = latest_no_bid if last_entry_side == "YES" else latest_yes_bid

    # Arm the stop once our side hits deep profit
    if not stop_armed:
        if our_bid is not None and our_bid >= STOP_ARM:
            stop_armed = True
            print(f"[STOP ARMED] {last_entry_side} bid hit {our_bid:.2f} >= {STOP_ARM} — watching other side for {STOP_TRIGGER}")
        return

    # Stop is armed — check if other side triggers
    if other_bid is None or other_bid < STOP_TRIGGER:
        return

    # FIRE STOP
    stop_done = True
    sl_done = True  # block SL from firing after stop reversal
    other_side = "NO" if last_entry_side == "YES" else "YES"
    other_token = no_token if last_entry_side == "YES" else yes_token

    print(f"\n{'!'*60}")
    print(f"[STOP] Other side ({other_side}) bid hit {other_bid:.2f} >= {STOP_TRIGGER} — reversing")
    print(f"[STOP] Cancelling open orders, buying {STOP_SIZE} {other_side} @ {STOP_PRICE}")
    print(f"{'!'*60}")

    # Cancel all open orders
    try:
        client.cancel_all()
        print(f"[STOP] Cancelled all open orders")
    except Exception as e:
        print(f"[STOP CANCEL ERR] {e}")

    # Place reversal order
    try:
        client.create_and_post_order(
            OrderArgs(token_id=other_token, price=STOP_PRICE, size=STOP_SIZE, side=BUY)
        )
    except Exception as e:
        print(f"[STOP ENTRY ERR] {e}")

# ================= MARKET HANDLER =================

def on_market_open(ws):
    global active_ws
    active_ws = ws
    switch_market(ws, get_current_slug())

def on_market_message(ws, message):
    global last_tick_time, last_heartbeat_time
    global latest_yes_bid, latest_no_bid

    try:
        if not message or not message.strip():
            return

        data = json.loads(message)

        if not isinstance(data, dict) or data.get("event_type") != "book":
            return

        last_tick_time = time.time()

        # Switch to next contest 30s early, or catch up if boundary passed
        global switched_early, contest_hit_5c, prev_hit_5c
        global prev_reversal_done, prev_yes_bid, prev_no_bid, prev_sl_done
        ttl = seconds_to_next_boundary()
        if ttl <= 120:
            nxt = get_next_slug()
            if nxt != current_slug:
                switched_early = True
                switch_market(ws, nxt)
                return
        elif not switched_early:
            # Only switch to "current" if we haven't already switched early
            current = get_current_slug()
            if current != current_slug:
                switch_market(ws, current)
                return

        asset = data.get("asset_id")

        # --- Watch previous contest for late reversal ---
        if prev_yes_token and not prev_reversal_done and asset in (prev_yes_token, prev_no_token):
            p_bids = sorted(data.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
            if p_bids:
                p_bid = float(p_bids[0]["price"])
                if asset == prev_yes_token:
                    old_bid = prev_yes_bid
                    prev_yes_bid = p_bid
                else:
                    old_bid = prev_no_bid
                    prev_no_bid = p_bid

                # Prev contest SL: if we had a position and other side hits SL_TRIGGER
                if prev_entry_side is not None and not prev_sl_done and not prev_reversal_done:
                    prev_other_bid = prev_no_bid if prev_entry_side == "YES" else prev_yes_bid
                    if prev_other_bid is not None and prev_other_bid >= SL_TRIGGER:
                        prev_sl_done = True
                        sl_side = "NO" if prev_entry_side == "YES" else "YES"
                        sl_token = prev_no_token if prev_entry_side == "YES" else prev_yes_token
                        print(f"\n{'!'*60}")
                        print(f"[SL PREV] {sl_side} bid hit {prev_other_bid:.2f} >= {SL_TRIGGER} on {prev_slug} → buying {SIZE} {sl_side} @ {SL_PRICE}")
                        print(f"{'!'*60}")
                        try:
                            client.create_and_post_order(
                                OrderArgs(token_id=sl_token, price=SL_PRICE, size=SIZE, side=BUY)
                            )
                        except Exception as e:
                            print(f"[SL PREV ERR] {e}")

                # Detect reversal: side was dead (≤0.10) and just jumped to ≥0.30
                if old_bid is not None and old_bid <= REVERSAL_DEAD_THRESHOLD and p_bid >= REVERSAL_JUMP_THRESHOLD:
                    prev_reversal_done = True
                    rev_side = "YES" if asset == prev_yes_token else "NO"
                    rev_token = prev_yes_token if asset == prev_yes_token else prev_no_token
                    print(f"\n{'!'*60}")
                    print(f"[REVERSAL] {rev_side} on {prev_slug} jumped {old_bid:.2f} → {p_bid:.2f} — REVERSING")
                    print(f"[REVERSAL] Cancelling all, buying {REVERSAL_SIZE} {rev_side} @ market (0.95)")
                    print(f"{'!'*60}")
                    try:
                        client.cancel_all()
                    except Exception as e:
                        print(f"[REVERSAL CANCEL ERR] {e}")
                    try:
                        client.create_and_post_order(
                            OrderArgs(token_id=rev_token, price=0.95, size=REVERSAL_SIZE, side=BUY)
                        )
                    except Exception as e:
                        print(f"[REVERSAL ENTRY ERR] {e}")

        if asset not in (yes_token, no_token):
            return

        bids = sorted(data.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
        if not bids:
            return

        best_bid = float(bids[0]["price"])

        if asset == yes_token:
            latest_yes_bid = best_bid
        else:
            latest_no_bid = best_bid

        # Track 5c hit on our side
        if not contest_hit_5c and last_entry_side is not None:
            if (last_entry_side == "YES" and asset == yes_token and best_bid <= 0.05):
                contest_hit_5c = True
                print(f"[5c HIT] YES bid dropped to {best_bid:.2f} — marking loss")
            elif (last_entry_side == "NO" and asset == no_token and best_bid <= 0.05):
                contest_hit_5c = True
                print(f"[5c HIT] NO bid dropped to {best_bid:.2f} — marking loss")

        # Heartbeat every 30s
        now_hb = time.time()
        if now_hb - last_heartbeat_time >= 30:
            y = f"{latest_yes_bid:.2f}" if latest_yes_bid is not None else "--"
            n = f"{latest_no_bid:.2f}" if latest_no_bid is not None else "--"
            status = "DONE" if entry_done else "waiting"
            side_str = f" | side={last_entry_side}" if entry_done else ""
            sl_str = " | SL FIRED" if sl_done else ""
            stop_str = " | STOP FIRED" if stop_done else (" | STOP ARMED" if stop_armed else "")
            print(f"[TICK] Y={y} N={n} | ttl={seconds_to_next_boundary()}s | entry={status}{side_str}{sl_str}{stop_str} | trigger={TRIGGER_PRICE}")
            last_heartbeat_time = now_hb

        # Check entry on every tick, then check sl/stop
        try_trigger_entry()
        check_sl()
        check_stop()

    except Exception as e:
        print(f"[MSG ERR] {e}")

# ================= START =================

def start_trading_bot():
    print("Trading bot started (trigger strategy)")
    print(f"  Trigger: first side to hit bid >= {TRIGGER_PRICE}")
    print(f"  Entry: limit buy that side @ {ENTRY_PRICE}, size={SIZE}")
    print(f"  SL: other side hits {SL_TRIGGER} → buy other side {SIZE} @ {SL_PRICE}")
    print(f"  Stop: arm at {STOP_ARM}, fire at other side {STOP_TRIGGER}, reverse {STOP_SIZE} @ {STOP_PRICE}")
    print(f"  Reversal: dead side (≤{REVERSAL_DEAD_THRESHOLD}) jumps to ≥{REVERSAL_JUMP_THRESHOLD} → buy {REVERSAL_SIZE} @ 0.95")

    threading.Thread(target=poll_positions_loop, daemon=True).start()

    # Start all 8 exchange WS feeds
    # Only Chainlink RTDS feed — 8 exchange feeds commented out for now
    # for fn in [start_kraken_ws, start_coinbase_ws, start_bitstamp_ws, start_okx_ws,
    #            start_bitfinex_ws, start_bybit_ws, start_cryptodotcom_ws, start_htx_ws]:
    #     threading.Thread(target=fn, daemon=True).start()
    threading.Thread(target=start_pm_chainlink_ws, daemon=True).start()

    def boundary_checker():
        """Ensure we switch to new contest even if WS goes quiet after expiry."""
        global switched_early
        while True:
            if active_ws is not None:
                current = get_current_slug()
                ttl = seconds_to_next_boundary()
                if switched_early:
                    # Only clear flag once the boundary has actually passed (ttl > 250 means new period)
                    if ttl > 250 and current == current_slug:
                        switched_early = False
                else:
                    if current != current_slug:
                        print(f"[BOUNDARY] Forcing switch to {current}")
                        switch_market(active_ws, current)
            time.sleep(3)

    threading.Thread(target=boundary_checker, daemon=True).start()

    def watchdog():
        while True:
            if time.time() - last_tick_time > 60:
                print("[WATCHDOG] No data for 60s — restarting process")
                os._exit(1)
            time.sleep(10)

    threading.Thread(target=watchdog, daemon=True).start()

    while True:
        try:
            print("Connecting to Polymarket websocket...")
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
