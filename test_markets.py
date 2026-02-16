import time
from initialize import client

def main():

    print("Fetching positions...")
    positions = client.get_positions()

    if not positions:
        print("No positions found.")
        return

    redeemable_positions = []

    for p in positions:
        # Print everything once so you see structure
        print("\nPOSITION:")
        for k, v in p.items():
            print(f"{k}: {v}")

        if p.get("redeemable", False):
            redeemable_positions.append(p)

    if not redeemable_positions:
        print("\nNo redeemable positions found.")
        return

    print(f"\nFound {len(redeemable_positions)} redeemable positions.")

    for p in redeemable_positions:
        condition_id = p.get("conditionId")
        print(f"\nRedeeming condition: {condition_id}")

        try:
            tx = client.redeem(condition_id)
            print("Redeem TX sent:", tx)

        except Exception as e:
            print("Redeem failed:", e)

    print("\nDone.")

if __name__ == "__main__":
    main()
