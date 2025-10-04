# step_allowances.py
from web3 import Web3
from web3.constants import MAX_INT
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
RPC_URL = os.getenv("POLYGON_RPC")  # e.g. Alchemy or Infura endpoint
PRIV_KEY = os.getenv("PK")
PUB_KEY = os.getenv("PBK")
CHAIN_ID = 137

# Contracts
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

# Spenders that need approval
SPENDER_ADDRESSES = [
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # Main exchange
    "0xC5d563A36AE78145C45a50134d48A1215220f80a",  # Neg risk markets
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",  # Neg risk adapter
]

# ABIs
ERC20_APPROVE = """[{"constant": false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"}]"""
ERC1155_SET_APPROVAL = """[{"inputs":[{"internalType":"address","name":"operator","type":"address"},{"internalType":"bool","name":"approved","type":"bool"}],"name":"setApprovalForAll","outputs":[],"stateMutability":"nonpayable","type":"function"}]"""

# --- Setup ---
w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_APPROVE)
ctf = w3.eth.contract(address=CTF_ADDRESS, abi=ERC1155_SET_APPROVAL)


def send_tx(txn):
    signed = w3.eth.account.sign_transaction(txn, private_key=PRIV_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, 600)
    return receipt


def approve_all():
    nonce = w3.eth.get_transaction_count(PUB_KEY)

    for spender in SPENDER_ADDRESSES:
        print(f"\nApproving spender {spender}")

        # USDC approval (max int)
        tx1 = usdc.functions.approve(spender, 2**256 - 1).build_transaction({
            "chainId": CHAIN_ID,
            "from": PUB_KEY,
            "nonce": nonce,
            "gas": 100000,
            "maxFeePerGas": w3.to_wei("100", "gwei"),
            "maxPriorityFeePerGas": w3.to_wei("30", "gwei"),
        })
        receipt1 = send_tx(tx1)
        print("USDC approval:", receipt1.transactionHash.hex())
        nonce += 1

        # CTF approval (setApprovalForAll)
        tx2 = ctf.functions.setApprovalForAll(spender, True).build_transaction({
            "chainId": CHAIN_ID,
            "from": PUB_KEY,
            "nonce": nonce,
            "gas": 100000,
            "maxFeePerGas": w3.to_wei("100", "gwei"),
            "maxPriorityFeePerGas": w3.to_wei("30", "gwei"),
        })
        receipt2 = send_tx(tx2)
        print("CTF approval:", receipt2.transactionHash.hex())
        nonce += 1


if __name__ == "__main__":
    print("Approving all required spenders...")
    approve_all()
    print("Done ✅")
