"""
STEP 4: Sell a share back.

This sells shares you own (pretend money) and shows if you made
or lost money on the trade.

Run it like this:
    ./venv/bin/python step4_sell.py          (sells your Apple)
    ./venv/bin/python step4_sell.py TSLA     (sells your Tesla)
"""

import os
import sys
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# 1. Load keys
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# 2. Which stock to sell
symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"

# 3. Connect
trading = TradingClient(API_KEY, SECRET_KEY, paper=True)

# 4. Check we actually own it
try:
    position = trading.get_open_position(symbol)
except Exception:
    print(f"You don't own any {symbol}, so there's nothing to sell.")
    raise SystemExit(0)

shares_owned = float(position.qty)
bought_for = float(position.avg_entry_price)
print(f"You own {shares_owned:g} share(s) of {symbol}, bought at ${bought_for:,.2f} each.")

# 5. Sell all of it
order = trading.submit_order(MarketOrderRequest(
    symbol=symbol,
    qty=shares_owned,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.DAY,
))
print(f"Sell order sent! Ticket number {order.id}")

# 6. Wait for it to fill
print("Waiting for it to fill...")
for _ in range(10):
    time.sleep(1)
    order = trading.get_order_by_id(order.id)
    if order.status == "filled":
        break

# 7. Did we win or lose?
print("--------------------------------------")
if order.status == "filled":
    sold_for = float(order.filled_avg_price)
    profit = (sold_for - bought_for) * shares_owned
    print(f"  SOLD {order.filled_qty} share(s) of {symbol} at ${sold_for:,.2f} each.")
    if profit >= 0:
        print(f"  You made ${profit:,.2f} of pretend money. Nice!")
    else:
        print(f"  You lost ${abs(profit):,.2f} of pretend money. That's the spread biting.")
else:
    print(f"  Order status is '{order.status}' (not filled yet).")
print("--------------------------------------")

# 8. Show account after
account = trading.get_account()
print(f"Cash in the piggy bank now: ${float(account.cash):,.2f}")
