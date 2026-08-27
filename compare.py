"""
compare.py - grade the robot vs the AI.

For every decision in the diary, we look up what the stock price actually did
a few trading days later, then ask: was that decision any good?

How we score one decision:
  - If the decision meant "have money in this stock" (BUY, or WAIT while we
    already own it), you earned whatever the stock did next.
  - If the decision meant "stay in cash" (SELL, or WAIT while owning nothing),
    you earned 0 - but we note what you missed (or dodged).

Then for each strategy we add up the earned returns and compare to a simple
benchmark: "what if you just always stayed invested?"

Decisions too recent to judge yet are shown as PENDING.

Run it like this:
    ./venv/bin/python compare.py
    ./venv/bin/python compare.py 5      (judge 5 trading days forward instead of 3)
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import diary

LOOKAHEAD = int(sys.argv[1]) if len(sys.argv) > 1 else 3

load_dotenv()
data = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
db = diary.get_db()

# ---- get every decision, with the strategy that made it -------------------
rows = db.execute("""
    SELECT d.*, r.strategy AS strategy, r.mode AS mode
    FROM decisions d JOIN runs r ON d.run_id = r.run_id
    ORDER BY d.decision_id
""").fetchall()

if not rows:
    print("No decisions in the diary yet. Run the robot and the AI advisor first.")
    raise SystemExit(0)

# ---- fetch daily prices for every symbol we need ------------------------
symbols = sorted({r["symbol"] for r in rows})
earliest = min(datetime.fromisoformat(r["ts_utc"]) for r in rows) - timedelta(days=5)
bars_by_symbol = {}
for sym in symbols:
    bars = data.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=earliest,
    )).data.get(sym, [])
    bars_by_symbol[sym] = [(b.timestamp.date(), b.close) for b in bars]


def forward_return(symbol, decision_dt, entry_price):
    """Return (future_close - entry_price) / entry_price, LOOKAHEAD trading days later.
       Returns None if that day hasn't happened yet."""
    series = bars_by_symbol.get(symbol, [])
    d = decision_dt.date()
    after = [c for (dt, c) in series if dt > d]
    if len(after) < LOOKAHEAD:
        return None
    return (after[LOOKAHEAD - 1] - entry_price) / entry_price


# ---- score every decision ---------------------------------------------
score = defaultdict(lambda: {"judged": 0, "pending": 0, "earned": 0.0,
                             "benchmark": 0.0, "right": 0})

for r in rows:
    strat = r["strategy"]
    dt = datetime.fromisoformat(r["ts_utc"])
    entry = r["ref_price"]
    if entry is None:
        continue

    fr = forward_return(r["symbol"], dt, entry)
    if fr is None:
        score[strat]["pending"] += 1
        continue

    invested = (r["action"] == "BUY") or (r["action"] == "WAIT" and r["owned_before"] == 1)
    earned = fr if invested else 0.0

    # "right" = you were invested and it went up, OR you were in cash and it went down
    was_right = (invested and fr > 0) or (not invested and fr <= 0)

    s = score[strat]
    s["judged"] += 1
    s["earned"] += earned
    s["benchmark"] += fr          # benchmark = always invested
    s["right"] += 1 if was_right else 0

# ---- print the scoreboard -------------------------------------------
print("=" * 66)
print(f"SCOREBOARD   (judging {LOOKAHEAD} trading days after each decision)")
print("=" * 66)

for strat, s in score.items():
    print(f"\n[{strat}]")
    print(f"  decisions judged:      {s['judged']}")
    print(f"  decisions pending:     {s['pending']}  (too recent to grade)")
    if s["judged"] == 0:
        print("  Not enough time has passed to grade this one yet.")
        continue
    hit_rate = 100 * s["right"] / s["judged"]
    avg_earned = 100 * s["earned"] / s["judged"]
    avg_bench = 100 * s["benchmark"] / s["judged"]
    print(f"  got the direction right: {s['right']}/{s['judged']}  ({hit_rate:.0f}%)")
    print(f"  avg return it earned:    {avg_earned:+.2f}% per decision")
    print(f"  avg 'always invested':   {avg_bench:+.2f}% per decision  (the benchmark)")
    diff = s["earned"] - s["benchmark"]
    if abs(diff) < 1e-9:
        print("  --> this strategy TIED with just staying invested "
              "(it was always fully invested).")
    else:
        verdict = "BEAT" if diff > 0 else "LOST TO"
        print(f"  --> this strategy {verdict} just staying invested "
              f"by {abs(100 * diff / s['judged']):.2f}% per decision.")

print("\n" + "=" * 66)
print("Reminder: a few decisions prove nothing. Let it run for weeks.")
print("Also: 'beating the benchmark' on paper often disappears with real costs.")
