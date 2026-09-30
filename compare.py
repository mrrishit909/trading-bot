"""
compare.py - grade the robot vs the AI, printed in the terminal.

(The actual scoring lives in grader.py, so the website can use it too.)

Run it like this:
    ./venv/bin/python compare.py        (judge 10 trading days after each decision)
    ./venv/bin/python compare.py 5      (judge 5 trading days forward)
"""

import os
import sys
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
import settings
import diary
from grader import grade_all, grade_trades

LOOKAHEAD = int(sys.argv[1]) if len(sys.argv) > 1 else 10

load_dotenv()
data = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
db = diary.get_db()

scores = grade_all(data, db, lookahead=LOOKAHEAD)
if not scores:
    print("No decisions in the diary yet. Run the robot and the AI advisor first.")
    raise SystemExit(0)

print("=" * 66)
print(f"SCOREBOARD   (judging {LOOKAHEAD} trading days after each decision)")
print("=" * 66)

for strat, s in scores.items():
    print(f"\n[{strat}]")
    print(f"  decisions judged:      {s['judged']}")
    print(f"  decisions pending:     {s['pending']}  (too recent to grade)")
    if not s["judged"]:
        print("  Not enough time has passed to grade this one yet.")
        continue
    print(f"  got the direction right: {s['right']}/{s['judged']}  ({s['hit_rate']:.0f}%)")
    print(f"  avg return it earned:    {s['avg_earned_pct']:+.2f}% per decision")
    print(f"  avg 'always invested':   {s['avg_benchmark_pct']:+.2f}% per decision  (benchmark)")
    diff = s["earned"] - s["benchmark"]
    if abs(diff) < 1e-9:
        print("  --> TIED with just staying invested (it was always fully invested).")
    else:
        verdict = "BEAT" if diff > 0 else "LOST TO"
        print(f"  --> {verdict} just staying invested by "
              f"{abs(100 * diff / s['judged']):.2f}% per decision.")

print("\n" + "=" * 66)
print("Reminder: a few decisions prove nothing. Let it run for weeks.")
print("Also: 'beating the benchmark' on paper often disappears with real costs.")

# ---------- the honest money view: completed round-trip trades ----------
print("\n" + "=" * 66)
print("REAL TRADES   (each completed buy->sell counted once, actual P/L)")
print("=" * 66)
trades = grade_trades(data, db)
if not trades:
    print("\nNo completed round-trip trades yet (need a buy AND its later sell).")
for strat, s in trades.items():
    print(f"\n[{strat}]")
    print(f"  completed trades:     {s['round_trips']}   (still open: {s['still_open']})")
    if not s["round_trips"]:
        continue
    print(f"  won / lost:            {s['wins']} won, {s['round_trips'] - s['wins']} lost  "
          f"({s['win_rate']:.0f}% win rate)")
    print(f"  average trade:         {s['avg_return_pct']:+.2f}%")
    print(f"  best / worst:          {100*s['best_pct']:+.1f}%  /  {100*s['worst_pct']:+.1f}%")
    print(f"  total realised profit: ${s['realised_pnl']:+,.2f}")
    if s["avg_spy_return_pct"] is not None:
        vs = s["avg_return_pct"] - s["avg_spy_return_pct"]
        word = "BEAT" if vs > 0 else "LOST TO"
        print(f"  same money in SPY:     {s['avg_spy_return_pct']:+.2f}% per trade  "
              f"--> {word} the index by {abs(vs):.2f}%/trade")
print("\n" + "=" * 66)
print(f"This is the number that matters. A {settings.STOCK_SLIPPAGE_PCT}% (stocks) / "
      f"{settings.CRYPTO_SLIPPAGE_PCT}% (crypto) slippage haircut is already priced in on "
      "both legs of every trade — see settings.py — so this is close to what real trading "
      "would look like, not an optimistic paper-fill number.")
