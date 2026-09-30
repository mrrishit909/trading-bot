"""
The crypto scanner — same idea as scanner.py but for coins.

Because crypto moves faster, it uses shorter averages:
  main:  fast = 3-day, slow = 10-day
  $500 sprint: fast = 2-day, slow = 6-day  (catch moves earlier)
"trending up" = fast above slow. "just crossed up" = flipped above today.
"sell signal" = fast dropped a clear margin (SELL_BUFFER_PCT) below slow.

Also computes RSI(14) and 30-day momentum so rank_buys can prefer coins with
real multi-week strength and skip ones that are already overbought.
"""

import os
from datetime import datetime, timezone, timedelta
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
import settings

_SPRINT = os.environ.get("ROBOT_PROFILE") == "sprint500"
FAST_DAYS = 2 if _SPRINT else 3
SLOW_DAYS = 6 if _SPRINT else 10
STRATEGY_NAME = "crypto_sma_v1"

SELL_BUFFER_PCT = 1.0 if _SPRINT else 1.5

MOM_DAYS = 30
RSI_DAYS = 14


def _avg(xs):
    return sum(xs) / len(xs)


def _rsi(closes, n=RSI_DAYS):
    if len(closes) < n + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_g, avg_l = _avg(gains[:n]), _avg(losses[:n])
    for i in range(n, len(deltas)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
    if avg_l == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_g / avg_l), 1)


def signals_from_series(closes, fast_days=FAST_DAYS, slow_days=SLOW_DAYS,
                        sell_buffer_pct=SELL_BUFFER_PCT):
    """The pure per-coin signal math — no I/O. `closes` is a chronological list
    of daily closing prices (oldest first). Live trading (analyze_all) and the
    crypto backtest both call this so they can't drift apart.

    Same contract as scanner.signals_from_series for stocks: pass a trailing
    window ending on the day you want signals for."""
    if len(closes) < slow_days + 1:
        return {"enough_data": False}
    fast_now = _avg(closes[-fast_days:])
    slow_now = _avg(closes[-slow_days:])
    fast_prev = _avg(closes[-fast_days - 1:-1])
    slow_prev = _avg(closes[-slow_days - 1:-1])
    mom = (round((closes[-1] / closes[-MOM_DAYS - 1] - 1) * 100, 1)
           if len(closes) > MOM_DAYS else None)
    return {
        "enough_data": True,
        "price": round(closes[-1], 4),
        "fast": round(fast_now, 4),
        "slow": round(slow_now, 4),
        "trending_up": fast_now > slow_now,
        "sell_signal": fast_now < slow_now * (1 - sell_buffer_pct / 100),
        "crossed_up": (fast_prev <= slow_prev) and (fast_now > slow_now),
        "crossed_down": (fast_prev >= slow_prev) and (fast_now < slow_now),
        "move_1d_pct": round((closes[-1] / closes[-2] - 1) * 100, 2),
        "move_5d_pct": round((closes[-1] / closes[-6] - 1) * 100, 2) if len(closes) > 6 else 0.0,
        "mom_30d": mom,
        "rsi14": _rsi(closes),
        # recent high, for the trailing stop — approximates "peak since entry".
        "recent_high": round(max(closes[-20:]), 4),
    }


def analyze_all(crypto_data_client, symbols):
    start = datetime.now(timezone.utc) - timedelta(days=120)
    bars = crypto_data_client.get_crypto_bars(CryptoBarsRequest(
        symbol_or_symbols=list(symbols), timeframe=TimeFrame.Day, start=start,
    )).data

    out = {}
    for sym in symbols:
        closes = [b.close for b in bars.get(sym, [])]
        out[sym] = signals_from_series(closes)
    return out


def rank_buys(analysis, exclude=()):
    exclude = set(exclude)
    rsi_cap = getattr(settings, "RSI_OVERBOUGHT", 78)
    picks = []
    for sym, a in analysis.items():
        if sym in exclude or not a.get("enough_data") or not a["trending_up"]:
            continue
        if a.get("rsi14") is not None and a["rsi14"] > rsi_cap:
            continue
        mom = a.get("mom_30d")
        # prefer coins with real 30-day strength; fall back to the 5-day move
        score = (mom if mom is not None else a["move_5d_pct"]) + (15 if a["crossed_up"] else 0)
        picks.append((score, sym))
    picks.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in picks]
