"""
The robot's rules, all in one place. Change these numbers to make the
robot braver or more careful. Start SMALL and CAREFUL.
"""

# Only allowed to trade these stocks. Nothing else.
ALLOWED_STOCKS = ["AAPL", "MSFT", "SPY"]

# Never put more than this many dollars into one stock.
MAX_DOLLARS_PER_STOCK = 2000

# Never make more than this many trades in one day.
MAX_TRADES_PER_DAY = 5

# If we lose more than this much pretend money in one day, STOP everything.
DAILY_LOSS_LIMIT = 500
