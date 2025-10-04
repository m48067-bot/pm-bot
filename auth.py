import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()

def init_client():
    host = os.getenv("HOST", "https://clob.polymarket.com")
    chain_id = int(os.getenv("CHAIN_ID", "137"))

    api_key = os.getenv("CLOB_API_KEY")
    api_secret = os.getenv("CLOB_SECRET")
    api_passphrase = os.getenv("CLOB_PASS_PHRASE")

    if not all([api_key, api_secret, api_passphrase]):
        raise RuntimeError("Missing API creds in env vars")

    client = ClobClient(
        host=host,
        key='b69862c9bb41c895d65f9d94ab536810a7b6033cbaf0281f5cfbb8fd875f6fff',           # ❌ no private key needed
        chain_id=chain_id,
        signature_type=2,   # ✅ API key signing
        funder='0xFc34EcAFb149004A4051bF17519C3c9dcF758E75',        # ❌ not needed for sig=2
    )

    client.set_api_creds(ApiCreds(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
    ))

    return client

