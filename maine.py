import time
from auth import init_client
from markets import fetch_live_games, fetch_nfl_games_today, fetch_cfb_games_today, fetch_browns_game_only
from trader import place_both_sides, monitor_and_cancel, monitor_all


def main(test_mode=False, browns_mode=False):
    client = init_client()

    if browns_mode:
        print("=== Browns-only test mode ===")
        browns_games = fetch_browns_game_only()
        print(f"Found {len(browns_games)} Browns contests\n")

        for m, ev in browns_games:
            print(f"[BROWNS TEST] {m.get('question')}")
            results = place_both_sides(client, m, price=0.5, size=2.0)
            if results:
                monitor_all(client, results)
        return

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

    # --- LIVE trading loop ---
    traded = set()
    while True:
        live_games = fetch_live_games()
        print(f"Qualified contests: {len(live_games)}")

        for m, ev in live_games:
            contest_id = m.get("id")
            if contest_id in traded:
                continue

            print(f"\n[TRADE] {m.get('question')} | Score {ev.get('score')} | Period {ev.get('period')} | Elapsed {ev.get('elapsed')}")
            results = place_both_sides(client, m, price=0.16, size=35.0)
            if results:
                done = monitor_and_cancel(client, results)
                if done:
                    traded.add(contest_id)

        time.sleep(30)


if __name__ == "__main__":
    #main(test_mode=False)
    main(browns_mode=True)
