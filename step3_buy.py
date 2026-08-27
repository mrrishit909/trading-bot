"""
STEP 3: Buy ONE pretend share.

This buys exactly 1 share of a stock with PRETEND money, then shows you
that you own it. Still 100% fake money. Nothing real can happen here.

Run it like this:
    ./venv/bin/python step3_buy.py          (buys 1 share of Apple)
    ./venv/bin/python step3_buy.py TSLA     (buys 1 share of Tesla)
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

# 1. Load keys
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# 2. Which stock, and how many shares (always 1 for this step)
symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
shares = 1

# 3. Connect (paper = pretend money)
trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
data = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# 4. Look first, so we know roughly what we're about to spend
quote = data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
guess_price = quote.ask_price
print(f"About to buy {shares} share of {symbol} for roughly ${guess_price:,.2f} (pretend money).")

# 5. Place the order.
#    "market order" = buy right now at whatever the going price is.
order_request = MarketOrderRequest(
    symbol=symbol,
    qty=shares,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY,   # this order is only good for today
)
order = trading.submit_order(order_request)
print(f"Order sent! Its ticket number is {order.id}")

# 6. Wait a few seconds for it to go through, then check on it
print("Waiting for it to fill...")
for _ in range(10):
    time.sleep(1)
    order = trading.get_order_by_id(order.id)
    if order.status == "filled":
        break

# 7. Report what happened
print("--------------------------------------")
if order.status == "filled":
    paid = float(order.filled_avg_price)
    print(f"  BOUGHT {order.filled_qty} share of {symbol} at ${paid:,.2f} each.")
    print(f"  You spent ${paid * float(order.filled_qty):,.2f} of pretend money.")
else:
    print(f"  Order status is '{order.status}' (not filled yet).")
    print("  If the market is closed, it will fill when it opens.")
print("--------------------------------------")

# 8. Show everything we now own
positions = trading.get_all_positions()
if positions:
    print("Stuff you now own:")
    for p in positions:
        print(f"  {p.qty} share(s) of {p.symbol}, worth ${float(p.market_value):,.2f} right now")
else:
    print("You don't own anything yet.")
