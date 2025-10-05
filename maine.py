import time
import threading
from auth import init_client
from markets import fetch_live_games, fetch_nfl_games_today, fetch_cfb_games_today, fetch_browns_game_only
from trader import place_both_sides, monitor_and_cancel, monitor_all


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
    while True:
        live_games = fetch_live_games()
        print(f"Qualified contests: {len(live_games)}")

        for m, ev in live_games:
            contest_id = m.get("id")
            if contest_id in traded:
                continue

            question = m.get("question")
            score = ev.get("score")
            period = ev.get("period")
            elapsed = ev.get("elapsed")

            print(f"\n[{contest_id}] [TRADE] {question} | Score {score} | Period {period} | Elapsed {elapsed}")
            results = place_both_sides(client, m, price=0.16, size=35.0)

            if results:
                # Launch a background thread to monitor and manage fills for this contest
                t = threading.Thread(target=monitor_and_cancel, args=(client, results), name=f"contest_{contest_id}")
                t.daemon = True  # ensures threads close automatically if main script stops
                t.start()

                # Mark contest as traded so we don’t re-enter
                traded.add(contest_id)
                print(f"[{contest_id}] [THREAD] Started monitoring thread for {question}")

        time.sleep(30)


if __name__ == "__main__":
    main(test_mode=False)
    # main(browns_mode=True)

