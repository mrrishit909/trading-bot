"""
STEP 2: Look up a stock price.

This does ONE thing: you tell it a stock (like AAPL for Apple),
and it tells you the latest price. Still no buying or selling.

Run it like this:
    ./venv/bin/python step2_look.py          (defaults to Apple)
    ./venv/bin/python step2_look.py TSLA     (look up Tesla instead)
"""

import os
import sys
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# 1. Load our keys
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# 2. Which stock do we want? Use what you typed, or Apple if you typed nothing.
symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"

# 3. Connect to the "price-looking-up" part of Alpaca
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# 4. Ask for the latest quote (the current buy price and sell price)
request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
quote = data_client.get_stock_latest_quote(request)[symbol]

# 5. Explain it simply
#    "ask" = the price someone will SELL you a share for (what you pay to buy)
#    "bid" = the price someone will BUY your share for (what you get if you sell)
ask = quote.ask_price
bid = quote.bid_price
middle = (ask + bid) / 2 if ask and bid else (ask or bid)

print(f"Looking up: {symbol}")
print("--------------------------------------")
print(f"  If you want to BUY now, one share costs about:  ${ask:,.2f}")
print(f"  If you want to SELL now, you'd get about:       ${bid:,.2f}")
print(f"  Fair middle price:                              ${middle:,.2f}")
print("--------------------------------------")
print(f"  (price checked at {quote.timestamp})")
