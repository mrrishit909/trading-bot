"""
The grading brain, shared by compare.py (text) and dashboard.py (website).

For every decision in the diary, look up what the stock actually did
`lookahead` trading days later, then score it:

  - "invested" decision (BUY, or WAIT while we owned it) earns the forward return
  - "in cash" decision (SELL, or WAIT while owning nothing) earns 0
  - a decision is "right" if: invested and it went up, OR in cash and it went down

Then per strategy we compare total earned vs the "always invested" benchmark.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment
import settings


def _slippage_pct(strategy):
    """Realism haircut applied on BOTH legs of a round trip — see settings.py."""
    if strategy == "crypto_sma_v1":
        return getattr(settings, "CRYPTO_SLIPPAGE_PCT", 0.15) / 100
    if strategy == "options_long_v1":
        return getattr(settings, "OPTION_SLIPPAGE_PCT", 1.0) / 100
    return getattr(settings, "STOCK_SLIPPAGE_PCT", 0.05) / 100


def grade_all(data_client, db, lookahead=3):
    rows = db.execute("""
        SELECT d.symbol, d.action, d.owned_before, d.ref_price, d.ts_utc, r.strategy AS strategy
        FROM decisions d JOIN runs r ON d.run_id = r.run_id
        WHERE r.strategy NOT IN ('options_long_v1', 'crypto_sma_v1')   -- these have their own P/L pages
          AND r.mode != 'pretend'                                      -- talk-only test runs don't count
        ORDER BY d.decision_id
    """).fetchall()
    if not rows:
        return {}

    symbols = sorted({r["symbol"] for r in rows})
    earliest = min(datetime.fromisoformat(r["ts_utc"]) for r in rows) - timedelta(days=5)
    bars = data_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=earliest,
        adjustment=Adjustment.ALL,
    )).data
    series_by = {s: [(b.timestamp.date(), b.close) for b in bars.get(s, [])] for s in symbols}

    def forward_return(symbol, decision_dt, entry_price):
        series = series_by.get(symbol, [])
        after = [c for (d, c) in series if d > decision_dt.date()]
        if len(after) < lookahead:
            return None
        return (after[lookahead - 1] - entry_price) / entry_price

    score = defaultdict(lambda: {"decisions": 0, "judged": 0, "pending": 0,
                                 "earned": 0.0, "benchmark": 0.0, "right": 0})
    for r in rows:
        s = score[r["strategy"]]
        s["decisions"] += 1
        entry = r["ref_price"]
        if entry is None:
            continue
        dt = datetime.fromisoformat(r["ts_utc"])
        fr = forward_return(r["symbol"], dt, entry)
        if fr is None:
            s["pending"] += 1
            continue
        invested = (r["action"] == "BUY") or (r["action"] == "WAIT" and r["owned_before"] == 1)
        s["judged"] += 1
        s["earned"] += fr if invested else 0.0
        s["benchmark"] += fr
        if (invested and fr > 0) or (not invested and fr <= 0):
            s["right"] += 1

    # add friendly derived numbers
    for s in score.values():
        j = s["judged"]
        s["hit_rate"] = (100 * s["right"] / j) if j else None
        s["avg_earned_pct"] = (100 * s["earned"] / j) if j else None
        s["avg_benchmark_pct"] = (100 * s["benchmark"] / j) if j else None
        s["beat_benchmark"] = (s["earned"] > s["benchmark"]) if j else None
    return dict(score)


def grade_trades(data_client, db):
    """
    The HONEST money view: match each real filled BUY to the later filled SELL
    that closed it (oldest-first), and measure the actual round-trip result.

    Unlike grade_all (which scores the signal every 30 min and double-counts a
    long hold hundreds of times), this counts each completed trade exactly once
    and reports real % return, win rate, and total realised profit — next to
    what the same money in SPY would have done over the same days.
    """
    from collections import defaultdict, deque

    rows = db.execute("""
        SELECT r.strategy AS strategy, t.symbol, t.side, t.shares, t.fill_price, t.ts_utc
        FROM trades t JOIN runs r ON t.run_id = r.run_id
        WHERE t.status = 'filled' AND r.mode != 'pretend'
          AND r.strategy != 'claude_advisor_v1'          -- advisory never trades
          AND t.shares IS NOT NULL AND t.fill_price IS NOT NULL
        ORDER BY t.trade_id
    """).fetchall()

    # SPY closes, for the "same money in the index instead" comparison
    spy = {}
    if rows:
        earliest = min(datetime.fromisoformat(r["ts_utc"]) for r in rows) - timedelta(days=5)
        sbars = data_client.get_stock_bars(StockBarsRequest(
            symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=earliest,
            adjustment=Adjustment.ALL,
        )).data.get("SPY", [])
        spy = {b.timestamp.date(): b.close for b in sbars}

    def spy_on_or_before(d):
        for back in range(7):
            hit = spy.get(d - timedelta(days=back))
            if hit:
                return hit
        return None

    def spy_return(buy_ts, sell_ts):
        a = spy_on_or_before(datetime.fromisoformat(buy_ts).date())
        b = spy_on_or_before(datetime.fromisoformat(sell_ts).date())
        return (b / a - 1) if (a and b) else None

    lots = defaultdict(deque)      # (strategy, symbol) -> [ [shares, price, ts], ... ]
    per = defaultdict(lambda: {"round_trips": 0, "wins": 0, "realised_pnl": 0.0,
                               "ret_sum": 0.0, "spy_ret_sum": 0.0, "spy_n": 0,
                               "best_pct": None, "worst_pct": None,
                               "still_open": 0, "open_cost": 0.0, "closed": []})

    for r in rows:
        key = (r["strategy"], r["symbol"])
        sh, px = float(r["shares"]), float(r["fill_price"])
        if r["side"] == "buy":
            lots[key].append([sh, px, r["ts_utc"]])
            continue
        # options are quoted per share but 1 contract controls 100 shares
        mult = 100 if r["strategy"] == "options_long_v1" else 1
        slip = _slippage_pct(r["strategy"])
        remaining = sh
        while remaining > 1e-9 and lots[key]:
            lot = lots[key][0]
            take = min(remaining, lot[0])
            # realism haircut: pay a touch more going in, get a touch less going out
            buy_eff = lot[1] * (1 + slip)
            sell_eff = px * (1 - slip)
            ret = (sell_eff / buy_eff - 1) if buy_eff else 0.0
            pnl = take * (sell_eff - buy_eff) * mult
            s = per[r["strategy"]]
            s["round_trips"] += 1
            s["realised_pnl"] += pnl
            s["ret_sum"] += ret
            if pnl > 0:
                s["wins"] += 1
            s["best_pct"] = ret if s["best_pct"] is None else max(s["best_pct"], ret)
            s["worst_pct"] = ret if s["worst_pct"] is None else min(s["worst_pct"], ret)
            sr = spy_return(lot[2], r["ts_utc"])
            if sr is not None:
                s["spy_ret_sum"] += sr
                s["spy_n"] += 1
            s["closed"].append({
                "symbol": r["symbol"], "qty": take,
                "buy_price": lot[1], "sell_price": px,
                "buy_ts": lot[2], "sell_ts": r["ts_utc"],
                "ret_pct": 100 * ret, "pnl": pnl, "spy_ret_pct": (100 * sr) if sr is not None else None,
            })
            lot[0] -= take
            remaining -= take
            if lot[0] <= 1e-9:
                lots[key].popleft()

    for key, dq in lots.items():
        strat, _ = key
        mult = 100 if strat == "options_long_v1" else 1
        for lot in dq:
            per[strat]["still_open"] += 1
            per[strat]["open_cost"] += lot[0] * lot[1] * mult

    for s in per.values():
        n = s["round_trips"]
        s["win_rate"] = (100 * s["wins"] / n) if n else None
        s["avg_return_pct"] = (100 * s["ret_sum"] / n) if n else None
        s["avg_spy_return_pct"] = (100 * s["spy_ret_sum"] / s["spy_n"]) if s["spy_n"] else None
        s["beat_spy"] = (s["avg_return_pct"] is not None and s["avg_spy_return_pct"] is not None
                         and s["avg_return_pct"] > s["avg_spy_return_pct"])
    return dict(per)
