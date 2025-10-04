from py_clob_client.client import ClobClient

host = "https://clob.polymarket.com"
private_key = 'b69862c9bb41c895d65f9d94ab536810a7b6033cbaf0281f5cfbb8fd875f6fff'
chain_id = 137  # Polygon Mainnet

# Initialize the client with private key
client = ClobClient(host, key=private_key, chain_id=chain_id)

api_key_data = client.create_api_key()

print(api_key_data)