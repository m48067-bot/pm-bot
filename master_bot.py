import threading
import time

from ws_debug import start_trading_bot
from mrkets import redeem_all


def start_redeem_loop():
    print("Redeem loop started.")

    while True:
        try:
            redeem_all()
        except Exception as e:
            print("Redeem loop error:", e)

        time.sleep(30)


def main():
    print("Starting Polymarket Master Bot")

    trading_thread = threading.Thread(
        target=start_trading_bot,
        daemon=True
    )

    redeem_thread = threading.Thread(
        target=start_redeem_loop,
        daemon=True
    )

    trading_thread.start()
    redeem_thread.start()

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
