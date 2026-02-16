import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.clob_types import BalanceAllowanceParams

load_dotenv()

host = os.getenv("HOST")
chain_id = int(os.getenv("CHAIN_ID"))
private_key = os.getenv("PRIVATE_KEY")

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










