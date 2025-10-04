import warnings
warnings.filterwarnings("ignore")

# step5_dryrun_order.py

from clob_ok import create_clob_client
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

def dryrun_order(token_id: str, side: str, price: float, size: int):
    client = create_clob_client()

    # Build the order args
    order_args = OrderArgs(
        price=price,
        size=size,
        side=side,
        token_id=token_id,
    )

    # Create the signed order locally (no post)
    signed_order = client.create_order(order_args)

    print("=== DRY RUN ORDER ===")
    print(f"Side:   {side}")
    print(f"Price:  {price}")
    print(f"Size:   {size}")
    print(f"Token:  {token_id}")
    print("\nSigned order JSON:\n", signed_order)

if __name__ == "__main__":
    # Example token_id from your step2 script
    yes_token = "60487116984468020978247225474488676749601001829886755968952521846780452448915"
    dryrun_order(yes_token, BUY, 0.05, 10)

