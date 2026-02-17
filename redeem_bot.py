import time
from mrkets import redeem_all

if __name__ == "__main__":
    print("Redeem bot started")
    while True:
        try:
            redeem_all()
        except Exception as e:
            print("Redeem error:", e)

        time.sleep(30)
