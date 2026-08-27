"""
STEP 6: The robot's baby brain.

It follows ONE classic rule, called a "moving average crossover":

  - Take the average price over the last 5 days  (the "fast" line)
  - Take the average price over the last 20 days (the "slow" line)
  - If the fast line is ABOVE the slow line  -> the stock is trending UP  -> we want to OWN it
  - If the fast line is BELOW the slow line  -> the stock is trending DOWN -> we want to be in CASH

An "average price over the last few days" just smooths out the daily jiggles
so we can see which way the stock is really leaning.

This rule is famous, simple, and (spoiler) usually does NOT beat just buying
and holding. That's fine. We're using it to build the machinery.
"""

from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta, timezone

FAST_DAYS = 5
SLOW_DAYS = 20


def _average(numbers):
    return sum(numbers) / len(numbers)


def decide(data_client, symbol, do_we_own_it):
    """
    Look at the stock and decide what to do.
    Returns a dict: {"action": "BUY"/"SELL"/"WAIT", "reason": "...", "fast": x, "slow": y}
    """
    symbol = symbol.upper()

    # Get the last ~40 calendar days of daily prices (enough for a 20-day average)
    start = datetime.now(timezone.utc) - timedelta(days=40)
    bars = data_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
    )).data.get(symbol, [])

    closing_prices = [bar.close for bar in bars]

    if len(closing_prices) < SLOW_DAYS:
        return {"action": "WAIT", "reason": f"Not enough price history yet "
                f"({len(closing_prices)} days, need {SLOW_DAYS}).", "fast": None, "slow": None}

    fast_line = _average(closing_prices[-FAST_DAYS:])
    slow_line = _average(closing_prices[-SLOW_DAYS:])
    trending_up = fast_line > slow_line

    if trending_up and not do_we_own_it:
        action = "BUY"
        reason = (f"{symbol} is trending UP (5-day avg ${fast_line:,.2f} is above "
                  f"20-day avg ${slow_line:,.2f}) and we don't own any. Let's buy a little.")
    elif not trending_up and do_we_own_it:
        action = "SELL"
        reason = (f"{symbol} is trending DOWN (5-day avg ${fast_line:,.2f} is below "
                  f"20-day avg ${slow_line:,.2f}) and we own some. Let's get out.")
    elif trending_up and do_we_own_it:
        action = "WAIT"
        reason = f"{symbol} still trending up and we already own it. Hold. Do nothing."
    else:
        action = "WAIT"
        reason = f"{symbol} trending down and we don't own it. Stay in cash. Do nothing."

    return {"action": action, "reason": reason, "fast": fast_line, "slow": slow_line}
