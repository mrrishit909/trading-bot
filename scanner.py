"""
The scanner: looks at the WHOLE big list at once and finds the few stocks
worth a closer look.

For every stock it works out:
  - the 5-day average price (fast) and 20-day average price (slow)
  - "trending up" = fast is above slow
  - "just crossed up" = fast was below slow yesterday and is above it today
    (this is the strongest buy signal)
  - how much it moved in the last 1 day and last 5 days

Then rank_buys() picks the best ones to actually consider buying.
"""

from datetime import datetime, timezone, timedelta
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import settings

FAST_DAYS = 5
SLOW_DAYS = 20
STRATEGY_NAME = "sma_scan_v1"

# Ignore anything priced outside this band (too cheap = risky, too pricey = can't afford a share).
MIN_PRICE = 5
MAX_PRICE = 1500


def _avg(xs):
    return sum(xs) / len(xs)


def analyze_all(data_client, symbols):
    """Fetch daily prices for every symbol in one go and analyze each one."""
    symbols = sorted(set(symbols))
    start = datetime.now(timezone.utc) - timedelta(days=50)
    bars = data_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start,
    )).data

    out = {}
    for sym in symbols:
        closes = [b.close for b in bars.get(sym, [])]
        if len(closes) < SLOW_DAYS + 1:
            out[sym] = {"enough_data": False}
            continue

        fast_now = _avg(closes[-FAST_DAYS:])
        slow_now = _avg(closes[-SLOW_DAYS:])
        fast_prev = _avg(closes[-FAST_DAYS - 1:-1])
        slow_prev = _avg(closes[-SLOW_DAYS - 1:-1])

        price = closes[-1]
        out[sym] = {
            "enough_data": True,
            "price": round(price, 2),
            "fast": round(fast_now, 4),
            "slow": round(slow_now, 4),
            "trending_up": fast_now > slow_now,
            "crossed_up": (fast_prev <= slow_prev) and (fast_now > slow_now),
            "crossed_down": (fast_prev >= slow_prev) and (fast_now < slow_now),
            "move_1d_pct": round((closes[-1] / closes[-2] - 1) * 100, 2),
            "move_5d_pct": round((closes[-1] / closes[-6] - 1) * 100, 2),
        }
    return out


def rank_buys(analysis, exclude=()):
    """
    Return a list of symbols worth buying, best first.
    A stock qualifies if: enough data, trending up, price in band,
    we can afford at least one share, and it's not excluded (already held).
    Fresh 'crossed up' signals rank above stocks that have been trending a while.
    """
    exclude = set(exclude)
    picks = []
    for sym, a in analysis.items():
        if sym in exclude or not a.get("enough_data"):
            continue
        if not a["trending_up"]:
            continue
        if not (MIN_PRICE <= a["price"] <= MAX_PRICE):
            continue
        if a["price"] > settings.DOLLARS_PER_BUY:      # can't afford even one share
            continue
        score = (100 if a["crossed_up"] else 0) + a["move_5d_pct"]
        picks.append((score, sym, a))

    picks.sort(key=lambda t: t[0], reverse=True)
    return [sym for (_, sym, _) in picks]
