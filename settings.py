"""
The robot's rules, all in one place. Change these numbers to make the
robot braver or more careful. Start SMALL and CAREFUL.
"""

from universe import UNIVERSE

# The robot may ONLY trade stocks on this list (the "big list" in universe.py).
ALLOWED_STOCKS = UNIVERSE

# Never put more than this many dollars into one stock.
MAX_DOLLARS_PER_STOCK = 2000

# How many dollars to spend each time the robot buys a stock.
DOLLARS_PER_BUY = 1000

# Never own more than this many different stocks at once.
MAX_STOCKS_HELD = 5

# Never make more than this many trades in one day.
# (With up to 5 stocks to buy and 5 to sell, 10 gives a little headroom.)
MAX_TRADES_PER_DAY = 10

# If we lose more than this much pretend money in one day, STOP everything.
DAILY_LOSS_LIMIT = 500

# When scanning the big list, how many top candidates to look at closely.
SHORTLIST_SIZE = 8
