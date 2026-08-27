"""
STEP 8 (part 2): A webpage to watch the robot.

Starts a tiny web server on your own computer. Open the address it prints
in your browser and you'll see:
  - how much pretend money you have right now
  - what the robot is holding
  - its recent decisions and trades (from diary.db)

The page refreshes itself every 30 seconds.

Run it like this:
    ./venv/bin/python dashboard.py           (uses port 8777)
    ./venv/bin/python dashboard.py 9001       (pick your own port)
Then open the http://localhost:... address it prints. Ctrl+C to stop.
"""

import os
import sys
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
import diary

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8777

load_dotenv()
trading = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)


def money(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def account_section():
    try:
        a = trading.get_account()
        equity = float(a.equity)
        last = float(a.last_equity)
        day_change = equity - last
        color = "up" if day_change >= 0 else "down"
        return f"""
        <div class="cards">
          <div class="card"><div class="label">Account value</div><div class="big">{money(equity)}</div></div>
          <div class="card"><div class="label">Cash</div><div class="big">{money(a.cash)}</div></div>
          <div class="card"><div class="label">Today's change</div>
            <div class="big {color}">{'+' if day_change >= 0 else ''}{money(day_change)}</div></div>
        </div>"""
    except Exception as e:
        return f"<p class='warn'>Couldn't reach Alpaca for account info: {html.escape(str(e))}</p>"


def holdings_section():
    try:
        positions = trading.get_all_positions()
    except Exception as e:
        return f"<p class='warn'>Couldn't load holdings: {html.escape(str(e))}</p>"
    if not positions:
        return "<p>Holding nothing right now (all cash).</p>"
    rows = ""
    for p in positions:
        pl = float(p.unrealized_pl)
        cls = "up" if pl >= 0 else "down"
        rows += (f"<tr><td>{p.symbol}</td><td>{p.qty}</td>"
                 f"<td>{money(p.avg_entry_price)}</td><td>{money(p.current_price)}</td>"
                 f"<td>{money(p.market_value)}</td>"
                 f"<td class='{cls}'>{'+' if pl >= 0 else ''}{money(pl)}</td></tr>")
    return f"""<table>
      <tr><th>Stock</th><th>Shares</th><th>Bought at</th><th>Now</th><th>Value</th><th>Profit/Loss</th></tr>
      {rows}</table>"""


def runs_section(db):
    rows = db.execute("SELECT * FROM runs ORDER BY run_id DESC LIMIT 15").fetchall()
    if not rows:
        return "<p>No runs yet.</p>"
    out = "<table><tr><th>Run</th><th>When (UTC)</th><th>Mode</th><th>Value before</th><th>Value after</th><th>Change</th></tr>"
    for r in rows:
        before = r["equity_before"] or 0
        after = r["equity_after"] if r["equity_after"] is not None else before
        change = after - before
        cls = "up" if change >= 0 else "down"
        out += (f"<tr><td>{r['run_id']}</td><td>{r['ts_utc'][:19]}</td><td>{r['mode']}</td>"
                f"<td>{money(before)}</td><td>{money(after)}</td>"
                f"<td class='{cls}'>{'+' if change >= 0 else ''}{money(change)}</td></tr>")
    return out + "</table>"


def decisions_section(db):
    rows = db.execute("SELECT * FROM decisions ORDER BY decision_id DESC LIMIT 20").fetchall()
    if not rows:
        return "<p>No decisions yet.</p>"
    out = "<table><tr><th>When</th><th>Stock</th><th>Action</th><th>Fast avg</th><th>Slow avg</th><th>Why</th></tr>"
    for r in rows:
        badge = {"BUY": "buy", "SELL": "sell", "WAIT": "wait"}.get(r["action"], "wait")
        out += (f"<tr><td>{r['ts_utc'][:16]}</td><td>{r['symbol']}</td>"
                f"<td><span class='badge {badge}'>{r['action']}</span></td>"
                f"<td>{money(r['fast_avg'])}</td><td>{money(r['slow_avg'])}</td>"
                f"<td class='why'>{html.escape(r['reason'])}</td></tr>")
    return out + "</table>"


def trades_section(db):
    rows = db.execute("SELECT * FROM trades ORDER BY trade_id DESC LIMIT 20").fetchall()
    if not rows:
        return "<p>No trades yet.</p>"
    out = "<table><tr><th>When</th><th>Stock</th><th>Side</th><th>Status</th><th>Shares</th><th>Price</th><th>Amount</th><th>Note</th></tr>"
    for r in rows:
        out += (f"<tr><td>{r['ts_utc'][:16]}</td><td>{r['symbol']}</td><td>{r['side']}</td>"
                f"<td>{r['status']}</td><td>{r['shares'] if r['shares'] is not None else '-'}</td>"
                f"<td>{money(r['fill_price'])}</td><td>{money(r['gross_amount'])}</td>"
                f"<td class='why'>{html.escape(r['note'] or '')}</td></tr>")
    return out + "</table>"


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Trading Robot</title>
<meta http-equiv="refresh" content="30">
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background:#0f1216; color:#e6e6e6;
         margin:0; padding:24px; }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .sub {{ color:#8a94a0; font-size:13px; margin-bottom:20px; }}
  h2 {{ font-size:15px; color:#8a94a0; text-transform:uppercase; letter-spacing:.5px;
        margin:28px 0 10px; }}
  .cards {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .card {{ background:#171c22; border:1px solid #262d36; border-radius:10px; padding:14px 18px; min-width:150px; }}
  .label {{ color:#8a94a0; font-size:12px; }}
  .big {{ font-size:22px; font-weight:600; margin-top:4px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid #222933; }}
  th {{ color:#8a94a0; font-weight:500; }}
  .up {{ color:#3fb950; }}
  .down {{ color:#f85149; }}
  .why {{ color:#b6bec8; max-width:420px; }}
  .warn {{ color:#f0a020; }}
  .badge {{ padding:2px 8px; border-radius:6px; font-size:11px; font-weight:600; }}
  .badge.buy {{ background:#193c22; color:#3fb950; }}
  .badge.sell {{ background:#3c1a1a; color:#f85149; }}
  .badge.wait {{ background:#2a2f37; color:#8a94a0; }}
</style></head>
<body>
  <h1>🤖 Trading Robot</h1>
  <div class="sub">pretend money · page refreshes every 30s</div>
  {account}
  <h2>Holding right now</h2>
  {holdings}
  <h2>Recent runs</h2>
  {runs}
  <h2>Recent decisions</h2>
  {decisions}
  <h2>Recent trades</h2>
  {trades}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        db = diary.get_db()
        body = PAGE.format(
            account=account_section(),
            holdings=holdings_section(),
            runs=runs_section(db),
            decisions=decisions_section(db),
            trades=trades_section(db),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep the terminal quiet


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard running. Open this in your browser:\n\n    http://localhost:{PORT}\n")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
