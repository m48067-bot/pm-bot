# place_order_final.py
import os
from dotenv import load_dotenv
import requests
import certifi

# --- Cloudflare patch ---
import py_clob_client.http_helpers.helpers as helpers

session = requests.Session()
session.verify = certifi.where()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://polymarket.com/",
    "Origin": "https://polymarket.com",
})

def patched_get(url, headers=None, params=None):
    merged_headers = session.headers.copy()
    if headers:
        merged_headers.update(headers)
    resp = session.get(url, headers=merged_headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

import json

def patched_post(url, headers=None, data=None):
    merged_headers = session.headers.copy()
    if headers:
        merged_headers.update(headers)

    merged_headers["Content-Type"] = "application/json"

    # If data is dict-like, send with `json=...` instead of `data=...`
    if isinstance(data, (dict, list)):
        resp = session.post(url, headers=merged_headers, json=data, timeout=30)
    else:
        resp = session.post(url, headers=merged_headers, data=data, timeout=30)

    print("\n=== DEBUG POST ===")
    print("URL:", url)
    print("HEADERS:", merged_headers)
    print("BODY:", data)

    resp.raise_for_status()
    return resp.json()

helpers.get = patched_get
helpers.post = patched_post

# --- Polymarket imports ---
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
from py_clob_client.order_builder.constants import BUY
from py_clob_client.clob_types import asdict

# --- Load env ---
load_dotenv()

HOST = os.getenv("HOST", "https://clob.polymarket.com")
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))
PRIVATE_KEY = os.getenv("PK")
FUNDER = os.getenv("FUNDER")      # your Polygon wallet address
TOKEN_ID = os.getenv("TOKEN_ID")  # the tokenId you want to trade

API_KEY = os.getenv("CLOB_API_KEY")
API_SECRET = os.getenv("CLOB_SECRET")
API_PASSPHRASE = os.getenv("CLOB_PASS_PHRASE")

if not all([PRIVATE_KEY, FUNDER, TOKEN_ID, API_KEY, API_SECRET, API_PASSPHRASE]):
    raise RuntimeError("Missing env vars: PK, FUNDER, TOKEN_ID, or API creds")

# --- Init ClobClient ---
client = ClobClient(
    host=HOST,
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID,
    signature_type=0,  # 0 = EOA
    funder=FUNDER
)

# Attach API creds
client.set_api_creds(ApiCreds(
    api_key=API_KEY,
    api_secret=API_SECRET,
    api_passphrase=API_PASSPHRASE
))

# --- Build + sign order ---
order_args = OrderArgs(
    price=0.01,        # $0.01
    size=10.0,          # 5 contracts
    side=BUY,          # buy side
    token_id=TOKEN_ID
)

signed_order = client.create_order(order_args)

# --- Place order (GTC) ---
print("\n=== SIGNED ORDER ===")
print(asdict(signed_order))

resp = client.post_order(signed_order, OrderType.GTC)

print("\n=== ORDER RESPONSE ===")
print(resp)
