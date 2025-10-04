import os, socket, json
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

# force IPv4
socket.has_ipv6 = False

load_dotenv()
KEY = os.getenv("PRIVATE_KEY")
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

def main():
    if not KEY:
        raise SystemExit("No PRIVATE_KEY in .env")

    client = ClobClient(HOST, key=KEY, chain_id=CHAIN_ID, signature_type=0)

    print("Requesting API credentials from CLOB...")
    creds = client.create_or_derive_api_creds()
    print("API Key:", creds.api_key)
    print("API Secret:", creds.api_secret)
    print("API Passphrase:", creds.api_passphrase)


if __name__ == "__main__":
    main()

