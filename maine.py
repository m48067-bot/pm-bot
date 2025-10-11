import time
from concurrent.futures import ThreadPoolExecutor
from auth import init_client
from markets import fetch_live_games
from trader import place_both_sides, monitor_and_cancel


# --- Config ---
MAX_WORKERS = 8        # number of contests to trade simultaneously
ENTRY_PRICE = 0.16     # entry price for both sides
ENTRY_SIZE = 5.0       # order size (lots)


def handle_contest(client, m, ev):
    """
    Handle one NFL contest: place both sides, monitor fills, cancel the other side.
    (No resell logic for NFL.)
    """
    cid = m.get("id")
    question = m.get("question")
    score = ev.get("score")
    period = ev.get("period")
    elapsed = ev.get("elapsed")

    print(f"\n[{cid}] [NFL TRADE] {question} | Score {score} | Period {period} | Elapsed {elapsed}")

    results = place_both_sides(client, m, price=ENTRY_PRICE, size=ENTRY_SIZE)
    if results:
        monitor_and_cancel(client, results)
    print(f"[{cid}] Finished thread for {question}")


def main():
    """
    NFL tail-risk strategy:
    - Monitors live markets for close 4Q contests (≤6-pt difference, ≤5:00 remaining)
    - Places both-side orders once per contest
    - Manages fills concurrently across multiple games
    """
    client = init_client()
    traded = set()
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    while True:
        try:
            games = fetch_live_games()
            print(f"Qualified NFL contests: {len(games)}")

            for m, ev in games:
                cid = m.get("id")
                if cid in traded:
                    continue

                executor.submit(handle_contest, client, m, ev)
                traded.add(cid)
                print(f"[{cid}] Submitted to thread pool.")

            time.sleep(25)

        except Exception as e:
            print("[ERROR in main loop]", e)
            time.sleep(10)


if __name__ == "__main__":
    main()


