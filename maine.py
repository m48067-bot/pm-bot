import time
import threading
from auth import init_client
from markets import fetch_live_games, fetch_nfl_games_today, fetch_cfb_games_today, fetch_browns_game_only
from trader import place_both_sides, monitor_and_cancel, monitor_all
from concurrent.futures import ThreadPoolExecutor
from markets import fetch_cfb_second_quarter  # we'll add this helper in markets.py


def main(test_mode=False, browns_mode=False):
    client = init_client()

    if browns_mode:
        traded = set()
        while True:
            browns_games = fetch_browns_game_only()
            for m, ev in browns_games:
                contest_id = m.get("id")
                if contest_id in traded:
                    continue

                results = place_both_sides(client, m, price=0.06, size=5.0)
                if results:
                    done = monitor_and_cancel(client, results)
                    if done:
                        traded.add(contest_id)

            time.sleep(30)

    if test_mode:
        # --- NFL today ---
        nfl_games = fetch_nfl_games_today()
        print(f"NFL contests today: {len(nfl_games)}")

        # --- CFB today ---
        cfb_games = fetch_cfb_games_today()
        print(f"CFB contests today: {len(cfb_games)}")

        all_results = []

        # Place NFL positions
        for m in nfl_games:
            print(f"\n[TRADE-TEST NFL] {m.get('question')}")
            results = place_both_sides(client, m, price=0.16, size=7.0)
            all_results.extend(results)

        # Place CFB positions
        for m in cfb_games:
            print(f"\n[TRADE-TEST CFB] {m.get('question')}")
            results = place_both_sides(client, m, price=0.16, size=7.0)
            all_results.extend(results)

        if all_results:
            monitor_all(client, all_results)
        return

    # --- LIVE trading loop (multi-threaded) ---
    traded = set()
    MAX_WORKERS = 8  # number of contests to trade simultaneously
    ENTRY_PRICE = 0.34
    ENTRY_SIZE = 5.0

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def handle_contest(client, m, ev):
        """Handle one contest from start to finish in its own thread."""
        cid = m.get("id")
        question = m.get("question")
        score = ev.get("score")
        period = ev.get("period")
        elapsed = ev.get("elapsed")

        print(f"\n[{cid}] Launching handler | {question} | Score {score} | Period {period} | Elapsed {elapsed}")
        results = place_both_sides(client, m, price=ENTRY_PRICE, size=ENTRY_SIZE)
        if results:
            monitor_and_cancel(client, results)
        print(f"[{cid}] Finished thread for {question}")

    while True:
        try:
            # --- Fetch CFB games currently in 2Q ---
            games = fetch_cfb_second_quarter()
            print(f"Found {len(games)} contests currently in 2Q.")

            for m, ev in games:
                cid = m.get("id")
                if cid in traded:
                    continue

                # Submit each qualifying contest to thread pool
                executor.submit(handle_contest, client, m, ev)
                traded.add(cid)
                print(f"[{cid}] Submitted to thread pool.")

            # small delay before next refresh
            time.sleep(25)

        except Exception as e:
            print("[ERROR in main loop]", e)
            time.sleep(10)


if __name__ == "__main__":
    main(test_mode=False)
    # main(browns_mode=True)

