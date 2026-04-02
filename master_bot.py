import threading
import time
import traceback

from ws_debug import start_trading_bot
from mrkets import redeem_all


def start_redeem_loop():
    """Redeem resolved positions every 30 seconds, never crash."""
    print("Redeem loop started")
    while True:
        try:
            redeem_all()
        except Exception as e:
            print(f"[REDEEM ERR] {e}")
            traceback.print_exc()
        time.sleep(30)


def main():
    print("="*40)
    print("POLYMARKET MASTER BOT")
    print("="*40)

    # Start redeem in background
    threading.Thread(target=start_redeem_loop, daemon=True).start()

    # Run trading bot in main thread — its internal while-loop
    # handles reconnects, and the watchdog calls os._exit(1) if
    # the websocket goes silent for 60s, which lets systemd restart us.
    start_trading_bot()


if __name__ == "__main__":
    main()
