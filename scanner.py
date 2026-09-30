"""
The scanner: looks at the WHOLE big list at once and finds the few stocks
worth a closer look.

For every stock it works out:
  - the 5-day average price (fast) and 20-day average price (slow)
  - "trending up" = fast is above slow
  - "just crossed up" = fast was below slow yesterday and is above it today
  - "sell signal" = fast has dropped a clear margin (SELL_BUFFER_PCT) below slow
    (a margin, not a bare crossover, so a stock on the line isn't churned)
  - 1-day / 5-day / 3-month / 6-month price moves
  - RSI(14)      — momentum oscillator; >~78 means "already stretched"
  - ATR%(14)     — how jumpy the stock is, as a % of its price
  - recent high  — for the trailing stop

Then rank_buys() ranks candidates by longer-horizon momentum.
"""

from datetime import datetime, timezone, timedelta
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment
import settings

FAST_DAYS = 5
SLOW_DAYS = 20
STRATEGY_NAME = "sma_scan_v1"

SELL_BUFFER_PCT = 0.5

# Ignore anything priced under this (penny stocks — thin, jumpy, risky).
# No upper bound: buys are fractional (spend $X), so a $700 stock is fine.
MIN_PRICE = 5
MAX_PRICE = 1_000_000

MOM_SHORT_DAYS = 63     # ~3 months
MOM_LONG_DAYS = 126     # ~6 months
RSI_DAYS = 14
ATR_DAYS = 14


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
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 1)


def _atr_pct(highs, lows, closes, n=ATR_DAYS):
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    atr = _avg(trs[:n])
    for i in range(n, len(trs)):
        atr = (atr * (n - 1) + trs[i]) / n
    return round(atr / closes[-1] * 100, 2) if closes[-1] else None


def _ret_pct(closes, days):
    if len(closes) <= days:
        return None
    return round((closes[-1] / closes[-days - 1] - 1) * 100, 2)


def signals_from_series(closes, highs=None, lows=None):
    """
    The actual signal math, taking price history UP TO AND INCLUDING "today"
    (closes[-1] is the latest close). This is the one place every number the
    bot trades on gets computed — analyze_all() below calls it for "today" on
    live data, and backtest.py calls it for every historical day, so the
    backtest tests the SAME arithmetic that's live, not a re-implementation
    that could quietly drift out of sync.
    Returns {"enough_data": False} if there isn't enough history yet.
    """
    if len(closes) < SLOW_DAYS + 1:
        return {"enough_data": False}

    fast_now = _avg(closes[-FAST_DAYS:])
    slow_now = _avg(closes[-SLOW_DAYS:])
    fast_prev = _avg(closes[-FAST_DAYS - 1:-1])
    slow_prev = _avg(closes[-SLOW_DAYS - 1:-1])

    return {
        "enough_data": True,
        "price": round(closes[-1], 2),
        "fast": round(fast_now, 4),
        "slow": round(slow_now, 4),
        "trending_up": fast_now > slow_now,
        "sell_signal": fast_now < slow_now * (1 - SELL_BUFFER_PCT / 100),
        "crossed_up": (fast_prev <= slow_prev) and (fast_now > slow_now),
        "crossed_down": (fast_prev >= slow_prev) and (fast_now < slow_now),
        "move_1d_pct": round((closes[-1] / closes[-2] - 1) * 100, 2),
        "move_5d_pct": round((closes[-1] / closes[-6] - 1) * 100, 2),
        "mom_63d": _ret_pct(closes, MOM_SHORT_DAYS),
        "mom_126d": _ret_pct(closes, MOM_LONG_DAYS),
        "rsi14": _rsi(closes),
        "atr_pct": _atr_pct(highs, lows, closes) if highs and lows else None,
        "recent_high": round(max(closes[-30:]), 4),
    }


def analyze_all(data_client, symbols):
    """Fetch ~10 months of daily prices for every symbol and analyze each one."""
    symbols = sorted(set(symbols))
    start = datetime.now(timezone.utc) - timedelta(days=300)
    bars = data_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start,
        adjustment=Adjustment.ALL,   # split/dividend adjusted, or a split looks like a crash
    )).data

    out = {}
    for sym in symbols:
        rows = bars.get(sym, [])
        closes = [b.close for b in rows]
        highs = [b.high for b in rows]
        lows = [b.low for b in rows]
        out[sym] = signals_from_series(closes, highs, lows)
    return out


def momentum_score(a):
    """The same blend-of-momentum score rank_buys ranks candidates by, exposed
    standalone so a HELD position can be scored too (used by the rank-based
    rotation rule in step10_scan_and_trade.py to compare "weakest thing we
    hold" against "best thing we don't")."""
    use_mom = getattr(settings, "USE_MOMENTUM_RANK", True)
    m3 = a.get("mom_63d")
    m6 = a.get("mom_126d")
    if use_mom and (m3 is not None or m6 is not None):
        return 0.6 * (m3 or 0) + 0.4 * (m6 or 0) + (15 if a.get("crossed_up") else 0)
    return (100 if a.get("crossed_up") else 0) + a.get("move_5d_pct", 0)


def rank_buys(analysis, exclude=()):
    """
    Return symbols worth buying, best first. A stock qualifies if:
    enough data, trending up, not a penny stock, not overbought, and (if
    REQUIRE_POSITIVE_QUARTER) also up over the past 3 months.
    Ranked by a blend of 3- and 6-month momentum, with a bonus for a fresh
    crossover.
    """
    exclude = set(exclude)
    need_quarter = getattr(settings, "REQUIRE_POSITIVE_QUARTER", True)
    rsi_cap = getattr(settings, "RSI_OVERBOUGHT", 78)
    atr_cap = getattr(settings, "MAX_BUY_ATR_PCT", None)

    picks = []
    for sym, a in analysis.items():
        if sym in exclude or not a.get("enough_data"):
            continue
        if not a["trending_up"] or a["price"] < MIN_PRICE:
            continue
        if a.get("rsi14") is not None and a["rsi14"] > rsi_cap:
            continue
        if atr_cap is not None and a.get("atr_pct") is not None and a["atr_pct"] > atr_cap:
            continue
        m3 = a.get("mom_63d")
        if need_quarter and m3 is not None and m3 <= 0:
            continue
        picks.append((momentum_score(a), sym))

    picks.sort(key=lambda t: t[0], reverse=True)
    return [sym for (_, sym) in picks]
