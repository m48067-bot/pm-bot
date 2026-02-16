import asyncio
import websockets
import json

TOKEN_ID = "79797384925980301204291764463143222887700240966082867554945455886769829331145"
# Replace with a current YES token

async def main():
    uri = "wss://clob.polymarket.com/ws"

    async with websockets.connect(uri) as websocket:
        print("Connected to Polymarket WebSocket")

        subscribe_msg = {
            "type": "subscribe",
            "channel": "book",
            "token_id": TOKEN_ID
        }

        await websocket.send(json.dumps(subscribe_msg))
        print("Subscribed to book updates")

        while True:
            message = await websocket.recv()
            data = json.loads(message)

            if "bids" in data and "asks" in data:
                best_bid = float(data["bids"][0]["price"]) if data["bids"] else None
                best_ask = float(data["asks"][0]["price"]) if data["asks"] else None

                print(f"Best Bid: {best_bid} | Best Ask: {best_ask}")

asyncio.run(main())
