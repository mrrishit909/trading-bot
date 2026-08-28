"""
STEP 5: The bouncer.

Before the robot makes ANY trade, it must ask the bouncer:
    "Can I buy 5 shares of AAPL?"
The bouncer says YES or NO with a reason.

The 4 rules:
  1. Is this stock on the allowed list?
  2. Would this trade put too much money in one stock?
  3. Have we already traded too many times today?
  4. Have we lost too much money today? (if so, nothing is allowed)
"""

from datetime import datetime, timezone
import settings


def _trades_made_today(trading_client):
    """Count how many orders we've placed since midnight (UTC)."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    orders = trading_client.get_orders(GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        after=today_start,
        limit=500,
    ))
    return len(orders)


def _money_lost_today(trading_client):
    """How much the whole account is down today. Positive number = we lost that much."""
    account = trading_client.get_account()
    now = float(account.equity)
    start = float(account.last_equity)   # what the account was worth at yesterday's close
    change = now - start
    return -change if change < 0 else 0.0


def can_i_trade(trading_client, symbol, shares, price_per_share, side):
    """
    Ask the bouncer. Returns (True, "ok") or (False, "reason it said no").
    side is "buy" or "sell".
    """
    symbol = symbol.upper()

    # RULE 4 first: if we're having a bad day, stop completely.
    lost = _money_lost_today(trading_client)
    if lost >= settings.DAILY_LOSS_LIMIT:
        return (False, f"NO. We've lost ${lost:,.2f} today (limit is ${settings.DAILY_LOSS_LIMIT}). "
                       f"Done trading for the day.")

    # RULE 3: too many trades today?
    count = _trades_made_today(trading_client)
    if count >= settings.MAX_TRADES_PER_DAY:
        return (False, f"NO. We've already made {count} trades today "
                       f"(limit is {settings.MAX_TRADES_PER_DAY}).")

    # Selling something we own is always allowed past this point (it reduces risk).
    if side == "sell":
        return (True, "ok")

    # RULE 1: is this stock on the big list?
    if symbol not in settings.ALLOWED_STOCKS:
        return (False, f"NO. {symbol} is not on the big list of "
                       f"{len(settings.ALLOWED_STOCKS)} allowed stocks.")

    # RULE 1b: are we already holding as many different stocks as allowed?
    #   (only count real stock positions, not option positions)
    held_symbols = {p.symbol for p in trading_client.get_all_positions()
                    if str(getattr(p, "asset_class", "")).endswith("us_equity")}
    if symbol not in held_symbols and len(held_symbols) >= settings.MAX_STOCKS_HELD:
        return (False, f"NO. We already hold {len(held_symbols)} different stocks "
                       f"(limit is {settings.MAX_STOCKS_HELD}). Sell something first.")

    # RULE 2: would we have too much money in this one stock?
    #   current value we already hold + what we're about to add
    try:
        pos = trading_client.get_open_position(symbol)
        already_in = float(pos.market_value)
    except Exception:
        already_in = 0.0
    about_to_add = shares * price_per_share
    total_after = already_in + about_to_add
    if total_after > settings.MAX_DOLLARS_PER_STOCK:
        return (False, f"NO. That would put ${total_after:,.2f} into {symbol} "
                       f"(limit is ${settings.MAX_DOLLARS_PER_STOCK} per stock).")

    return (True, "ok")


def can_i_trade_option(trading_client, occ_symbol, underlying, contracts, cost_per_contract, side):
    """
    The bouncer for OPTIONS. Returns (True, "ok") or (False, "reason").
    side is "buy" (open a bet) or "sell" (close one).
    """
    # Same bad-day and too-many-trades rules as stocks.
    lost = _money_lost_today(trading_client)
    if lost >= settings.DAILY_LOSS_LIMIT:
        return (False, f"NO. We've lost ${lost:,.2f} today (limit ${settings.DAILY_LOSS_LIMIT}). "
                       f"Done for the day.")

    count = _trades_made_today(trading_client)
    if count >= settings.MAX_TRADES_PER_DAY:
        return (False, f"NO. Already made {count} trades today (limit {settings.MAX_TRADES_PER_DAY}).")

    # Closing a bet is always allowed (it reduces risk).
    if side == "sell":
        return (True, "ok")

    # The stock it's about must be on the big list.
    if underlying.upper() not in settings.ALLOWED_STOCKS:
        return (False, f"NO. {underlying} is not on the big list.")

    # How many option bets do we already have open?
    from options_engine import parse_occ
    option_positions = [p for p in trading_client.get_all_positions()
                        if str(getattr(p, "asset_class", "")).endswith("us_option")]
    held_occ = {p.symbol for p in option_positions}
    open_underlyings = {info["underlying"]
                        for p in option_positions
                        if (info := parse_occ(p.symbol))}

    if occ_symbol not in held_occ:   # this would be a brand-new bet
        if len(option_positions) >= settings.MAX_OPTION_POSITIONS:
            return (False, f"NO. Already hold {len(option_positions)} option bets "
                           f"(limit {settings.MAX_OPTION_POSITIONS}).")
        if underlying.upper() in open_underlyings:
            return (False, f"NO. Already have an option bet on {underlying}.")

    # Cost of the bet.
    total_cost = contracts * cost_per_contract
    if total_cost > settings.MAX_DOLLARS_PER_OPTION:
        return (False, f"NO. That bet costs ${total_cost:,.2f} "
                       f"(limit ${settings.MAX_DOLLARS_PER_OPTION} per option).")

    return (True, "ok")
