import time
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from auth import init_client
from markets import fetch_live_games, fetch_live_nba_games
from trader import place_both_sides, monitor_and_cancel


# ==========================================================
# === CONFIGURATION ========================================
# ==========================================================

# NFL CONFIG
NFL_MAX_WORKERS = 10
NFL_ENTRY_PRICE = 0.16
NFL_ENTRY_SIZE = 7.0

# NBA CONFIG
NBA_MAX_WORKERS = 10
NBA_ENTRY_PRICE = 0.04
NBA_ENTRY_SIZE = 400.0
NBA_RESELL_PRICE = 0.60
NBA_CANCEL_OTHERS = False   # keep both sides active

# ==========================================================
# === NFL HANDLER LOOP =====================================
# ==========================================================

def handle_nfl_contest(client, m):
    """
    NFL tail-risk logic:
      - 4Q or 4th quarter
      - ≤7:00 remaining
      - ≤8-point score difference
      - bestBid between 0.15–0.85
      - places both sides at 0.16
      - cancels opposite side when filled
      - no resell orders
    """
    cid = m.get("id")
    question = m.get("question")
    ev = m.get("_event_meta", {})  # event metadata
    score = ev.get("score")
    period = ev.get("period")
    elapsed = ev.get("elapsed")

    print(f"\n[{cid}] [NFL TRADE] {question} | Score={score} | Period={period} | Elapsed={elapsed}")

    results = place_both_sides(client, m, price=NFL_ENTRY_PRICE, size=NFL_ENTRY_SIZE)
    if results:
        monitor_and_cancel(client, results, resell_price=None, cancel_others=True)
        print(f"[{cid}] [NFL DONE] {question}")
    else:
        print(f"[{cid}] [NFL SKIP] Could not place orders.")


def nfl_loop(client):
    """Continuously fetch and trade NFL contests concurrently."""
    traded = set()
    executor = ThreadPoolExecutor(max_workers=NFL_MAX_WORKERS)

    while True:
        try:
            games = fetch_live_games()
            print(f"\n=== Qualified NFL contests: {len(games)} ===")

            for m in games:  # now just one object, not (m, ev)
                cid = m.get("id")
                if cid in traded:
                    continue
                executor.submit(handle_nfl_contest, client, m)
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
    """
    NBA logic:
      - Places both sides at 4¢
      - Keeps both active (does NOT cancel opposite)
      - Resells each filled side independently at 60¢
    """
    cid = m.get("id")
    question = m.get("question")
    score = ev.get("score")
    period = ev.get("period")

    print(f"\n[{cid}] [NBA TRADE] {question} | Score {score} | Period {period}")
    print(f"[MODE] cancel_others={NBA_CANCEL_OTHERS} | resell_price={NBA_RESELL_PRICE}")

    # Step 1: Place both sides
    results = place_both_sides(client, m, price=NBA_ENTRY_PRICE, size=NBA_ENTRY_SIZE)
    if not results:
        print(f"[{cid}] No orders placed for {question}")
        return

    # Step 2: Monitor fills for *each* side (keep both sides active)
    for order in results:
        try:
            contest_id, token_id, order_id, side, sz = order
            print(f"[{cid}] Monitoring order {order_id} ({side}) for fills...")
            Thread(
                target=monitor_and_cancel,
                args=(client, [order]),
                kwargs={
                    "resell_price": NBA_RESELL_PRICE,
                    "cancel_others": NBA_CANCEL_OTHERS
                },
                daemon=True
            ).start()
        except Exception as e:
            print(f"[{cid}] Failed to spawn monitor for order: {e}")

    print(f"[{cid}] [NBA ORDERS LIVE] {question}")


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

                period = (ev.get("period") or "").lower()
                elapsed = ev.get("elapsed") or ""

                # --- Skip if game is over (4Q or 0:00 clock) ---
                if period in ("q4", "4th", "4q"):
                    if elapsed.strip() == "0:00" or elapsed.strip() == "00:00" or not elapsed:
                        print(f"[{cid}] Skipping {m.get('question')} (Period={period}, Elapsed={elapsed}) — game ended.")
                        continue

                # --- Skip if missing live time but likely ended ---
                if elapsed.strip() in ("0:00", "00:00", "0", "00", ""):
                    print(f"[{cid}] Skipping {m.get('question')} (Elapsed={elapsed}) — likely finished.")
                    continue

                executor.submit(handle_nba_contest, client, m, ev)
                traded.add(cid)
                print(f"[{cid}] Submitted NBA contest to thread pool.")

            time.sleep(20)

        except Exception as e:
            print("[NBA LOOP ERROR]", e)
            time.sleep(10)


# ==========================================================
# === MAIN ENTRY POINT =====================================
# ==========================================================

def main():
    client = init_client()

    nfl_thread = Thread(target=nfl_loop, args=(client,), daemon=True)
    nba_thread = Thread(target=nba_loop, args=(client,), daemon=True)

    nfl_thread.start()
    nba_thread.start()

    print("\n[BOT] NFL + NBA concurrent trading started...\n")

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()


