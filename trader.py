import json
import time
from py_clob_client.clob_types import OrderArgs, OrderType, PostOrdersArgs
from py_clob_client.order_builder.constants import BUY, SELL


def place_both_sides(client, market, price=0.16, size=10.0):
    """
    Place BUY orders on both token_ids in one batch.
    Returns list of (contest_id, token_id, order_id, side, size).
    """
    token_ids = market.get("clobTokenIds", [])
    question = market.get("question", "Unknown")
    contest_id = market.get("id")

    if isinstance(token_ids, str):
        token_ids = json.loads(token_ids)

    post_orders_payload = []
    print(f"\n[DEBUG] Market: {question}")

    for token_id in token_ids:
        try:
            order_args = OrderArgs(
                price=price,
                size=size,
                side=BUY,
                token_id=str(token_id),
            )
            signed_order = client.create_order(order_args)
            post_orders_payload.append(
                PostOrdersArgs(order=signed_order, orderType=OrderType.GTC)
            )
        except Exception as e:
            print(f"[FAIL] Could not build order | token_id={token_id}")
            print("Reason:", e, "\n")

    try:
        resp = client.post_orders(post_orders_payload)
        results = []
        for i, r in enumerate(resp):
            token_id = token_ids[i]
            order_id = r.get("orderID")
            if order_id:
                print(f"[OK] [{question}] Placed BUY | token_id={token_id} | order_id={order_id} | size={size}")
                results.append((contest_id, token_id, order_id, BUY, size))
            else:
                print(f"[FAIL] [{question}] Order failed | token_id={token_id}")
        return results

    except Exception as e:
        print(f"[FAIL] Could not place batch orders for {question}")
        print("Reason:", e, "\n")
        return []


def place_resell(client, token_id, size, question="Unknown Contest", price=0.92, retries=20, delay=5):
    """
    Try to place a SELL order for the filled token at given price/size.
    Retries while waiting for Polymarket's allowance ledger to sync.
    Includes detailed debug logging.
    """
    token_id = str(token_id)

    for attempt in range(1, retries + 1):
        print(f"\n[DEBUG] Attempt {attempt}/{retries} | token_id={token_id} | size={size} | price={price}")
        try:
            # Build and sign order
            order_args = OrderArgs(
                price=price,
                size=size,
                side=SELL,
                token_id=token_id,
            )
            signed_order = client.create_order(order_args)
            print(f"[DEBUG] Built SELL order struct: {signed_order}")

            # Try posting it
            resp = client.post_order(signed_order)
            print(f"[DEBUG] Raw response: {resp}")

            order_id = resp.get("orderID") if isinstance(resp, dict) else None

            if order_id:
                print(f"[RESALE OK] [{question}] | token {token_id} | order {order_id} | size={size} @ {price}")
                return True
            else:
                print(f"[FAIL] No orderID returned (resp={resp}) on attempt {attempt}/{retries}")

        except Exception as e:
            msg = str(e)
            if "not enough balance" in msg or "allowance" in msg:
                print(f"[WAIT] Allowance/balance not ready yet (attempt {attempt}/{retries})... retrying in {delay}s")
                time.sleep(delay)
                continue
            else:
                print(f"[FAIL] Unexpected error posting SELL for token {token_id}: {e}")
                return False

        time.sleep(delay)

    print(f"[FAIL] Exhausted {retries} retries (~{retries * delay}s total) for SELL token {token_id}")
    return False

def monitor_and_cancel(client, results, resell_price=None, cancel_others=False):
    """
    Monitors orders until one fills, cancels, or the market is no longer live.
    - Stops if market disappears from live list or all orders are gone.
    - Optionally cancels other side and/or resells filled token.
    """
    filled = False
    tracked = {r[2]: r for r in results}  # order_id -> tuple
    league = ""

    # --- Try to infer league (NBA vs NFL) once ---
    if results:
        try:
            order_info = client.get_order(results[0][2])
            if isinstance(order_info, dict):
                slug = (order_info.get("slug") or "").lower()
                question = (order_info.get("question") or "").lower()
                if "nba" in slug or "nba" in question:
                    league = "nba"
        except Exception:
            pass

    print(f"[MONITOR] Tracking {len(tracked)} orders | league={league or 'unknown'}")

    refresh_counter = 0
    live_ids = set()

    while tracked and not filled:
        time.sleep(5)
        refresh_counter += 5

        # --- Periodically refresh live markets (every 15s) ---
        if refresh_counter >= 15:
            refresh_counter = 0
            try:
                if league == "nba":
                    live_games = fetch_live_nba_games()
                else:
                    live_games = fetch_live_games()
                live_ids = {m.get("id") for m, _ in live_games}
            except Exception as e:
                print(f"[WARN] Could not refresh live list: {e}")
                live_ids = set()

        # --- Stop monitoring if market no longer active ---
        if not tracked:
            print("[INFO] No active orders left — exiting monitor.")
            return False

        first_cid = next(iter(tracked.values()))[0]
        if live_ids and first_cid not in live_ids:
            print(f"[END] Market {first_cid} no longer live or marked closed — exiting monitor.")
            return False

        # --- Check each tracked order ---
        for order_id, (contest_id, token_id, _, side, sz) in list(tracked.items()):
            try:
                info = client.get_order(order_id)
                if not info or not isinstance(info, dict):
                    print(f"[INFO] Order {order_id} invalid/removed — stop tracking.")
                    tracked.pop(order_id, None)
                    continue

                status = (info.get("status") or "").lower()
                question = info.get("question", "Unknown")

                if status in ("filled", "matched"):
                    print(f"[FILL] [{question}] | order {order_id} | side={side}")
                    filled = True

                    if cancel_others:
                        for oid in list(tracked.keys()):
                            if oid != order_id:
                                try:
                                    client.cancel(order_id=oid)
                                    print(f"[CANCEL] Cancelled sibling {oid}")
                                except Exception as ce:
                                    print(f"[FAIL] Cancel {oid}: {ce}")

                    if resell_price is not None:
                        trader.place_resell(client, token_id, sz, question=question, price=resell_price)
                    return True

                if status in ("cancelled", "canceled", "expired"):
                    print(f"[INFO] [{question}] order {order_id} canceled/expired.")
                    tracked.pop(order_id, None)

            except Exception as e:
                msg = str(e)
                if "429" in msg:
                    print(f"[RATE LIMIT] Pausing 10s due to 429 error.")
                    time.sleep(10)
                else:
                    print(f"[FAIL] Could not check order {order_id}: {e}")

    print("[INFO] Monitor exiting cleanly (no active or filled orders).")
    return False



