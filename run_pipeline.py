import warnings
warnings.filterwarnings("ignore")

# run_pipeline.py

from clob_ok import create_clob_client
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
import requests

# Step 1: fetch active markets from gamma API
def fetch_active_markets(limit=5):   # fetch more than 1 to avoid blanks
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": limit, "closed": "false"}
    r = requests.get(url, params=params, timeout=20, verify=False)
    r.raise_for_status()
    data = r.json()
    markets = data["data"] if isinstance(data, dict) else data
    return markets


# Step 2: get token IDs from conditionId using CLOB
def get_market_tokens(condition_id: str):
    client = create_clob_client()
    market = client.get_market(condition_id=condition_id)
    return market

# Step 3: dry run an order
def dryrun_order(token_id: str, side: str, price: float, size: int):
    client = create_clob_client()
    order_args = OrderArgs(
        price=price,
        size=size,
        side=side,
        token_id=token_id,
    )
    signed_order = client.create_order(order_args)
    print("\n=== DRY RUN ORDER ===")
    print(f"Side:   {side}")
    print(f"Price:  {price}")
    print(f"Size:   {size}")
    print(f"Token:  {token_id}")
    print(f"Signature: {signed_order.signature[:16]}...")

if __name__ == "__main__":
    markets = fetch_active_markets(limit=10)  # pull 10 to choose from

    # Step 1: pick the first market that actually has a conditionId
    m = next((m for m in markets if m.get("conditionId")), None)
    if not m:
        print("No markets with conditionId found!")
        exit()

    print("Picked market:", m.get("question"))
    cid = m.get("conditionId")
    print("Condition ID:", cid)

    # Step 2: get token IDs
    market_full = get_market_tokens(cid)
    tokens = market_full.get("tokens", [])
    for t in tokens:
        print(f"Outcome: {t['outcome']} | Token ID: {t['token_id']}")

    # Step 3: dry run on YES token
    yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
    if yes_token:
        dryrun_order(yes_token["token_id"], BUY, 0.05, 10)

