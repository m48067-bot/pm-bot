from py_order_utils.builders.order_builder import OrderBuilder, Order
from py_order_utils.signer import Signer
from py_clob_client.clob_types import OrderType

import time

signer = Signer('b69862c9bb41c895d65f9d94ab536810a7b6033cbaf0281f5cfbb8fd875f6fff')

builder = OrderBuilder(exchange_address, CHAIN_ID, signer)

# Build the Order object
order = Order(
    maker=signer.address(),
    signer=signer.address(),
    taker="0x0000000000000000000000000000000000000000",
    tokenId=int(TOKEN_ID),
    makerAmount=50000,
    takerAmount=5000000,
    expiration=int(time.time()) + 3600,   # valid for 1h
    nonce=int(time.time()),               # crude but unique
    feeRateBps=0,
    side=0,                               # 0 = buy, 1 = sell
    signatureType=0
)

# Sign it
signed = builder.sign_order(order)

print("=== SIGNED ORDER ===")
print(signed)

# Post it
resp = client.post_order(signed, OrderType.GTC)
print("=== ORDER RESPONSE ===")
print(resp)

