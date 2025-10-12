import time
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from auth import init_client
from markets import fetch_live_games, fetch_live_nba_games, fetch_live_nhl_games
from trader import place_both_sides, monitor_and_cancel
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY


# ==========================================================
# === CONFIGURATION ========================================
# ==========================================================

# NFL
NFL_MAX_WORKERS = 10
NFL_ENTRY_PRICE = 0.16
NFL_ENTRY_SIZE = 7.0

# NBA
NBA_MAX_WORKERS = 10
NBA_ENTRY_PRICE = 0.05
NBA_ENTRY_SIZE = 20.0
NBA_SELL_PRICE = 0.50

# NHL
NHL_MAX_WORKERS = 8
NHL_ENTRY_PRICE = 0.30
NHL_ENTRY_SIZE = 10.0
NHL_REVERSAL_PRICE = 0.20


# ==========================================================
# === NFL HANDLER LOOP =====================================
# ==========================================================

def handle_nfl_contest(client, m, ev):
    """Tail-risk logic for NFL (reuses standard monitor_and_cancel)."""
    cid = m.get("id")
    question = m.get("question")
    score = ev.get("score")
    period = ev.get("period")
    elapsed = ev.get("elapsed")

    print(f"\n[{cid}] [NFL TRADE] {question} | Score {score} | Period {period} | Elapsed {elapsed}")

    results = place_both_sides(client, m, price=NFL_ENTRY_PRICE, size=NFL_ENTRY_SIZE)
    if results:
        monitor_and_cancel(client, results)
    print(f"[{cid}] [NFL DONE] {question}")


def nfl_loop(client):
    """Continuously fetch and trade NFL contests concurrently."""
    traded = set()
    executor = ThreadPoolExecutor(max_workers=NFL_MAX_WORKERS)

    while True:
        try:
            games = fetch_live_games()
            print(f"\n=== Qualified NFL contests: {len(games)} ===")

            for m, ev in games:
                cid = m.get("id")
                if cid in traded:
                    continue
                executor.submit(handle_nfl_contest, client, m, ev)
                traded.add(cid)
                print(f"[{cid}] Submitted NFL contest to thread pool.")
            time.sleep(25)

        except Exception as e:
            print("[NFL LOOP ERROR]", e)
            time.sleep(10)


# ==========================================================
# === NBA HANDLER LOOP =====================================
# ==========================================================

def handle_nba_contest(client, m, ev):
    """NBA logic: both sides at 5¢, cancel opposite, resell half at 50¢ (uses retry logic)."""
    cid = m.get("id")
    question = m.get("question")
    score = ev.get("score")
    period = ev.get("period")

    print(f"\n[{cid}] [NBA TRADE] {question} | Score {score} | Period {period}")

    # Step 1: place both sides
    results = place_both_sides(client, m, price=NBA_ENTRY_PRICE, size=NBA_ENTRY_SIZE)
    if not results:
        print(f"[{cid}] No orders placed for {question}")
        return

    # Step 2: monitor fills, cancel other side, resell using same retry logic as NFL/CFB
    monitor_and_cancel(client, results, resell_price=NBA_SELL_PRICE)
    print(f"[{cid}] [NBA DONE] {question}")


def nba_loop(client):
    """Continuously fetch and trade NBA contests concurrently."""
    traded = set()
    executor = ThreadPoolExecutor(max_workers=NBA_MAX_WORKERS)

    while True:
        try:
            games = fetch_live_nba_games()
            print(f"\n=== Qualified NBA contests: {len(games)} ===")

            for m, ev in games:
                cid = m.get("id")
                if cid in traded:
                    continue
                executor.submit(handle_nba_contest, client, m, ev)
                traded.add(cid)
                print(f"[{cid}] Submitted NBA contest to thread pool.")
            time.sleep(20)

        except Exception as e:
            print("[NBA LOOP ERROR]", e)
            time.sleep(10)


# ==========================================================
# === NHL HANDLER LOOP =====================================
# ==========================================================

def handle_nhl_contest(client, m, ev):
    """NHL logic: buy favorite at 0.30; if unfilled by P3, cancel and buy opposite if >0.20."""
    cid = m.get("id")
    question = m.get("question")
    period = ev.get("period")
    score = ev.get("score")
    print(f"\n[{cid}] [NHL TRADE] {question} | Period {period} | Score {score}")

    try:
        prices = [float(x) for x in json.loads(m.get("outcomePrices", "[]"))]
        tokens = json.loads(m.get("clobTokenIds", "[]"))
        outcomes = json.loads(m.get("outcomes", "[]"))
    except Exception as e:
        print(f"[{cid}] Could not parse outcome data: {e}")
        return
    if len(prices) != 2 or len(tokens) != 2:
        print(f"[{cid}] Bad outcome data.")
        return

    fav_idx = 0 if prices[0] > prices[1] else 1
    und_idx = 1 - fav_idx
    fav_token = tokens[fav_idx]
    fav_team = outcomes[fav_idx]
    und_token = tokens[und_idx]
    und_team = outcomes[und_idx]

    print(f"[{cid}] Favorite: {fav_team} ({prices[fav_idx]}) | Underdog: {und_team} ({prices[und_idx]})")

    try:
        order = OrderArgs(price=NHL_ENTRY_PRICE, size=NHL_ENTRY_SIZE, side=BUY, token_id=fav_token)
        signed = client.create_order(order)
        resp = client.post_order(signed)
        order_id = resp.get("orderID") if isinstance(resp, dict) else None
        print(f"[BUY] {fav_team} {NHL_ENTRY_SIZE}@{NHL_ENTRY_PRICE} | OrderID={order_id}")
    except Exception as e:
        print(f"[FAIL] Favorite buy failed: {e}")
        return

    # Monitor until P3 for possible reversal buy
    while True:
        time.sleep(30)
        try:
            games = fetch_live_nhl_games()
            for gm, ev2 in games:
                if gm.get("id") == cid:
                    curr_period = ev2.get("period")
                    if curr_period in ("p3", "3p", "P3", "3P"):
                        print(f"[CANCEL] Reached P3 | Cancel favorite {order_id}")
                        try:
                            client.cancel(order_id=order_id)
                        except Exception as ce:
                            print(f"[CANCEL FAIL] {ce}")

                        new_prices = [float(x) for x in json.loads(gm.get("outcomePrices", "[]"))]
                        if new_prices[und_idx] > NHL_REVERSAL_PRICE:
                            rev_order = OrderArgs(price=new_prices[und_idx], size=NHL_ENTRY_SIZE,
                                                  side=BUY, token_id=und_token)
                            rev_signed = client.create_order(rev_order)
                            rev_resp = client.post_order(rev_signed)
                            rev_id = rev_resp.get("orderID") if isinstance(rev_resp, dict) else None
                            print(f"[REVERSAL BUY] {und_team} {NHL_ENTRY_SIZE}@{new_prices[und_idx]} | OrderID={rev_id}")
                        return
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
            continue


def nhl_loop(client):
    traded = set()
    executor = ThreadPoolExecutor(max_workers=NHL_MAX_WORKERS)
    while True:
        try:
            games = fetch_live_nhl_games()
            print(f"\n=== Qualified NHL contests: {len(games)} ===")

            for m, ev in games:
                cid = m.get("id")
                if cid in traded:
                    continue
                if ev.get("period") in ("p1", "1p", "1P", "P1"):
                    executor.submit(handle_nhl_contest, client, m, ev)
                    traded.add(cid)
                    print(f"[{cid}] Submitted NHL contest to thread pool.")
            time.sleep(30)
        except Exception as e:
            print("[NHL LOOP ERROR]", e)
            time.sleep(10)


# ==========================================================
# === MAIN ENTRY POINT =====================================
# ==========================================================

def main():
    client = init_client()

    nfl_thread = Thread(target=nfl_loop, args=(client,), daemon=True)
    nba_thread = Thread(target=nba_loop, args=(client,), daemon=True)
    nhl_thread = Thread(target=nhl_loop, args=(client,), daemon=True)

    nfl_thread.start()
    nba_thread.start()
    nhl_thread.start()

    print("\n[BOT] NFL + NBA + NHL concurrent trading started...\n")

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()


