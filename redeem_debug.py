import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

RPC_URL = "https://polygon-rpc.com"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET = Web3.to_checksum_address(os.getenv("WALLET_ADDRESS"))

# Polymarket Conditional Tokens contract (Polygon)
CTF_ADDRESS = Web3.to_checksum_address("0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce")

# USDC on Polygon
USDC_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

# Minimal ABI for redeemPositions
CTF_ABI = [{
    "inputs": [
        {"internalType": "address", "name": "collateralToken", "type": "address"},
        {"internalType": "bytes32", "name": "parentCollectionId", "type": "bytes32"},
        {"internalType": "bytes32", "name": "conditionId", "type": "bytes32"},
        {"internalType": "uint256[]", "name": "indexSets", "type": "uint256[]"}
    ],
    "name": "redeemPositions",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
}]

w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)

def redeem(condition_id):

    nonce = w3.eth.get_transaction_count(WALLET)

    # Polymarket uses indexSets [1,2] for binary
    index_sets = [1, 2]

    tx = contract.functions.redeemPositions(
        USDC_ADDRESS,
        b'\x00' * 32,        # parentCollectionId = 0x0
        bytes.fromhex(condition_id[2:]),
        index_sets
    ).build_transaction({
        'from': WALLET,
        'nonce': nonce,
        'gas': 500000,
        'gasPrice': w3.to_wei('50', 'gwei')
    })

    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)

    print("Redeem TX sent:", tx_hash.hex())

if __name__ == "__main__":

    condition_id = input("Enter conditionId to redeem: ").strip()
    redeem(condition_id)
