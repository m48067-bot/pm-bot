import time
from concurrent.futures import ThreadPoolExecutor
from auth import init_client
from markets import fetch_live_games, fetch_live_nba_games
from trader import place_both_sides, monitor_and_cancel
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import SELL


# --- CONFIG ---
NFL_MAX_WORKERS = 10
NBA_MAX_WORKERS = 10

# NFL parameters
NFL_ENTRY_PRICE = 0.16
NFL_ENTRY_SIZE = 7.0

# NBA parameters
NBA_ENTRY_PRICE = 0.05
NBA_ENTRY_SIZE = 20.0
NBA_SELL_PRICE = 0.50
NBA_SELL_SIZE = NBA_ENTRY_SIZE / 2  # half-sell after fill


# =========================
# === NFL HANDLER LOOP ===
# =========================
def handle_nfl_contest(client, m, ev):
    """Tail-risk logic for NFL (no resells)."""
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


# =========================
# === NBA HANDLER LOOP ===
# =========================
def handle_nba_contest(client, m, ev):
    """NBA logic: both sides at 5c, cancel opposite, half-sell at 50c."""
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

    filled_token = None
    filled_order = None

    # Step 2: monitor fills
    while True:
        time.sleep(5)
        for contest_id, token_id, order_id, side, sz in results:
            try:
                order_info = client.get_order(order_id)
                status = order_info.get("status")
                if status and status.lower() in ("filled", "matched"):
                    filled_order = order_id
                    filled_token = token_id
                    print(f"[FILL] [{question}] order {order_id} filled | token={token_id}")
                    break
            except Exception as e:
                print(f"[FAIL] Could not fetch order {order_id}", e)

        if filled_order:
            # cancel the rest
            for contest_id, token_id, order_id, side, sz in results:
                if order_id != filled_order:
                    try:
                        client.cancel(order_id=order_id)
                        print(f"[CANCEL] [{question}] cancelled opposite order {order_id}")
                    except Exception as e:
                        print(f"[FAIL] Cancel {order_id}", e)
            break

    # Step 3: half-sell at 50c
    try:
        sell_args = OrderArgs(
            price=NBA_SELL_PRICE,
            size=NBA_SELL_SIZE,
            side=SELL,
            token_id=str(filled_token)
        )
        signed_sell = client.create_order(sell_args)
        resp = client.post_order(signed_sell)
        sell_id = resp.get("orderID") if isinstance(resp, dict) else None
        if sell_id:
            print(f"[SELL] [{question}] half-sell {NBA_SELL_SIZE} lots @ {NBA_SELL_PRICE} for token {filled_token}")
        else:
            print(f"[FAIL] [{question}] no orderID returned on sell attempt")
    except Exception as e:
        print(f"[FAIL] [{question}] could not place half-sell | {e}")

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


# =========================
# === MAIN ENTRY POINT ===
# =========================
def main():
    client = init_client()

    # Run NFL + NBA loops in parallel
    from threading import Thread
    nfl_thread = Thread(target=nfl_loop, args=(client,), daemon=True)
    nba_thread = Thread(target=nba_loop, args=(client,), daemon=True)

    nfl_thread.start()
    nba_thread.start()

    print("\n[BOT] NFL + NBA concurrent trading started...\n")

    # keep alive
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()

