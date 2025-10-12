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

def monitor_and_cancel(client, results, resell_price=None):
    """
    Poll orders. When one fills, cancel the rest and place a resell.
    """
    filled = False
    while not filled:
        time.sleep(5)
        for contest_id, token_id, order_id, side, sz in results:
            try:
                order_info = client.get_order(order_id)
                status = order_info.get("status")
                print(f"[DEBUG] Order {order_id} | contest {contest_id} | token {token_id} | status={status}")

                if status == "filled" or status == "MATCHED":
                    print(f"[FILL] [{order_info.get('question', 'Unknown')}] | order {order_id} | side={side}")
                    filled = True
                    # cancel other orders
                    for cid, tid, oid, _, _ in results:
                        if oid != order_id:
                            try:
                                client.cancel(order_id=oid)
                                print(f"[CANCEL] Cancelled {oid}")
                            except Exception as ce:
                                print(f"[FAIL] Cancel {oid}", ce)
                    # resell
                    if resell_price is not None:
                        place_resell(
                            client,
                            token_id,
                            sz,
                            question=order_info.get("question", "Unknown"),
                            price=resell_price
                        )
                    else:
                        print(f"[INFO] Skipping resell for {order_info.get('question', 'Unknown')} (no resell_price set)")
                    break
            except Exception as e:
                print(f"[FAIL] Could not fetch order {order_id}", e)

    return True


def monitor_all(client, all_results):
    """
    Monitor all active orders across contests.
    If one fills, cancel the others in that contest and place resell.
    """
    active = {oid: (cid, tid, side, sz) for cid, tid, oid, side, sz in all_results}

    while active:
        time.sleep(5)
        to_remove = []

        for order_id, (contest_id, token_id, side, sz) in list(active.items()):
            try:
                order_info = client.get_order(order_id)
                status = order_info.get("status")
                print(f"[DEBUG] Order {order_id} | contest {contest_id} | token {token_id} | status={status}")

                if status == "filled" or status == "MATCHED":
                    print(f"[FILL] {contest_id} | Order {order_id} filled | token {token_id}")

                    # cancel siblings
                    for other_id, (ocid, otid, _, _) in list(active.items()):
                        if ocid == contest_id and other_id != order_id:
                            try:
                                client.cancel(order_id=other_id)
                                print(f"[CANCEL] {contest_id} | Cancelled {other_id}")
                                to_remove.append(other_id)
                            except Exception as ce:
                                print(f"[FAIL] Cancel {other_id}", ce)

                    # resell
                    place_resell(client, token_id, sz)

                    to_remove.append(order_id)

            except Exception as e:
                print(f"[FAIL] Could not fetch order {order_id}", e)

        for oid in to_remove:
            active.pop(oid, None)

    print("[DONE] All contests resolved.")




