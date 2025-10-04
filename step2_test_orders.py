# step2_test_orders.py

import requests, warnings
warnings.filterwarnings("ignore")

from clob_okk import create_clob_client
from py_clob_client.clob_types import OpenOrderParams

def test_open_orders():
    client = create_clob_client()
    # Fetch all open orders tied to your account
    open_orders = client.get_orders(OpenOrderParams())
    print(f"Found {len(open_orders)} open orders\n")
    for o in open_orders:
        print(o)

if __name__ == "__main__":
    test_open_orders()
