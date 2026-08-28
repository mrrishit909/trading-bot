"""
STEP 11 helpers: everything about finding and trading a single option.

An option contract has a code like  AAPL260918C00320000  which means:
    AAPL      the stock it's about
    260918    expires 2026-09-18
    C         a Call (P would be a Put)
    00320000  strike price $320.00

We ONLY ever buy calls and puts (never sell them), so the worst that can
happen on any bet is we lose what we paid.
"""

import re
from datetime import date, timedelta

from alpaca.trading.requests import GetOptionContractsRequest, LimitOrderRequest
from alpaca.trading.enums import ContractType, AssetStatus, OrderSide, TimeInForce
from alpaca.data.requests import OptionLatestQuoteRequest

import settings

STRATEGY_NAME = "options_long_v1"

_OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_occ(symbol):
    """AAPL260918C00320000 -> dict(underlying, expiration(date), kind, strike)."""
    m = _OCC.match(symbol)
    if not m:
        return None
    u, ymd, cp, strike = m.groups()
    exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    return {"underlying": u, "expiration": exp,
            "kind": "call" if cp == "C" else "put",
            "strike": int(strike) / 1000}


def readable(symbol):
    p = parse_occ(symbol)
    if not p:
        return symbol
    return f"{p['underlying']} ${p['strike']:g} {p['kind']} exp {p['expiration']}"


def days_to_expiry(symbol):
    p = parse_occ(symbol)
    return (p["expiration"] - date.today()).days if p else None


def pick_contract(trading_client, option_data_client, underlying, direction, stock_price):
    """
    Find a good contract to buy.
    direction: "call" (bullish) or "put" (bearish).
    Returns a dict with the contract + its live quote, or None if nothing good.
    """
    ctype = ContractType.CALL if direction == "call" else ContractType.PUT
    offset = settings.OPTION_STRIKE_OFFSET_PCT / 100
    target_strike = stock_price * (1 + offset) if direction == "call" else stock_price * (1 - offset)

    req = GetOptionContractsRequest(
        underlying_symbols=[underlying],
        status=AssetStatus.ACTIVE,
        type=ctype,
        expiration_date_gte=date.today() + timedelta(days=settings.OPTION_MIN_DAYS),
        expiration_date_lte=date.today() + timedelta(days=settings.OPTION_MAX_DAYS),
        strike_price_gte=str(round(target_strike * 0.85, 2)),
        strike_price_lte=str(round(target_strike * 1.15, 2)),
        limit=200,
    )
    contracts = trading_client.get_option_contracts(req).option_contracts
    if not contracts:
        return None

    # keep liquid ones
    liquid = [c for c in contracts
              if (c.open_interest is not None
                  and float(c.open_interest) >= settings.OPTION_MIN_OPEN_INTEREST)]
    pool = liquid or contracts

    # nearest expiration first, then strike closest to our target
    nearest_exp = min(c.expiration_date for c in pool)
    same_exp = [c for c in pool if c.expiration_date == nearest_exp]
    best = min(same_exp, key=lambda c: abs(float(c.strike_price) - target_strike))

    # live quote
    q = option_data_client.get_option_latest_quote(
        OptionLatestQuoteRequest(symbol_or_symbols=best.symbol))[best.symbol]
    ask, bid = q.ask_price, q.bid_price
    if not ask or ask <= 0:
        return None
    mid = (ask + bid) / 2 if bid else ask
    spread_frac = (ask - bid) / mid if (bid and mid) else 1.0
    if spread_frac > 0.35:          # bid/ask too wide -> hard to trade
        return None

    return {
        "symbol": best.symbol,
        "underlying": underlying,
        "kind": direction,
        "strike": float(best.strike_price),
        "expiration": str(best.expiration_date),
        "open_interest": best.open_interest,
        "bid": bid, "ask": ask, "mid": round(mid, 2),
        "cost_1_contract": round(ask * 100, 2),
    }


def _order(trading_client, symbol, contracts, side, limit_price):
    order = trading_client.submit_order(LimitOrderRequest(
        symbol=symbol, qty=contracts, side=side,
        time_in_force=TimeInForce.DAY,
        limit_price=round(limit_price, 2),
    ))
    return order


def buy_to_open(trading_client, symbol, contracts, ask):
    return _order(trading_client, symbol, contracts, OrderSide.BUY, ask)


def sell_to_close(trading_client, symbol, contracts, bid):
    # sell a hair below the bid so it actually fills
    return _order(trading_client, symbol, contracts, OrderSide.SELL, max(bid * 0.98, 0.01))
