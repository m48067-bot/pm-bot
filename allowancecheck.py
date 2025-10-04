from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv()

# RPC + wallet
RPC = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")
ADDRESS = Web3.to_checksum_address(os.getenv("FUNDER"))

# USDC contract (Polygon)
USDC_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

# Polymarket CLOB Exchange contract (spender)
SPENDER = Web3.to_checksum_address("0x86C37afC09A3AfC69A1bc84f6eD68EAA8B16905C")

# Connect
w3 = Web3(Web3.HTTPProvider(RPC))
assert w3.is_connected(), "Polygon RPC not connected"

# ERC20 ABI fragment for allowance
erc20_abi = [
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "type": "function",
    }
]

usdc = w3.eth.contract(address=USDC_ADDRESS, abi=erc20_abi)

allowance = usdc.functions.allowance(ADDRESS, SPENDER).call()
print(f"Allowance for {ADDRESS} -> {SPENDER}: {allowance} USDC (raw units)")

# USDC has 6 decimals, so convert to "human" form
print(f"Allowance (human): {allowance / 1e6} USDC")
