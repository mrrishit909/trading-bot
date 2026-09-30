"""
Order-fill confirmation — shared by the stock robot (step10) and the crypto
robot (step12).

The bug this fixes: a market order almost always fills, but Alpaca's fill
*confirmation* can lag several seconds (worst at the market open). The old code
polled for ~12 seconds, then gave up and wrote "not_filled" to the diary — even
though the order filled a moment later. That silently dropped real round trips
from the record (e.g. ORCL +9.6% on 2026-09-08 never got logged), so the
scoreboard and the daily review were grading an incomplete history.

`confirm_fill` polls longer, keeps checking after the nominal timeout, treats a
partial fill as a fill, and — for a position-closing sell — double-checks that
the position actually cleared before it will admit defeat. It only returns
"not_filled" when the order reaches a terminal non-filled state (canceled /
rejected / expired) with zero shares filled.
"""

import time

_TERMINAL_BAD = ("canceled", "cancelled", "rejected", "expired", "done_for_day", "stopped")


def _s(order):
    """Order status as a lowercase plain string ('filled', 'accepted', ...)."""
    return str(getattr(order, "status", "")).split(".")[-1].lower()


def _filled_qty(order):
    try:
        return float(order.filled_qty or 0)
    except (TypeError, ValueError):
        return 0.0


def _result(order):
    return ("filled", float(order.filled_avg_price), _filled_qty(order), str(order.id))


def confirm_fill(trading, order, *, want_qty=None, symbol=None, price_fn=None,
                 patience_s=30, grace_s=20):
    """Wait for `order` to fill.

    Returns (status, fill_price, filled_qty, order_id):
      - ("filled", price, qty, id)      normal / partial fill
      - ("not_filled", None, None, id)  order terminally did not fill

    want_qty / symbol / price_fn are optional and only used to salvage a
    position-closing sell whose confirmation never arrived: if the position is
    gone, the sell worked, and we fall back to `price_fn(symbol)` for the diary
    price if Alpaca still hasn't given us `filled_avg_price`.
    """
    oid = order.id
    deadline = time.time() + patience_s
    while time.time() < deadline:
        time.sleep(1)
        order = trading.get_order_by_id(oid)
        st = _s(order)
        if st == "filled" and order.filled_avg_price:
            return _result(order)
        if st in _TERMINAL_BAD:
            break

    # past the nominal timeout — keep checking with backoff. Market orders that
    # are merely slow to confirm land here and resolve within a few more seconds.
    grace_deadline = time.time() + grace_s
    delay = 1.5
    while time.time() < grace_deadline:
        time.sleep(delay)
        delay = min(delay * 1.5, 5)
        order = trading.get_order_by_id(oid)
        st = _s(order)
        if st == "filled" and order.filled_avg_price:
            return _result(order)
        if _filled_qty(order) > 0 and order.filled_avg_price:
            return _result(order)                       # partial fill counts
        if st in _TERMINAL_BAD and _filled_qty(order) == 0:
            break

    # last resort: did a closing sell actually clear the position even though we
    # never saw the confirmation?
    if symbol is not None:
        try:
            trading.get_open_position(symbol)
            still_held = True
        except Exception:
            still_held = False
        if not still_held:
            fill = float(order.filled_avg_price) if order.filled_avg_price else (
                price_fn(symbol) if price_fn else None)
            qty = _filled_qty(order) or (want_qty or 0)
            if fill:
                return ("filled", fill, qty, str(oid))

    # genuinely didn't fill — cancel so it can't fill later behind our back
    try:
        trading.cancel_order_by_id(oid)
        time.sleep(1.5)
        order = trading.get_order_by_id(oid)
        if _s(order) == "filled" and order.filled_avg_price:
            return _result(order)
    except Exception:
        pass
    return ("not_filled", None, None, str(oid))
