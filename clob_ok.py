import os
import socket
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON

socket.AF_INET
socket.has_ipv6 = False

HOST = "https://clob.polymarket.com"

load_dotenv()

def create_clob_client() -> ClobClient:
    priv_key = os.getenv("PK")
    if not priv_key:
        raise ValueError("Missing PK in .env file!")

    # Load API creds if present
    creds = None
    if os.getenv("CLOB_API_KEY"):
        creds = ApiCreds(
            api_key=os.getenv("CLOB_API_KEY"),
            api_secret=os.getenv("CLOB_SECRET"),
            api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
        )

    return ClobClient(
        host=HOST,
        key=priv_key,
        chain_id=POLYGON,
        creds=creds,  # <- now supports posting orders
    )

if __name__ == "__main__":
    print("PK from env:", os.getenv("PK"))
    print("PBK from env:", os.getenv("PBK"))
    c = create_clob_client()
    print("OK:", c.get_ok())
    print("Server time:", c.get_server_time())

