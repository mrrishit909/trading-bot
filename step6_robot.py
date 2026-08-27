"""
STEP 6: Run the robot ONCE.

For each stock on our allowed list, the robot:
  1. Looks at the price history
  2. Decides: BUY, SELL, or WAIT (and says why)
  3. Asks the bouncer if it's allowed
  4. If yes, makes the pretend trade

Run it like this:
    ./venv/bin/python step6_robot.py             (really makes pretend trades)
    ./venv/bin/python step6_robot.py --pretend   (just talk, don't trade)
"""

import os
import sys
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

import settings
from robot import decide
from safety import can_i_trade

# How many dollars to spend each time the robot buys.
DOLLARS_PER_BUY = 1000

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

just_talking = "--pretend" in sys.argv

trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
data = StockHistoricalDataClient(API_KEY, SECRET_KEY)


def do_we_own(symbol):
    try:
        trading.get_open_position(symbol)
        return True
    except Exception:
        return False


def market_price(symbol):
    q = data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    return q.ask_price or q.bid_price


def make_trade(symbol, side, shares):
    order = trading.submit_order(MarketOrderRequest(
        symbol=symbol, qty=shares,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    for _ in range(10):
        time.sleep(1)
        order = trading.get_order_by_id(order.id)
        if order.status == "filled":
            return f"{side.upper()} {order.filled_qty} {symbol} @ ${float(order.filled_avg_price):,.2f}"
    return f"{side.upper()} {symbol}: order status '{order.status}'"


print("=" * 55)
print("ROBOT IS THINKING" + ("  (pretend mode: no trades)" if just_talking else ""))
print("=" * 55)

for symbol in settings.ALLOWED_STOCKS:
    print(f"\n--- {symbol} ---")
    own = do_we_own(symbol)
    plan = decide(data, symbol, own)
    print(f"Decision: {plan['action']}")
    print(f"Why: {plan['reason']}")

    if plan["action"] == "WAIT":
        continue

    price = market_price(symbol)

    if plan["action"] == "BUY":
        shares = int(DOLLARS_PER_BUY // price)
        if shares < 1:
            print(f"Skip: one share of {symbol} costs ${price:,.2f}, more than our ${DOLLARS_PER_BUY} budget.")
            continue
        side = "buy"
    else:  # SELL
        pos = trading.get_open_position(symbol)
        shares = float(pos.qty)
        side = "sell"

    ok, reason = can_i_trade(trading, symbol, shares, price, side)
    if not ok:
        print(f"Bouncer blocked it: {reason}")
        continue

    if just_talking:
        print(f"WOULD {side} {shares:g} share(s) of {symbol} (~${shares * price:,.2f})")
    else:
        print("Bouncer said yes. Trading...")
        print(make_trade(symbol, side, shares))

print("\n" + "=" * 55)
account = trading.get_account()
print(f"Account value now: ${float(account.portfolio_value):,.2f}   "
      f"Cash: ${float(account.cash):,.2f}")
positions = trading.get_all_positions()
if positions:
    print("Holding:")
    for p in positions:
        pl = float(p.unrealized_pl)
        print(f"  {p.qty} {p.symbol}  worth ${float(p.market_value):,.2f}  "
              f"({'+' if pl >= 0 else ''}{pl:,.2f})")
else:
    print("Holding: nothing (all cash)")
