import os
from dotenv import load_dotenv
from eth_account import Account

load_dotenv()
KEY = os.getenv("PRIVATE_KEY")

if not KEY:
    raise SystemExit("No PRIVATE_KEY in .env")

acct = Account.from_key(KEY)
print("Derived address from your key:", acct.address)
