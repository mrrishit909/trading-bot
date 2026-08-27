"""
STEP 5 demo: watch the bouncer work.

We ask the bouncer a few questions and see it say YES and NO.
No real trades happen here — we're just testing the bouncer.

Run it like this:
    ./venv/bin/python step5_safety_demo.py
"""

import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from safety import can_i_trade
import settings

load_dotenv()
trading = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)

print("The rules right now:")
print(f"  Allowed stocks:        {', '.join(settings.ALLOWED_STOCKS)}")
print(f"  Max per stock:         ${settings.MAX_DOLLARS_PER_STOCK}")
print(f"  Max trades per day:    {settings.MAX_TRADES_PER_DAY}")
print(f"  Daily loss limit:      ${settings.DAILY_LOSS_LIMIT}")
print("=" * 50)

# We'll pretend Apple costs $310 for these tests.
tests = [
    ("AAPL", 3, 310, "buy",  "small Apple buy -> should be YES"),
    ("AAPL", 50, 310, "buy", "huge Apple buy ($15,500) -> should be NO (too much in one stock)"),
    ("DOGE", 1, 310, "buy",  "buy a stock not on the list -> should be NO"),
    ("AAPL", 3, 310, "sell", "selling -> should be YES"),
]

for symbol, shares, price, side, description in tests:
    ok, reason = can_i_trade(trading, symbol, shares, price, side)
    stamp = "YES ✅" if ok else "NO  🚫"
    print(f"\n{description}")
    print(f"  Ask: {side} {shares} {symbol} @ ${price}")
    print(f"  Bouncer says: {stamp}  {reason if not ok else ''}")
