"""
Look at the robot's diary.

Run it like this:
    ./venv/bin/python show_diary.py            (show a summary + recent activity)
    ./venv/bin/python show_diary.py trades     (show every trade)
    ./venv/bin/python show_diary.py decisions  (show every decision)
    ./venv/bin/python show_diary.py runs       (show every run)
"""

import sys
import diary

db = diary.get_db()
what = sys.argv[1] if len(sys.argv) > 1 else "summary"


def show_runs():
    rows = db.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
    print(f"\n{'RUN':>4}  {'WHEN (UTC)':<20} {'MODE':<8} {'EQUITY BEFORE':>14} {'EQUITY AFTER':>14} {'CHANGE':>10}")
    print("-" * 78)
    for r in rows:
        before = r["equity_before"] or 0
        after = r["equity_after"] or before
        change = after - before
        print(f"{r['run_id']:>4}  {r['ts_utc'][:19]:<20} {r['mode']:<8} "
              f"{before:>14,.2f} {after:>14,.2f} {change:>+10,.2f}")


def show_decisions():
    rows = db.execute("SELECT * FROM decisions ORDER BY decision_id").fetchall()
    print(f"\n{'ID':>4} {'RUN':>4}  {'WHEN':<17} {'SYM':<5} {'ACTION':<6} {'FAST':>9} {'SLOW':>9}  WHY")
    print("-" * 100)
    for r in rows:
        fast = f"{r['fast_avg']:,.2f}" if r["fast_avg"] else "-"
        slow = f"{r['slow_avg']:,.2f}" if r["slow_avg"] else "-"
        print(f"{r['decision_id']:>4} {r['run_id']:>4}  {r['ts_utc'][:16]:<17} {r['symbol']:<5} "
              f"{r['action']:<6} {fast:>9} {slow:>9}  {r['reason'][:55]}")


def show_trades():
    rows = db.execute("SELECT * FROM trades ORDER BY trade_id").fetchall()
    print(f"\n{'ID':>4} {'RUN':>4}  {'WHEN':<17} {'SYM':<5} {'SIDE':<4} {'STATUS':<10} "
          f"{'SHARES':>8} {'PRICE':>10} {'AMOUNT':>12}  NOTE")
    print("-" * 105)
    for r in rows:
        shares = f"{r['shares']:g}" if r["shares"] is not None else "-"
        price = f"{r['fill_price']:,.2f}" if r["fill_price"] is not None else "-"
        amount = f"{r['gross_amount']:,.2f}" if r["gross_amount"] is not None else "-"
        print(f"{r['trade_id']:>4} {r['run_id']:>4}  {r['ts_utc'][:16]:<17} {r['symbol']:<5} "
              f"{r['side']:<4} {r['status']:<10} {shares:>8} {price:>10} {amount:>12}  {r['note'] or ''}")


def show_summary():
    n_runs = db.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
    n_dec = db.execute("SELECT COUNT(*) c FROM decisions").fetchone()["c"]
    n_fill = db.execute("SELECT COUNT(*) c FROM trades WHERE status='filled'").fetchone()["c"]
    n_block = db.execute("SELECT COUNT(*) c FROM trades WHERE status='blocked'").fetchone()["c"]

    print("\n=== ROBOT DIARY SUMMARY ===")
    print(f"  Runs so far:        {n_runs}")
    print(f"  Decisions made:     {n_dec}")
    print(f"  Trades filled:      {n_fill}")
    print(f"  Trades blocked:     {n_block}")

    by_action = db.execute(
        "SELECT action, COUNT(*) c FROM decisions GROUP BY action ORDER BY c DESC").fetchall()
    if by_action:
        print("  Decisions breakdown: " + ", ".join(f"{r['action']} {r['c']}" for r in by_action))

    filled = db.execute(
        "SELECT symbol, side, shares, fill_price FROM trades WHERE status='filled' "
        "ORDER BY trade_id DESC LIMIT 10").fetchall()
    if filled:
        print("\n  Last few filled trades:")
        for r in filled:
            print(f"    {r['side'].upper():<4} {r['shares']:g} {r['symbol']} @ ${r['fill_price']:,.2f}")
    print("\n  (use: show_diary.py trades | decisions | runs  for full lists)")


{"summary": show_summary, "runs": show_runs,
 "decisions": show_decisions, "trades": show_trades}.get(what, show_summary)()
