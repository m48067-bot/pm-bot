import os, time, hmac, hashlib, requests
from dotenv import load_dotenv
load_dotenv()

HOST = os.getenv("HOST", "https://clob.polymarket.com")
API_KEY = os.getenv("CLOB_API_KEY")
API_SECRET = os.getenv("CLOB_SECRET")
API_PASSPHRASE = os.getenv("CLOB_PASS_PHRASE")
FUNDER = os.getenv("FUNDER")

def sign_request(secret, timestamp, method, path, body=""):
    message = str(timestamp) + method + path + body
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def get_internal_balances():
    path = "/balances"
    url = HOST + path
    method = "GET"
    timestamp = str(int(time.time() * 1000))

    signature = sign_request(API_SECRET, timestamp, method, path)

    headers = {
        "POLY-API-KEY": API_KEY,
        "POLY-SIGNATURE": signature,
        "POLY-TIMESTAMP": timestamp,
        "POLY-PASSPHRASE": API_PASSPHRASE,
        "POLY-ADDRESS": FUNDER,
    }

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    print(get_internal_balances())
