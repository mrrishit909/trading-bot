"""
STEP 1: Say hi to our pretend-money account.

This does ONE thing: it connects to Alpaca and tells us how much
play money we have. No buying. No selling. Just "hello, how much money?"

Run it like this:
    ./venv/bin/python step1_say_hi.py
"""

import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

# 1. Load our secret keys from the .env file
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    print("Hmm, I can't find your keys.")
    print("Did you make a file called .env with your keys in it?")
    print("Copy .env.example to .env and paste your real keys.")
    raise SystemExit(1)

# 2. Connect to Alpaca. paper=True means PRETEND MONEY. Very important.
client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# 3. Ask the account how it's doing
account = client.get_account()

# 4. Print it out in a friendly way
print("Hi! Here is your pretend-money account:")
print("--------------------------------------")
print(f"  Play money you can spend:   ${float(account.buying_power):,.2f}")
print(f"  Total value of everything:  ${float(account.portfolio_value):,.2f}")
print(f"  Cash sitting in the piggy bank: ${float(account.cash):,.2f}")
print(f"  Account status: {account.status}")
print("--------------------------------------")
print("If you see numbers above, it worked!")
