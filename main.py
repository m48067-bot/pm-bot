import time
from auth import init_client
from markets import fetch_live_games, is_close_game
from trader import place_both_sides, monitor_and_cancel

def main():
    client = init_client()
    traded = set()  # track contests we already traded

    while True:
        games = fetch_live_games()
        qualified = [ (m, ev) for (m, ev) in games if is_close_game(ev) ]
        print(f"Qualified contests: {len(qualified)}")

        for m, ev in qualified:
            contest_id = m.get("id")
            if contest_id in traded:
                continue  # already traded this contest

            print(f"\n[TRADE] {m.get('question')} | Score {ev.get('score')} | Elapsed {ev.get('elapsed')}")
            results = place_both_sides(client, m, price=0.16, size=1.0)
            if results:
                done = monitor_and_cancel(client, results)
                if done:
                    traded.add(contest_id)  # mark contest as finished

        time.sleep(30)  # re-scan every 30s


if __name__ == "__main__":
    main()
