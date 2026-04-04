"""Live monitor: PM-Chainlink ticks with YES/NO book prices side by side."""
import json
import time
import threading
from datetime import datetime, timezone
from websocket import WebSocketApp

RTDS_WS = "wss://ws-live-data.polymarket.com"
PM_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_API = "https://gamma-api.polymarket.com"

# State
yes_bid = None
no_bid = None
cl_strike = None
cl_strike_locked = False
ticks = []  # (ts_ms, price, yes, no)
yes_depth = 0  # total bid size for YES
no_depth = 0   # total bid size for NO

# Sweep detection
trade_buf = []  # (ts_ms, side_label, price, size)  — rolling window
sweeps = []     # (ts_str, side_label, count, total_size, lo_price, hi_price, duration)
SWEEP_WINDOW = 2.0    # seconds — trades within this window = potential sweep
SWEEP_MIN_FILLS = 1   # single fill counts
SWEEP_MIN_SIZE = 700  # minimum total shares to show in sweep log
sweep_vol_yes = 0     # cumulative sweep volume this contest
sweep_vol_no = 0
all_vol_yes = 0       # cumulative ALL trade volume this contest
all_vol_no = 0

# Sim trade
sim_side = None       # "YES" or "NO"
sim_entry = None      # entry price
sim_ts = None         # entry time string

def get_current_slug():
    now = int(time.time()); r = now - (now % 300)
    return f"btc-updown-5m-{r}"

def get_next_slug():
    now = int(time.time()); r = now - (now % 300)
    return f"btc-updown-5m-{r + 300}"

def seconds_to_boundary():
    now = int(time.time()); r = now - (now % 300)
    return (r + 300) - now

# ===== PM Book WS =====
def start_book_ws():
    global yes_bid, no_bid
    import requests
    pm = {"slug": None, "yes_token": None, "no_token": None}

    def switch(ws, slug):
        global sweep_vol_yes, sweep_vol_no, all_vol_yes, all_vol_no, sim_side, sim_entry, sim_ts
        if slug == pm["slug"]: return
        sweep_vol_yes = 0
        sweep_vol_no = 0
        all_vol_yes = 0
        all_vol_no = 0
        sim_side = None
        sim_entry = None
        sim_ts = None
        try:
            r = requests.get(f"{GAMMA_API}/events/slug/{slug}", timeout=10)
            tokens = json.loads(r.json()["markets"][0]["clobTokenIds"])
            pm["yes_token"], pm["no_token"] = tokens[0], tokens[1]
            pm["slug"] = slug
            ws.send(json.dumps({"assets_ids": [tokens[0], tokens[1]], "operation": "subscribe"}))
            # REST snapshot
            for token, side in [(tokens[0], "yes"), (tokens[1], "no")]:
                try:
                    br = requests.get("https://clob.polymarket.com/book", params={"token_id": token}, timeout=5)
                    bids = br.json().get("bids", [])
                    if bids:
                        best = max(float(b["price"]) for b in bids)
                        if side == "yes": yes_bid = best
                        else: no_bid = best
                except: pass
        except: pass

    def on_open(ws):
        switch(ws, get_current_slug())
        # Background thread to force-switch when book goes silent
        def contest_checker():
            while True:
                time.sleep(3)
                try:
                    current = get_current_slug()
                    if current != pm["slug"]:
                        switch(ws, current)
                except: pass
        threading.Thread(target=contest_checker, daemon=True).start()

    def on_message(ws, message):
        global yes_bid, no_bid, sweep_vol_yes, sweep_vol_no, all_vol_yes, all_vol_no, yes_depth, no_depth
        if not message or not message.strip(): return
        try:
            data = json.loads(message)
            if not isinstance(data, dict): return
            et = data.get("event_type")

            # Switch only when boundary passes
            current = get_current_slug()
            if current != pm["slug"]: switch(ws, current)

            if et == "book":
                asset = data.get("asset_id")
                if asset not in (pm["yes_token"], pm["no_token"]): return
                bids = data.get("bids", [])
                if not bids: return
                best = max(float(b["price"]) for b in bids)
                total_size = sum(float(b["size"]) for b in bids)
                if asset == pm["yes_token"]:
                    yes_bid = best
                    yes_depth = total_size
                else:
                    no_bid = best
                    no_depth = total_size

            elif et == "last_trade_price":
                asset = data.get("asset_id")
                if asset not in (pm["yes_token"], pm["no_token"]): return
                side_label = "YES" if asset == pm["yes_token"] else "NO"
                trade_side = data.get("side", "").upper()  # BUY = taker bought (sweep asks)
                price = float(data.get("price", 0))
                size = float(data.get("size", 0))
                ts_ms = int(data.get("timestamp", 0))

                # BUY on YES token = buying YES, SELL on YES token = selling YES (= buying NO)
                # BUY on NO token = buying NO, SELL on NO token = selling NO (= buying YES)
                if trade_side == "BUY":
                    buy_side = side_label  # buying this token
                else:
                    buy_side = "NO" if side_label == "YES" else "YES"  # selling this = buying other

                # Rolling cumulative for ALL trades
                if buy_side == "YES":
                    all_vol_yes += size
                else:
                    all_vol_no += size

                # Sweep detection: group by token+side so prices are comparable
                # key = "BUY YES" or "SELL YES" etc
                trade_key = f"{trade_side} {side_label}"
                trade_buf.append((ts_ms, trade_key, price, size, buy_side))

                # Prune old trades outside window
                cutoff = ts_ms - int(SWEEP_WINDOW * 1000)
                while trade_buf and trade_buf[0][0] < cutoff:
                    trade_buf.pop(0)

                # Sweep log: 2+ fills on same token+side within window
                key_trades = [(t, k, p, sz, bs) for t, k, p, sz, bs in trade_buf if k == trade_key]
                if len(key_trades) >= 2:
                    prices = [p for _, _, p, _, _ in key_trades]
                    sizes = [sz for _, _, _, sz, _ in key_trades]
                    total = sum(sizes)
                    duration = (key_trades[-1][0] - key_trades[0][0]) / 1000
                    lo, hi = min(prices), max(prices)
                    ts_str = datetime.fromtimestamp(ts_ms // 1000, tz=timezone.utc).strftime("%H:%M:%S")
                    # Accumulate sweep vol for ALL sweeps (no min size)
                    if buy_side == "YES":
                        sweep_vol_yes += total
                    else:
                        sweep_vol_no += total
                    # Only log to sweep list if meets min size
                    if total < SWEEP_MIN_SIZE:
                        trade_buf[:] = [(t, k, p, sz, bs) for t, k, p, sz, bs in trade_buf if k != trade_key]
                        return
                    sweep = (ts_str, buy_side, len(key_trades), total, lo, hi, duration)
                    sweeps.append(sweep)
                    if len(sweeps) > 50:
                        sweeps.pop(0)
                    trade_buf[:] = [(t, k, p, sz, bs) for t, k, p, sz, bs in trade_buf if k != trade_key]
        except: pass

    while True:
        try:
            ws = WebSocketApp(PM_WS, on_open=on_open, on_message=on_message,
                on_error=lambda w,e: None, on_close=lambda w,c,m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

# ===== PM-Chainlink WS =====
def start_cl_ws():
    global cl_strike, cl_strike_locked
    def on_open(ws):
        ws.send(json.dumps({
            "action": "subscribe",
            "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*",
                               "filters": "{\"symbol\":\"btc/usd\"}"}]
        }))
        def ping():
            while True:
                try: ws.send("PING")
                except: break
                time.sleep(5)
        threading.Thread(target=ping, daemon=True).start()

    def on_message(ws, message):
        global cl_strike, cl_strike_locked
        try:
            data = json.loads(message)
            if data.get("topic") != "crypto_prices_chainlink": return
            p = data.get("payload", {})
            if p.get("symbol") != "btc/usd" or "value" not in p: return
            v = float(p["value"])
            ts_ms = p.get("timestamp", 0)
            ts_sec = ts_ms // 1000

            # Lock strike at boundary
            if ts_sec > 0 and ts_sec % 300 == 0:
                cl_strike = v
                cl_strike_locked = True

            ticks.append((ts_ms, v, yes_bid, no_bid))
            if len(ticks) > 300:
                ticks.pop(0)
        except: pass

    while True:
        try:
            ws = WebSocketApp(RTDS_WS, on_open=on_open, on_message=on_message,
                on_error=lambda w,e: None, on_close=lambda w,c,m: None)
            ws.run_forever(ping_interval=20)
        except: pass
        time.sleep(3)

# ===== Display =====
import os
def clear(): os.system("cls" if os.name == "nt" else "clear")

def display():
    global sim_side, sim_entry, sim_ts
    while True:
        clear()
        slug = get_current_slug()
        ttl = seconds_to_boundary()
        strike_str = f"${cl_strike:,.2f}" if cl_strike else "waiting..."
        locked = "*" if cl_strike_locked else ""

        print(f"  {slug}  |  TTL: {ttl}s  |  STRIKE: {strike_str}{locked}")
        print(f"  ALL VOL:  YES={all_vol_yes:,.0f}  NO={all_vol_no:,.0f}  NET={all_vol_yes - all_vol_no:+,.0f}")
        print(f"  SWEEP VOL:  YES={sweep_vol_yes:,.0f}  NO={sweep_vol_no:,.0f}  NET={sweep_vol_yes - sweep_vol_no:+,.0f}")
        print(f"  DEPTH:  YES bids={yes_depth:,.0f}  NO bids={no_depth:,.0f}")

        # Sim trade logic
        sweep_net = sweep_vol_yes - sweep_vol_no
        if sim_side is None:
            if sweep_net <= -2000 and yes_bid is not None and yes_bid < 0.50:
                sim_side = "YES"
                sim_entry = yes_bid
                sim_ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            elif sweep_net >= 2000 and no_bid is not None and no_bid < 0.50:
                sim_side = "NO"
                sim_entry = no_bid
                sim_ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

        if sim_side:
            cur = yes_bid if sim_side == "YES" else no_bid
            if cur is not None:
                pnl = cur - sim_entry
                print(f"  SIM: LONG {sim_side} @ {sim_entry:.2f} ({sim_ts}) | cur={cur:.2f} | PnL={pnl:+.2f}")
            else:
                print(f"  SIM: LONG {sim_side} @ {sim_entry:.2f} ({sim_ts}) | cur=-- | PnL=--")
        else:
            print(f"  SIM: waiting (sweep NET={sweep_net:+,.0f})")

        print()
        print(f"  {'TIME':>10}  {'CL PRICE':>12}  {'DIFF':>8}  {'%':>7}  {'YES':>5}  {'NO':>5}")
        print(f"  {'-'*10}  {'-'*12}  {'-'*8}  {'-'*7}  {'-'*5}  {'-'*5}")

        for ts_ms, val, y, n in ticks:
            ts_sec = ts_ms // 1000
            utc = datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime("%H:%M:%S")
            if cl_strike:
                d = val - cl_strike
                diff_str = f"{d:+.2f}"
                pct = (d / cl_strike) * 100
                pct_str = f"{pct:+.3f}%"
            else:
                diff_str = "--"
                pct_str = "--"
            y_str = f"{y:.2f}" if y is not None else "--"
            n_str = f"{n:.2f}" if n is not None else "--"
            marker = "  << STRIKE" if ts_sec % 300 == 0 else ""
            print(f"  {utc:>10}  ${val:>11,.2f}  {diff_str:>8}  {pct_str:>7}  {y_str:>5}  {n_str:>5}{marker}")

        # Show recent sweeps
        if sweeps:
            cum_yes = sum(t for _, s, _, t, _, _, _ in sweeps if s == "YES")
            cum_no = sum(t for _, s, _, t, _, _, _ in sweeps if s == "NO")
            print()
            print(f"  === SWEEPS ({len(sweeps)}) | CUM: YES={cum_yes:,.0f}  NO={cum_no:,.0f}  NET={cum_yes - cum_no:+,.0f} ===")
            for ts_str, side, count, total, lo, hi, dur in sweeps[-25:]:
                print(f"  {ts_str}  [SWEEP BUY {side}]  {count} fills  {total:.0f} shares  ${lo:.2f}→${hi:.2f}  {dur:.1f}s")

        print()
        time.sleep(0.5)

if __name__ == "__main__":
    threading.Thread(target=start_book_ws, daemon=True).start()
    threading.Thread(target=start_cl_ws, daemon=True).start()
    time.sleep(2)
    display()
