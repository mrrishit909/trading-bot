"""
The website. A little multi-page site on your own computer for watching
the robot.

Pages:
    /            Overview     - account value, chart, today's picks
    /holdings    Holdings     - what we own right now
    /decisions   Decisions    - every BUY/SELL/WAIT with the reasoning
    /trades      Trades       - every trade attempt
    /scoreboard  Scoreboard   - robot vs AI, graded against reality
    /universe    Universe     - the whole big list and the scan signal

Run it like this:
    ./venv/bin/python dashboard.py           (port 8777)
    ./venv/bin/python dashboard.py 9001       (pick your own port)
Then open the address it prints. Ctrl+C to stop.
"""

import os
import sys
import html
import time
import traceback
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

import settings
import diary
from scanner import analyze_all, rank_buys
from grader import grade_all

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8777

load_dotenv()
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)
data = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)


# ---- tiny cache so refreshing doesn't hammer the APIs ------------------
_cache = {}
def cached(key, seconds, make):
    now = time.time()
    if key in _cache and now - _cache[key][0] < seconds:
        return _cache[key][1]
    val = make()
    _cache[key] = (now, val)
    return val


def money(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def pct(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    return f"{v:+.2f}%"


def cls_for(v):
    try:
        return "up" if float(v) >= 0 else "down"
    except (TypeError, ValueError):
        return ""


# ---- page shell ------------------------------------------------------
NAV = [("/", "Overview"), ("/holdings", "Holdings"), ("/options", "Options"),
       ("/decisions", "Decisions"), ("/trades", "Trades"),
       ("/scoreboard", "Scoreboard"), ("/universe", "Universe")]

def shell(path, title, body):
    links = "".join(
        f'<a href="{href}" class="{"on" if href == path else ""}">{label}</a>'
        for href, label in NAV
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title} · Trading Robot</title>
<meta http-equiv="refresh" content="60">
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:-apple-system,system-ui,sans-serif; background:#0f1216; color:#e6e6e6;
         margin:0; padding:0 0 60px; }}
  header {{ padding:18px 26px 0; }}
  h1 {{ margin:0; font-size:20px; }}
  nav {{ display:flex; gap:4px; padding:14px 26px 0; flex-wrap:wrap; border-bottom:1px solid #222933; }}
  nav a {{ padding:8px 14px; color:#8a94a0; text-decoration:none; font-size:14px;
           border-radius:8px 8px 0 0; }}
  nav a.on {{ color:#e6e6e6; background:#171c22; border:1px solid #262d36; border-bottom:1px solid #171c22; }}
  nav a:hover {{ color:#e6e6e6; }}
  main {{ padding:22px 26px; }}
  h2 {{ font-size:14px; color:#8a94a0; text-transform:uppercase; letter-spacing:.5px; margin:26px 0 10px; }}
  .cards {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .card {{ background:#171c22; border:1px solid #262d36; border-radius:10px; padding:14px 18px; min-width:150px; }}
  .label {{ color:#8a94a0; font-size:12px; }}
  .big {{ font-size:22px; font-weight:600; margin-top:4px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th,td {{ text-align:left; padding:7px 10px; border-bottom:1px solid #222933; vertical-align:top; }}
  th {{ color:#8a94a0; font-weight:500; }}
  .up {{ color:#3fb950; }} .down {{ color:#f85149; }}
  .why {{ color:#b6bec8; max-width:460px; }}
  .warn {{ color:#f0a020; white-space:pre-wrap; }}
  .badge {{ padding:2px 8px; border-radius:6px; font-size:11px; font-weight:600; }}
  .badge.buy {{ background:#193c22; color:#3fb950; }}
  .badge.sell {{ background:#3c1a1a; color:#f85149; }}
  .badge.wait {{ background:#2a2f37; color:#8a94a0; }}
  .pill {{ font-size:11px; padding:2px 7px; border-radius:999px; background:#2a2f37; color:#9aa4b0; }}
  .muted {{ color:#8a94a0; font-size:12px; }}
  a.tk {{ color:#6cb6ff; text-decoration:none; }}
</style></head><body>
<header><h1>🤖 Trading Robot <span class="muted">· pretend money · refreshes every 60s</span></h1></header>
<nav>{links}</nav>
<main>{body}</main>
</body></html>"""


# ---- data helpers ---------------------------------------------------
def get_account():
    return cached("account", 20, lambda: trading.get_account())

def get_positions():
    return cached("positions", 20, lambda: list(trading.get_all_positions()))

def get_scan():
    def make():
        held = {p.symbol for p in get_positions()}
        a = analyze_all(data, list(settings.ALLOWED_STOCKS) + list(held))
        short = rank_buys(a, exclude=held)
        return a, short, held
    return cached("scan", 120, make)

def get_scores(lookahead=3):
    return cached(f"scores{lookahead}", 300, lambda: grade_all(data, diary.get_db(), lookahead))


# ---- SVG line chart -------------------------------------------------
def equity_chart(points):
    """points = list of (label, value). Returns an SVG string."""
    vals = [v for _, v in points if v is not None]
    if len(vals) < 2:
        return "<p class='muted'>Need a couple of runs to draw a chart.</p>"
    w, h, pad = 720, 200, 34
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    def x(i): return pad + i * (w - 2 * pad) / (n - 1)
    def y(v): return h - pad - (v - lo) * (h - 2 * pad) / span
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    area = f"{pad},{h-pad} " + line + f" {x(n-1):.1f},{h-pad}"
    last = vals[-1]
    return f"""<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;background:#171c22;border:1px solid #262d36;border-radius:10px">
      <polygon points="{area}" fill="#3fb95022"/>
      <polyline points="{line}" fill="none" stroke="#3fb950" stroke-width="2"/>
      <text x="{pad}" y="16" fill="#8a94a0" font-size="11">{money(hi)}</text>
      <text x="{pad}" y="{h-8}" fill="#8a94a0" font-size="11">{money(lo)}</text>
      <text x="{w-pad}" y="{y(last)-6:.0f}" fill="#e6e6e6" font-size="11" text-anchor="end">{money(last)}</text>
    </svg>"""


# ---- pages --------------------------------------------------------
def page_overview():
    a = get_account()
    equity, cash = float(a.equity), float(a.cash)
    day = equity - float(a.last_equity)
    positions = get_positions()
    total_pl = sum(float(p.unrealized_pl) for p in positions)

    db = diary.get_db()
    runs = db.execute("SELECT ts_utc, equity_after FROM runs WHERE equity_after IS NOT NULL ORDER BY run_id").fetchall()
    chart = equity_chart([(r["ts_utc"], r["equity_after"]) for r in runs])

    try:
        _, short, held = get_scan()
        picks = ", ".join(f'<a class="tk" href="/universe">{s}</a>' for s in short[:8]) or "(none trending up)"
    except Exception:
        picks = "(scan unavailable)"

    holdings_rows = "".join(
        f"<tr><td>{p.symbol}</td><td>{p.qty}</td><td>{money(p.market_value)}</td>"
        f"<td class='{cls_for(p.unrealized_pl)}'>{money(p.unrealized_pl)} "
        f"({pct(float(p.unrealized_plpc)*100)})</td></tr>"
        for p in positions
    ) or "<tr><td colspan='4' class='muted'>Holding nothing — all cash.</td></tr>"

    return f"""
      <div class="cards">
        <div class="card"><div class="label">Account value</div><div class="big">{money(equity)}</div></div>
        <div class="card"><div class="label">Cash</div><div class="big">{money(cash)}</div></div>
        <div class="card"><div class="label">Today's change</div>
          <div class="big {cls_for(day)}">{money(day)}</div></div>
        <div class="card"><div class="label">Open profit/loss</div>
          <div class="big {cls_for(total_pl)}">{money(total_pl)}</div></div>
        <div class="card"><div class="label">Stocks held</div>
          <div class="big">{len(positions)} / {settings.MAX_STOCKS_HELD}</div></div>
      </div>
      <h2>Account value over runs</h2>
      {chart}
      <h2>Scanner's current picks</h2>
      <p>{picks}</p>
      <h2>Holding now</h2>
      <table><tr><th>Stock</th><th>Shares</th><th>Value</th><th>Profit/Loss</th></tr>{holdings_rows}</table>
    """


def page_holdings():
    positions = get_positions()
    if not positions:
        return "<p class='muted'>Holding nothing right now — all cash.</p>"
    rows = ""
    for p in positions:
        pl = float(p.unrealized_pl)
        rows += (f"<tr><td>{p.symbol}</td><td>{p.qty}</td>"
                 f"<td>{money(p.avg_entry_price)}</td><td>{money(p.current_price)}</td>"
                 f"<td>{money(p.market_value)}</td>"
                 f"<td class='{cls_for(pl)}'>{money(pl)} ({pct(float(p.unrealized_plpc)*100)})</td></tr>")
    return f"""<table>
      <tr><th>Stock</th><th>Shares</th><th>Bought at</th><th>Price now</th><th>Value</th><th>Profit/Loss</th></tr>
      {rows}</table>"""


def page_options():
    from options_engine import readable, days_to_expiry
    positions = [p for p in get_positions()
                 if str(getattr(p, "asset_class", "")).endswith("us_option")]

    if positions:
        rows = ""
        for p in positions:
            pl = float(p.unrealized_pl)
            plpc = float(p.unrealized_plpc) * 100
            rows += (f"<tr><td>{readable(p.symbol)}</td><td>{p.qty}</td>"
                     f"<td>{money(float(p.avg_entry_price)*100)}</td>"
                     f"<td>{money(float(p.current_price)*100)}</td>"
                     f"<td>{money(p.market_value)}</td>"
                     f"<td>{days_to_expiry(p.symbol)}</td>"
                     f"<td class='{cls_for(pl)}'>{money(pl)} ({pct(plpc)})</td></tr>")
        held_html = (f"<table><tr><th>Bet</th><th>Contracts</th><th>Paid (each)</th>"
                     f"<th>Now (each)</th><th>Value</th><th>Days left</th><th>Profit/Loss</th></tr>{rows}</table>")
    else:
        held_html = "<p class='muted'>No option bets open right now.</p>"

    db = diary.get_db()
    # realized P/L: pair each SELL with the earlier BUY on the same contract
    trades = db.execute("""
        SELECT t.side, t.fill_price, t.shares, t.note FROM trades t JOIN runs r ON t.run_id=r.run_id
        WHERE r.strategy='options_long_v1' AND t.status='filled' ORDER BY t.trade_id
    """).fetchall()
    paid, got = {}, []
    for t in trades:
        contract = (t["note"] or "").split(" | ")[0]
        amt = (t["fill_price"] or 0) * 100 * (t["shares"] or 0)
        if t["side"] == "buy":
            paid[contract] = paid.get(contract, 0) + amt
        else:
            got.append((contract, amt - paid.get(contract, 0)))
    realized = sum(g for _, g in got)
    realized_html = ""
    if got:
        realized_html = "<h2>Closed bets</h2><table><tr><th>Contract</th><th>Result</th></tr>" + "".join(
            f"<tr><td>{html.escape(c)}</td><td class='{cls_for(g)}'>{money(g)}</td></tr>" for c, g in got
        ) + f"<tr><td><b>Total</b></td><td class='{cls_for(realized)}'><b>{money(realized)}</b></td></tr></table>"

    recent = db.execute("""
        SELECT d.ts_utc, d.symbol, d.action, d.reason FROM decisions d JOIN runs r ON d.run_id=r.run_id
        WHERE r.strategy='options_long_v1' ORDER BY d.decision_id DESC LIMIT 30
    """).fetchall()
    dec_html = "".join(
        f"<tr><td>{r['ts_utc'][:16]}</td><td>{r['symbol']}</td>"
        f"<td><span class='badge {r['action'].lower()}'>{r['action']}</span></td>"
        f"<td class='why'>{html.escape(r['reason'])}</td></tr>" for r in recent
    ) or "<tr><td colspan='4' class='muted'>Nothing yet.</td></tr>"

    return f"""<p class="muted">The options robot only BUYS calls and puts — most it can lose on a bet is what it paid.
      Limits: max {settings.MAX_OPTION_POSITIONS} bets, ${settings.MAX_DOLLARS_PER_OPTION} each,
      auto-exit at +{settings.OPTION_TAKE_PROFIT_PCT}% / -{settings.OPTION_STOP_LOSS_PCT}%.</p>
      <h2>Open option bets</h2>
      {held_html}
      {realized_html}
      <h2>Recent option decisions</h2>
      <table><tr><th>When (UTC)</th><th>Stock</th><th>Call</th><th>Reason</th></tr>{dec_html}</table>"""


def page_decisions(qs):
    db = diary.get_db()
    strat = qs.get("strategy", [None])[0]
    all_strats = [r["strategy"] for r in db.execute("SELECT DISTINCT strategy FROM runs ORDER BY strategy")]
    filt = "WHERE r.strategy = ?" if strat else ""
    args = (strat,) if strat else ()
    rows = db.execute(f"""
        SELECT d.*, r.strategy AS strategy FROM decisions d JOIN runs r ON d.run_id = r.run_id
        {filt} ORDER BY d.decision_id DESC LIMIT 200
    """, args).fetchall()

    chips = '<a href="/decisions" class="pill">all</a> ' + " ".join(
        f'<a href="/decisions?strategy={html.escape(s)}" class="pill">{html.escape(s)}</a>' for s in all_strats)

    body = "".join(
        f"<tr><td>{r['ts_utc'][:16]}</td><td class='muted'>{html.escape(r['strategy'])}</td>"
        f"<td>{r['symbol']}</td>"
        f"<td><span class='badge {r['action'].lower()}'>{r['action']}</span></td>"
        f"<td>{money(r['ref_price'])}</td>"
        f"<td class='why'>{html.escape(r['reason'])}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='6' class='muted'>No decisions yet.</td></tr>"

    return f"""<p>{chips}</p>
      <table><tr><th>When (UTC)</th><th>Strategy</th><th>Stock</th><th>Call</th><th>Price</th><th>Reason</th></tr>
      {body}</table>"""


def page_trades():
    db = diary.get_db()
    rows = db.execute("""
        SELECT t.*, r.strategy AS strategy FROM trades t JOIN runs r ON t.run_id = r.run_id
        ORDER BY t.trade_id DESC LIMIT 200
    """).fetchall()
    body = "".join(
        f"<tr><td>{r['ts_utc'][:16]}</td><td class='muted'>{html.escape(r['strategy'])}</td>"
        f"<td>{r['symbol']}</td><td>{r['side']}</td><td>{r['status']}</td>"
        f"<td>{r['shares'] if r['shares'] is not None else '-'}</td>"
        f"<td>{money(r['fill_price'])}</td><td>{money(r['gross_amount'])}</td>"
        f"<td class='why'>{html.escape(r['note'] or '')}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='9' class='muted'>No trades yet.</td></tr>"
    return f"""<table>
      <tr><th>When (UTC)</th><th>Strategy</th><th>Stock</th><th>Side</th><th>Status</th>
          <th>Shares</th><th>Price</th><th>Amount</th><th>Note</th></tr>{body}</table>"""


def page_scoreboard():
    scores = get_scores(3)
    if not scores:
        return "<p class='muted'>No decisions to grade yet.</p>"
    out = ["<p class='muted'>Each decision graded against what the price actually did 3 trading days later. "
           "\"Benchmark\" = what you'd have earned just staying fully invested.</p>"]
    for strat, s in scores.items():
        out.append(f"<h2>{html.escape(strat)}</h2>")
        if not s["judged"]:
            out.append(f"<p class='muted'>{s['decisions']} decisions logged, "
                       f"{s['pending']} still too recent to grade. Check back in a few days.</p>")
            continue
        diff = s["earned"] - s["benchmark"]
        verdict = ("TIED with" if abs(diff) < 1e-9
                   else ("BEAT" if diff > 0 else "LOST TO"))
        vcls = "up" if diff > 0 else ("down" if diff < 0 else "")
        out.append(f"""<div class="cards">
          <div class="card"><div class="label">Decisions graded</div><div class="big">{s['judged']}</div>
            <div class="muted">{s['pending']} pending</div></div>
          <div class="card"><div class="label">Got direction right</div>
            <div class="big">{s['hit_rate']:.0f}%</div><div class="muted">{s['right']} of {s['judged']}</div></div>
          <div class="card"><div class="label">Avg earned / decision</div>
            <div class="big {cls_for(s['avg_earned_pct'])}">{pct(s['avg_earned_pct'])}</div></div>
          <div class="card"><div class="label">Benchmark / decision</div>
            <div class="big">{pct(s['avg_benchmark_pct'])}</div></div>
          <div class="card"><div class="label">Verdict</div>
            <div class="big {vcls}">{verdict}</div><div class="muted">vs staying invested</div></div>
        </div>""")
    return "".join(out)


def page_universe():
    try:
        analysis, short, held = get_scan()
    except Exception as e:
        return f"<p class='warn'>Scan unavailable: {html.escape(str(e))}</p>"
    short_set = set(short[:settings.SHORTLIST_SIZE])
    rows = []
    for sym in settings.ALLOWED_STOCKS:
        a = analysis.get(sym, {})
        if not a.get("enough_data"):
            rows.append((99, f"<tr><td>{sym}</td><td class='muted' colspan='5'>not enough data</td></tr>"))
            continue
        trend = ("<span class='up'>▲ up</span>" if a["trending_up"] else "<span class='down'>▼ down</span>")
        tags = []
        if sym in held: tags.append("<span class='pill'>held</span>")
        if sym in short_set: tags.append("<span class='pill'>shortlist</span>")
        if a["crossed_up"]: tags.append("<span class='pill'>just crossed up</span>")
        sort_key = (0 if sym in held else 1, 0 if sym in short_set else 1, -a["move_5d_pct"])
        rows.append((sort_key, f"<tr><td>{sym}</td><td>{money(a['price'])}</td><td>{trend}</td>"
                     f"<td class='{cls_for(a['move_1d_pct'])}'>{pct(a['move_1d_pct'])}</td>"
                     f"<td class='{cls_for(a['move_5d_pct'])}'>{pct(a['move_5d_pct'])}</td>"
                     f"<td>{' '.join(tags)}</td></tr>"))
    rows.sort(key=lambda t: t[0])
    body = "".join(r for _, r in rows)
    return f"""<p class="muted">The {len(settings.ALLOWED_STOCKS)} stocks the robot may consider. Sorted: held, then shortlist, then by 5-day move.</p>
      <table><tr><th>Stock</th><th>Price</th><th>Trend (5d vs 20d avg)</th><th>1-day</th><th>5-day</th><th></th></tr>{body}</table>"""


ROUTES = {
    "/": lambda qs: page_overview(),
    "/holdings": lambda qs: page_holdings(),
    "/options": lambda qs: page_options(),
    "/decisions": lambda qs: page_decisions(qs),
    "/trades": lambda qs: page_trades(),
    "/scoreboard": lambda qs: page_scoreboard(),
    "/universe": lambda qs: page_universe(),
}
TITLES = {h: t for h, t in NAV}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        route = ROUTES.get(u.path)
        if route is None:
            self.send_error(404)
            return
        try:
            body = route(parse_qs(u.query))
        except Exception:
            body = f"<p class='warn'>Something went wrong:\n\n{html.escape(traceback.format_exc())}</p>"
        page = shell(u.path, TITLES.get(u.path, "Trading Robot"), body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Website running. Open this in your browser:\n\n    http://localhost:{PORT}\n")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWebsite stopped.")
