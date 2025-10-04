# step1_check_connection.py
from clob_okk import create_clob_client

client = create_clob_client()

print("OK check:", client.get_ok())
print("Server time:", client.get_server_time())
