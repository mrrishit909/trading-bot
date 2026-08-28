"""
The crypto scanner — same idea as scanner.py but for coins.

Because crypto moves faster, it uses shorter averages:
  fast = 3-day average, slow = 10-day average.
"trending up" = fast above slow. "just crossed up" = flipped above today.
"""

from datetime import datetime, timezone, timedelta
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

FAST_DAYS = 3
SLOW_DAYS = 10
STRATEGY_NAME = "crypto_sma_v1"


def _avg(xs):
    return sum(xs) / len(xs)


def analyze_all(crypto_data_client, symbols):
    start = datetime.now(timezone.utc) - timedelta(days=30)
    bars = crypto_data_client.get_crypto_bars(CryptoBarsRequest(
        symbol_or_symbols=list(symbols), timeframe=TimeFrame.Day, start=start,
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
        out[sym] = {
            "enough_data": True,
            "price": round(closes[-1], 4),
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
    exclude = set(exclude)
    picks = []
    for sym, a in analysis.items():
        if sym in exclude or not a.get("enough_data") or not a["trending_up"]:
            continue
        score = (100 if a["crossed_up"] else 0) + a["move_5d_pct"]
        picks.append((score, sym))
    picks.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in picks]
