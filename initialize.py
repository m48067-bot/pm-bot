import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()

host = os.getenv("host")
chain_id = int(os.getenv("chain_id"))
private_key = os.getenv("private_key")

creds = ApiCreds(
    api_key=os.getenv("CLOB_API_KEY"),
    api_secret=os.getenv("CLOB_SECRET"),
    api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
)

client = ClobClient(
    host,
    chain_id=chain_id,
    key=private_key,
    creds=creds,
    signature_type=2,
    funder=os.getenv("PROXY_ADDRESS"),
)
