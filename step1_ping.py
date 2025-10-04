from py_clob_client.client import ClobClient
import json

HOST = "https://clob.polymarket.com"

def main():
    c = ClobClient(HOST)  # no auth needed for reads

    # 1) Health check + server time
    print("OK:", c.get_ok())
    print("Server time:", c.get_server_time())

    # 2) Pull a tiny slice of markets (read-only)
    mkts = c.get_simplified_markets()
    data = mkts.get("data", [])
    print("Markets returned:", len(data))
    if data:
        first = {
            "question": data[0].get("question"),
            "slug": data[0].get("slug"),
            "tokens_sample": [
                {"outcome": t.get("outcome"), "token_id": t.get("token_id"), "price": t.get("price")}
                for t in (data[0].get("tokens") or [])[:2]
            ],
        }
        print(json.dumps(first, indent=2))

if __name__ == "__main__":
    main()
