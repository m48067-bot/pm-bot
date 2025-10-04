import time
from auth import init_client
from markets import (
    fetch_live_games, is_close_game, fetch_nfl_games_today,
    fetch_cfb_games_today, is_cfb_clutch_game, _fetch_today_games
)
from trader import place_both_sides, monitor_and_cancel, monitor_all


def main(test_mode=False):
    client = init_client()

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

        # Track fills/cancels/resells
        if all_results:
            monitor_all(client, all_results)

        return  # exit after test run

    # --- LIVE trading loop (NFL + CFB clutch) ---
    traded = set()
    while True:
        # NFL live games
        nfl_games = fetch_live_games()
        nfl_clutch = [(m, ev) for (m, ev) in nfl_games if is_close_game(ev)]

        # CFB live games
        cfb_live = _fetch_today_games(100351, "cfb")  # raw pull
        cfb_clutch = [(m, ev) for (m, ev) in cfb_live if is_cfb_clutch_game(ev)]

        # Apply the bestBid filter
        qualified = [
            (m, ev) for (m, ev) in (nfl_clutch + cfb_clutch)
            if has_reasonable_spread(m)
        ]

        print(f"Qualified contests: {len(qualified)} (after bestBid filter)")

        for m, ev in qualified:
            contest_id = m.get("id")
            if contest_id in traded:
                continue

            print(f"\n[TRADE] {m.get('question')} | Score {ev.get('score')} | Period {ev.get('period')} | Elapsed {ev.get('elapsed')}")
            results = place_both_sides(client, m, price=0.16, size=7.0)
            if results:
                done = monitor_and_cancel(client, results)
                if done:
                    traded.add(contest_id)

        time.sleep(30)


if __name__ == "__main__":
    main(test_mode=True)   # ✅ flip to False for live trading
