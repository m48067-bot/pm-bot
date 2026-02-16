import os
import time
import requests
from dotenv import load_dotenv
from web3 import Web3

from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.models import SafeTransaction, OperationType
from py_builder_signing_sdk.config import BuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds

# ================= ENV =================

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLY_BUILDER_API_KEY = os.getenv("POLY_BUILDER_API_KEY")
POLY_BUILDER_SECRET = os.getenv("POLY_BUILDER_SECRET")
POLY_BUILDER_PASSPHRASE = os.getenv("POLY_BUILDER_PASSPHRASE")

if not all([
    PRIVATE_KEY,
    POLY_BUILDER_API_KEY,
    POLY_BUILDER_SECRET,
    POLY_BUILDER_PASSPHRASE
]):
    raise ValueError("Missing environment variables")

# ================= RELAYER CLIENT =================

builder_config = BuilderConfig(
    local_builder_creds=BuilderApiKeyCreds(
        key=POLY_BUILDER_API_KEY,
        secret=POLY_BUILDER_SECRET,
        passphrase=POLY_BUILDER_PASSPHRASE,
    )
)

client = RelayClient(
    "https://relayer-v2.polymarket.com",
    137,
    PRIVATE_KEY,
    builder_config
)

# ================= HARD CODED PROXY =================

proxy_address = "0x7b9196eF079a8297BCCdd2Eb42c604255ED64Ae4"
print("Scanning proxy:", proxy_address)

# ================= CONSTANTS =================

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

CTF = Web3.to_checksum_address("0x4d97dcd97ec945f40cf65f87097ace5ea0476045")
USDC = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
ZERO_BYTES32 = "0x" + "00" * 32

# ================= WEB3 CONTRACT =================

w3 = Web3()

redeem_abi = [{
    "name": "redeemPositions",
    "type": "function",
    "inputs": [
        {"name": "collateralToken", "type": "address"},
        {"name": "parentCollectionId", "type": "bytes32"},
        {"name": "conditionId", "type": "bytes32"},
        {"name": "indexSets", "type": "uint256[]"}
    ],
    "outputs": []
}]

contract = w3.eth.contract(address=CTF, abi=redeem_abi)

# ================= BUILD SAFE TRANSACTION =================

def build_redeem_tx(condition_id: str):

    data = contract.encode_abi(
        abi_element_identifier="redeemPositions",
        args=[
            USDC,
            ZERO_BYTES32,
            condition_id,
            [1, 2]
        ]
    )

    return SafeTransaction(
        to=CTF,
        operation=OperationType.Call,
        data=data,
        value="0"
    )

# ================= REDEEM LOGIC =================

def redeem_all():

    print("\nScanning wallet...")

    response = requests.get(
        f"{DATA_API}/positions",
        params={"user": proxy_address, "sizeThreshold": 0}
    )

    positions = response.json()

    print("Positions returned:", len(positions))

    slugs = {p["slug"] for p in positions if float(p.get("size", 0)) > 0}
    print("Detected slugs:", slugs)

    if not slugs:
        return

    for slug in slugs:

        try:
            print("\nChecking slug:", slug)

            event = requests.get(
                f"{GAMMA_API}/events/slug/{slug}"
            ).json()

            market = event["markets"][0]

            print("UMA Status:", market.get("umaResolutionStatus"))

            if market.get("umaResolutionStatus") != "resolved":
                continue

            condition_id = market.get("conditionId")
            print("Condition ID:", condition_id)

            if not condition_id:
                continue

            print("Redeeming:", slug)

            tx = build_redeem_tx(condition_id)

            response = client.execute([tx])
            result = response.wait()

            if result:
                print("Raw result:", result)


        except Exception as e:
            print("Error processing", slug, e)

# ================= LOOP =================


