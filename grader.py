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


def grade_all(data_client, db, lookahead=3):
    rows = db.execute("""
        SELECT d.symbol, d.action, d.owned_before, d.ref_price, d.ts_utc, r.strategy AS strategy
        FROM decisions d JOIN runs r ON d.run_id = r.run_id
        WHERE r.strategy != 'options_long_v1'   -- options P/L is tracked on the Options page
        ORDER BY d.decision_id
    """).fetchall()
    if not rows:
        return {}

    symbols = sorted({r["symbol"] for r in rows})
    earliest = min(datetime.fromisoformat(r["ts_utc"]) for r in rows) - timedelta(days=5)
    bars = data_client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=earliest,
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
