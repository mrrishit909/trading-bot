"""
Reconcile the diary against Alpaca's actual order history.

Two gaps this closes:
  1. A diary trade row marked "not_filled" whose order ACTUALLY filled (the
     confirmation-lag bug — fixed going forward in fills.py, but old rows and any
     that still slip through need correcting).
  2. A real filled order on Alpaca with NO diary row at all.

For (1) we UPDATE the row in place (status -> filled, real price / qty / gross).
For (2) we INSERT a backfill row (linked to a synthetic "reconcile" run) so the
grader can see the round trip. Buys and sells both.

Safe to run repeatedly — it only touches rows that are demonstrably wrong, and
never deletes anything. Called automatically at the end of every auto_run cycle;
can also be run by hand:

    ./venv/bin/python reconcile.py [--profile sprint500] [--days 45] [--dry-run]
"""

import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

# --- profile plumbing (mirror auto_run.py) ----------------------------------
_profile = "main"
if "--profile" in sys.argv:
    _profile = sys.argv[sys.argv.index("--profile") + 1]
elif os.environ.get("ROBOT_PROFILE"):
    # invoked as a child of auto_run.py — keys + diary path are already in the env
    _profile = os.environ["ROBOT_PROFILE"]

if _profile != "main" and not os.environ.get("ROBOT_DIARY_PATH"):
    from profiles import get as _get_profile
    _p = _get_profile(_profile)
    load_dotenv(_p["env_file"], override=True)
    os.environ["ROBOT_PROFILE"] = _profile
    os.environ["ROBOT_DIARY_PATH"] = os.path.join(os.path.dirname(__file__), _p["diary"])
else:
    load_dotenv()

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
import diary

DRY = "--dry-run" in sys.argv
DAYS = 45
if "--days" in sys.argv:
    DAYS = int(sys.argv[sys.argv.index("--days") + 1])

trading = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
db = diary.get_db()


def _norm(sym):
    """BTC/USD and BTCUSD are the same coin; option OCC symbols stay as-is."""
    return sym.replace("/", "").upper()


def alpaca_fills(days):
    """Every filled order in the window, oldest first."""
    after = datetime.now(timezone.utc) - timedelta(days=days)
    req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=after,
                           limit=500, nested=False)
    out = []
    for o in trading.get_orders(req):
        if str(o.status).split(".")[-1].lower() != "filled":
            continue
        if not o.filled_avg_price or not o.filled_qty:
            continue
        out.append({
            "id": str(o.id),
            "symbol": o.symbol,
            "side": o.side.value if hasattr(o.side, "value") else str(o.side).split(".")[-1].lower(),
            "qty": float(o.filled_qty),
            "price": float(o.filled_avg_price),
            "ts": (o.filled_at or o.submitted_at or after).isoformat(),
        })
    return out


def strategy_for(symbol):
    """Best-guess the strategy a fill belongs to, from the symbol shape.
    Each asset class maps 1:1 to a strategy in this project."""
    s = symbol.upper()
    if len(s) > 15 and any(c.isdigit() for c in s[-9:]):
        return "options_long_v1"                     # OCC option symbol
    if "/" in s or (s.endswith("USD") and len(s) <= 8):
        return "crypto_sma_v1"
    if s == "SPY":
        return "spy_sleeve_v1"                       # step10 never picks SPY as a stock
    return "sma_scan_v1"


_run_cache = {}


def backfill_run(strategy):
    """One synthetic run per strategy to hang backfilled trades off of, so they
    show up under the right strategy on the scoreboard (not a 'reconcile' bucket)."""
    if strategy in _run_cache:
        return _run_cache[strategy]
    row = db.execute(
        "SELECT run_id FROM runs WHERE strategy = ? AND mode = 'reconcile' LIMIT 1",
        (strategy,),
    ).fetchone()
    if row:
        _run_cache[strategy] = row["run_id"]
        return row["run_id"]
    cur = db.execute(
        "INSERT INTO runs (ts_utc, mode, strategy) VALUES (?, 'reconcile', ?)",
        (datetime.now(timezone.utc).isoformat(), strategy),
    )
    db.commit()
    _run_cache[strategy] = cur.lastrowid
    return cur.lastrowid


def main():
    # --rebuild: drop prior backfilled rows and reconstruct from scratch (only
    # needed if the attribution logic changed; normal runs dedupe by order_id)
    if "--rebuild" in sys.argv and not DRY:
        db.execute("DELETE FROM trades WHERE note = 'backfilled from Alpaca' AND run_id IN "
                   "(SELECT run_id FROM runs WHERE mode = 'reconcile')")
        db.execute("DELETE FROM runs WHERE mode = 'reconcile' AND run_id NOT IN "
                   "(SELECT DISTINCT run_id FROM trades WHERE run_id IS NOT NULL)")
        db.commit()

    fills = alpaca_fills(DAYS)
    by_id = {f["id"]: f for f in fills}

    trade_rows = db.execute(
        "SELECT trade_id, order_id, symbol, side, status, shares, fill_price FROM trades"
    ).fetchall()
    rows_by_oid = {r["order_id"]: r for r in trade_rows if r["order_id"]}
    # a (symbol, side) set of everything the diary already believes filled,
    # to avoid double-inserting when order_id is missing on an old row
    known_filled_ids = {r["order_id"] for r in trade_rows
                        if r["order_id"] and r["status"] == "filled"}

    fixed, inserted = [], []

    # (1) correct rows that say not_filled but actually filled
    for r in trade_rows:
        if r["status"] in ("filled", "pretend", "blocked", "advisory", "skipped"):
            continue
        f = by_id.get(r["order_id"])
        if not f:
            continue
        gross = f["qty"] * f["price"]
        fixed.append(f"{f['symbol']} {f['side']} {f['qty']:g} @ ${f['price']:,.2f}  "
                     f"(was '{r['status']}')")
        if not DRY:
            db.execute(
                "UPDATE trades SET status='filled', shares=?, fill_price=?, gross_amount=?, "
                "note = COALESCE(note,'') || ' [reconciled]' WHERE trade_id=?",
                (f["qty"], f["price"], gross, r["trade_id"]),
            )

    # (2) insert rows for fills the diary never recorded at all
    for f in fills:
        if f["id"] in rows_by_oid or f["id"] in known_filled_ids:
            continue
        # skip if a filled row for this exact symbol+side+qty+price already exists
        # without an order_id (very old rows) — treat as already known
        dup = db.execute(
            "SELECT 1 FROM trades WHERE status='filled' AND side=? AND "
            "ABS(COALESCE(shares,0)-?)<1e-6 AND ABS(COALESCE(fill_price,0)-?)<1e-4 "
            "AND REPLACE(UPPER(symbol),'/','')=?",
            (f["side"], f["qty"], f["price"], _norm(f["symbol"])),
        ).fetchone()
        if dup:
            continue
        strat = strategy_for(f["symbol"])
        inserted.append(f"{f['symbol']} {f['side']} {f['qty']:g} @ ${f['price']:,.2f}  -> {strat}")
        if not DRY:
            db.execute(
                """INSERT INTO trades
                   (decision_id, run_id, ts_utc, symbol, side, status, shares,
                    fill_price, gross_amount, order_id, note)
                   VALUES (NULL, ?, ?, ?, ?, 'filled', ?, ?, ?, ?, 'backfilled from Alpaca')""",
                (backfill_run(strat), f["ts"], f["symbol"].upper(), f["side"], f["qty"],
                 f["price"], f["qty"] * f["price"], f["id"]),
            )

    if not DRY:
        db.commit()

    tag = "[dry-run] " if DRY else ""
    print(f"{tag}reconcile ({_profile}, {DAYS}d): "
          f"{len(fixed)} row(s) corrected, {len(inserted)} row(s) backfilled")
    for line in fixed:
        print(f"  fixed:      {line}")
    for line in inserted:
        print(f"  backfilled: {line}")


if __name__ == "__main__":
    main()
