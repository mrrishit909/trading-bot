"""
STEP 7: The diary.

Everything the robot does gets written into a little database file called
diary.db. Nothing is ever deleted. Later we can open it and ask questions like
"how many times did the robot buy Apple, and did it make money each time?"

Three tables:
  runs      - one row every time we run the robot
  decisions - one row for every stock the robot thought about (BUY/SELL/WAIT + why)
  trades    - one row for every trade attempt (filled, blocked, skipped, or pretend)

To look at the diary later:  ./venv/bin/python show_diary.py
"""

import sqlite3
import json
import os
from datetime import datetime, timezone

# Which diary file to use. auto_run.py / the dashboard set ROBOT_DIARY_PATH when
# running a non-main account profile; otherwise it's the original diary.db.
DB_PATH = (os.environ.get("ROBOT_DIARY_PATH")
           or os.path.join(os.path.dirname(__file__), "diary.db"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc        TEXT NOT NULL,
            mode          TEXT NOT NULL,          -- 'live' or 'pretend'
            strategy      TEXT NOT NULL,          -- which rule made the calls
            equity_before REAL,
            cash_before   REAL,
            equity_after  REAL,
            cash_after    REAL
        );

        CREATE TABLE IF NOT EXISTS decisions (
            decision_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER NOT NULL REFERENCES runs(run_id),
            ts_utc       TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            action       TEXT NOT NULL,           -- BUY / SELL / WAIT
            reason       TEXT NOT NULL,
            owned_before INTEGER NOT NULL,        -- 0 or 1
            fast_avg     REAL,
            slow_avg     REAL,
            ref_price    REAL,                    -- market price at decision time
            context_json TEXT                     -- full detail for replay (closes, params, bid/ask...)
        );

        CREATE TABLE IF NOT EXISTS trades (
            trade_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id    INTEGER REFERENCES decisions(decision_id),
            run_id         INTEGER NOT NULL REFERENCES runs(run_id),
            ts_utc         TEXT NOT NULL,
            symbol         TEXT NOT NULL,
            side           TEXT NOT NULL,         -- buy / sell
            status         TEXT NOT NULL,         -- filled / blocked / skipped / not_filled / pretend
            shares         REAL,
            fill_price     REAL,
            gross_amount   REAL,                  -- shares * fill_price
            order_id       TEXT,
            note           TEXT,                  -- e.g. bouncer's reason for blocking
            equity_before  REAL,
            cash_before    REAL
        );
    """)
    db.commit()
    return db


def start_run(db, mode, strategy, equity_before, cash_before):
    cur = db.execute(
        "INSERT INTO runs (ts_utc, mode, strategy, equity_before, cash_before) VALUES (?,?,?,?,?)",
        (_now(), mode, strategy, equity_before, cash_before),
    )
    db.commit()
    return cur.lastrowid


def finish_run(db, run_id, equity_after, cash_after):
    db.execute(
        "UPDATE runs SET equity_after = ?, cash_after = ? WHERE run_id = ?",
        (equity_after, cash_after, run_id),
    )
    db.commit()


def log_decision(db, run_id, symbol, action, reason, owned_before,
                 fast_avg, slow_avg, ref_price, context):
    cur = db.execute(
        """INSERT INTO decisions
           (run_id, ts_utc, symbol, action, reason, owned_before, fast_avg, slow_avg, ref_price, context_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (run_id, _now(), symbol.upper(), action, reason, 1 if owned_before else 0,
         fast_avg, slow_avg, ref_price, json.dumps(context)),
    )
    db.commit()
    return cur.lastrowid


def log_trade(db, run_id, decision_id, symbol, side, status,
              shares=None, fill_price=None, order_id=None, note=None,
              equity_before=None, cash_before=None):
    gross = (shares * fill_price) if (shares is not None and fill_price is not None) else None
    db.execute(
        """INSERT INTO trades
           (decision_id, run_id, ts_utc, symbol, side, status, shares, fill_price,
            gross_amount, order_id, note, equity_before, cash_before)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (decision_id, run_id, _now(), symbol.upper(), side, status, shares, fill_price,
         gross, order_id, note, equity_before, cash_before),
    )
    db.commit()


def already_scaled_out(db, strategy, symbol):
    """True if we've already taken a partial 'scale-out' profit on the CURRENT
    holding of `symbol` — i.e. a filled sell noted 'scale-out' dated after the
    most recent filled buy of it. Resets automatically on a fresh entry."""
    row = db.execute(
        """SELECT MAX(t.ts_utc) AS last_buy
           FROM trades t JOIN runs r ON t.run_id = r.run_id
           WHERE r.strategy = ? AND t.symbol = ? AND t.side = 'buy' AND t.status = 'filled'""",
        (strategy, symbol.upper()),
    ).fetchone()
    last_buy = row["last_buy"] if row else None
    if not last_buy:
        return False
    hit = db.execute(
        """SELECT 1 FROM trades t JOIN runs r ON t.run_id = r.run_id
           WHERE r.strategy = ? AND t.symbol = ? AND t.side = 'sell'
             AND t.status = 'filled' AND COALESCE(t.note, '') LIKE '%scale-out%'
             AND t.ts_utc > ? LIMIT 1""",
        (strategy, symbol.upper(), last_buy),
    ).fetchone()
    return hit is not None


def last_buy_ts(db, strategy, symbol):
    """UTC ISO timestamp of the most recent FILLED buy of `symbol` by this
    strategy, or None if we've never (knowably) bought it."""
    row = db.execute(
        """SELECT MAX(t.ts_utc) AS ts FROM trades t JOIN runs r ON t.run_id = r.run_id
           WHERE r.strategy = ? AND t.symbol = ? AND t.side = 'buy' AND t.status = 'filled'""",
        (strategy, symbol.upper()),
    ).fetchone()
    return row["ts"] if row and row["ts"] else None


def recently_sold(db, strategy, days):
    """Symbols this strategy actually SOLD (filled) within the last `days` days —
    used for the re-buy cooldown so we don't churn in and out of the same name."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.execute(
        """SELECT DISTINCT t.symbol
           FROM trades t JOIN runs r ON t.run_id = r.run_id
           WHERE t.side = 'sell' AND t.status = 'filled'
             AND r.strategy = ? AND t.ts_utc >= ?""",
        (strategy, cutoff),
    ).fetchall()
    return {r["symbol"].upper() for r in rows}
