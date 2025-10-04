# step0_generate_api_keys.py
import os
from dotenv import set_key, load_dotenv
from clob_okk import create_clob_client

def generate_api_keys():
    env_path = ".env"
    load_dotenv(env_path)

    # Debug what we are loading
    pk = os.getenv("PK")
    pbk = os.getenv("PBK")

    print("🔍 Debugging environment variables:")
    if pk:
        print(f"  PK loaded: {pk[:6]}...{pk[-4:]} (length {len(pk)})")
    else:
        print("  PK is MISSING or empty ❌")

    if pbk:
        print(f"  PBK loaded: {pbk} (length {len(pbk)})")
    else:
        print("  PBK is MISSING or empty ❌")

    # Build client
    client = create_clob_client()

    print("\n⚡ Attempting to create API key...")
    try:
        creds = client.create_api_key()
    except Exception as e:
        print("❌ Failed to create API key:", repr(e))
        return

    print("✅ API key successfully created")

    # Debug print creds
    print("  api_key:", creds.api_key[:6] + "..." + creds.api_key[-4:])
    print("  api_secret:", creds.api_secret[:6] + "..." + creds.api_secret[-4:])
    print("  api_passphrase:", creds.api_passphrase[:6] + "..." + creds.api_passphrase[-4:])

    # Write to .env
    set_key(env_path, "CLOB_API_KEY", creds.api_key)
    set_key(env_path, "CLOB_SECRET", creds.api_secret)
    set_key(env_path, "CLOB_PASS_PHRASE", creds.api_passphrase)

    print("\n✅ API keys written to .env")

if __name__ == "__main__":
    generate_api_keys()


