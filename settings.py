"""
The robot's rules, all in one place. Change these numbers to make the
robot braver or more careful. Start SMALL and CAREFUL.
"""

from universe import UNIVERSE
from crypto_universe import CRYPTO_UNIVERSE   # noqa: F401  (used by the crypto robot)

# The robot may ONLY trade stocks on this list (the "big list" in universe.py).
ALLOWED_STOCKS = UNIVERSE

# Never put more than this many dollars into one stock.
MAX_DOLLARS_PER_STOCK = 2000

# How many dollars to spend each time the robot buys a stock.
DOLLARS_PER_BUY = 1000

# Never own more than this many different stocks at once.
MAX_STOCKS_HELD = 5

# Never make more than this many trades in one day (stocks AND options together).
# Up to 5 stock buys + 5 stock sells + 3 option buys + 3 option sells = 16 worst case.
MAX_TRADES_PER_DAY = 16

# If we lose more than this much pretend money in one day, STOP everything.
DAILY_LOSS_LIMIT = 500

# When scanning the big list, how many top candidates to look at closely.
SHORTLIST_SIZE = 8


# ============ OPTIONS (paper only, and much more careful) ============
# The options robot ONLY ever BUYS calls and puts. It never sells options.
# That means the most it can ever lose on one bet is what it paid.

TRADE_OPTIONS = True

# Most we'll pay for one option bet (1 contract = the option price x 100).
MAX_DOLLARS_PER_OPTION = 1000

# How many option bets open at once.
MAX_OPTION_POSITIONS = 3

# Which expirations to consider (days from today).
OPTION_MIN_DAYS = 20
OPTION_MAX_DAYS = 45

# How far out-of-the-money to buy (percent). Calls this far above the stock
# price, puts this far below. Slightly OTM = cheaper bet, clearer direction.
OPTION_STRIKE_OFFSET_PCT = 2.0

# Skip contracts fewer people are trading than this (hard to get out of).
OPTION_MIN_OPEN_INTEREST = 100

# Auto-exit rules for an option we hold.
OPTION_TAKE_PROFIT_PCT = 50     # sell to close once up this much
OPTION_STOP_LOSS_PCT = 50       # sell to close once down this much
OPTION_CLOSE_BEFORE_EXPIRY_DAYS = 5   # always close if expiry is this close


# ============ CRYPTO (paper only, trades 24/7) ============
# Crypto never closes, so this part of the robot never has to stop.
# Crypto is jumpier than stocks, so the money limits are smaller.

TRADE_CRYPTO = True

# How many dollars to spend each time it buys a coin.
CRYPTO_DOLLARS_PER_BUY = 200

# Never own more than this many different coins at once.
MAX_CRYPTO_HELD = 4

# Never put more than this many dollars into one coin.
MAX_DOLLARS_PER_CRYPTO = 400

# Never make more than this many crypto trades in one day.
MAX_CRYPTO_TRADES_PER_DAY = 8
