# step3_post_orders.py
from clob_okk import create_clob_client
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

def main():
    client = create_clob_client()   # <-- create it here

    print("Client host:", client.host)

    # Example order
    token_id = "94055277933814664459688215103102515012212800920616003541729407298775136373506"
    order = OrderArgs(
        token_id=token_id,
        price=0.01,
        size=1.0,
        side=BUY,
    )

    signed_order = client.create_order(order)
    resp = client.post_order(signed_order, OrderType.GTC)

    print("Response:", resp)


if __name__ == "__main__":
    main()

