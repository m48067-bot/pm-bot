import os
import re
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

PRIVATE_KEY = os.getenv("private_key")
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
        params={"user": proxy_address, "sizeThreshold": 0},
        timeout=10,
    )

    positions = response.json()

    # Only try to redeem positions whose 5-min window has ended
    now = int(time.time())
    slugs = set()
    for p in positions:
        if float(p.get("size", 0)) <= 0:
            continue
        slug = p["slug"]
        # Extract timestamp from slug (e.g. btc-updown-5m-1771376100)
        try:
            ts = int(slug.rsplit("-", 1)[1])
            if ts + 300 < now:  # Only if 5-min window has fully ended
                slugs.add(slug)
        except (ValueError, IndexError):
            slugs.add(slug)  # Non-standard slug, try anyway

    print(f"Positions: {len(positions)} total, {len(slugs)} expired to redeem")

    if not slugs:
        return

    redeemed = 0
    for slug in slugs:

        try:
            event = requests.get(
                f"{GAMMA_API}/events/slug/{slug}",
                timeout=10,
            ).json()

            market = event["markets"][0]

            if market.get("umaResolutionStatus") != "resolved":
                continue

            condition_id = market.get("conditionId")
            if not condition_id:
                continue

            print(f"Redeeming: {slug}")

            tx = build_redeem_tx(condition_id)
            response = client.execute([tx])
            result = response.wait()

            if result:
                redeemed += 1
                tx_hash = result.get('transactionHash', 'unknown')[:16] if isinstance(result, dict) else 'ok'
                print(f"[REDEEMED] {slug} | tx={tx_hash}...")

            # Rate limit: wait between redeems
            time.sleep(10)

        except Exception as e:
            msg = str(e)
            # If quota exhausted, stop trying until reset
            if "429" in msg or "quota exceeded" in msg:
                match = re.search(r"resets in (\d+) seconds", msg)
                if match:
                    wait = int(match.group(1))
                    print(f"[REDEEM] Quota exhausted — waiting {wait//3600}h {(wait%3600)//60}m")
                    time.sleep(min(wait + 10, 3600))  # Wait up to 1 hour max per cycle
                else:
                    print("[REDEEM] Rate limited — waiting 10 min")
                    time.sleep(600)
                return  # Exit loop, try again next cycle
            else:
                print(f"[REDEEM ERR] {slug}: {e}")
                time.sleep(15)

    if redeemed:
        print(f"[REDEEM] Redeemed {redeemed} positions this cycle")
