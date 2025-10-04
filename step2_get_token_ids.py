from clob_ok import create_clob_client

def get_market_tokens(condition_id: str):
    client = create_clob_client()
    market = client.get_market(condition_id=condition_id)

    print("Market:", market.get("question"))
    print("Condition ID:", condition_id)
    print("Tokens:")
    for t in market.get("tokens", []):
        print(f"   Outcome: {t.get('outcome')} | Token ID: {t.get('token_id')}")
    return market

if __name__ == "__main__":
    # Example condition ID you got from get_active_markets.py
    cid = "0x4319532e181605cb15b1bd677759a3bc7f7394b2fdf145195b700eeaedfd5221"
    get_market_tokens(cid)





