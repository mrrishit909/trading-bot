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
       ("/crypto", "Crypto"), ("/decisions", "Decisions"), ("/trades", "Trades"),
       ("/scoreboard", "Scoreboard"), ("/universe", "Universe")]

def shell(path, title, body):
    links = "".join(
        f'<a href="{href}" class="{"on" if href == path else ""}">{label}</a>'
        for href, label in NAV
    )
    stamp = f"{datetime.now(timezone.utc):%H:%M UTC}"
    # wrap plain tables in a rounded panel for the polished look
    body = body.replace("<table>", '<div class="panel"><table>').replace("</table>", "</table></div>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Trading Robot</title>
<meta http-equiv="refresh" content="60">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#0a0d12; --surface:#12171f; --surface-2:#161c26; --raised:#1b2230;
    --border:#242d3a; --border-soft:#1b222d;
    --text:#e9edf2; --dim:#93a0b1; --faint:#5c6775;
    --accent:#4be0a8; --accent-dim:#2f9d78;
    --up:#40dd83; --down:#ff6f6f;
    --buy-bg:#12301f; --buy-fg:#5fe39a;
    --sell-bg:#331717; --sell-fg:#ff8a8a;
    --wait-bg:#232a36; --wait-fg:#9aa7b6;
  }}
  * {{ box-sizing:border-box; }}
  html {{ -webkit-text-size-adjust:100%; }}
  body {{
    font-family:'Inter',-apple-system,system-ui,'Segoe UI',sans-serif;
    background:var(--bg); color:var(--text); margin:0; padding:0 0 72px;
    font-size:14px; line-height:1.5; letter-spacing:-0.005em;
    background-image:radial-gradient(900px 500px at 78% -8%, rgba(75,224,168,.07), transparent 70%);
    background-attachment:fixed;
  }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:0 24px; }}
  a {{ color:inherit; }}

  header {{
    position:sticky; top:0; z-index:20; backdrop-filter:blur(10px);
    background:rgba(10,13,18,.72); border-bottom:1px solid var(--border-soft);
  }}
  .head-in {{ display:flex; align-items:center; justify-content:space-between; padding:14px 0 13px; }}
  h1 {{ margin:0; font-size:16px; font-weight:600; letter-spacing:-0.01em; display:flex; align-items:center; gap:9px; }}
  h1 .dot {{ width:8px; height:8px; border-radius:50%; background:var(--accent); box-shadow:0 0 10px var(--accent); }}
  .head-meta {{ font-size:11.5px; color:var(--faint); font-family:'JetBrains Mono',monospace; }}

  nav {{
    position:sticky; top:47px; z-index:19; backdrop-filter:blur(10px);
    background:rgba(10,13,18,.72); border-bottom:1px solid var(--border-soft);
  }}
  .nav-in {{ display:flex; gap:2px; padding:8px 0; flex-wrap:wrap; }}
  nav a {{
    padding:7px 13px; color:var(--dim); text-decoration:none; font-size:13px; font-weight:500;
    border-radius:8px; transition:background .15s, color .15s;
  }}
  nav a:hover {{ color:var(--text); background:var(--surface-2); }}
  nav a.on {{ color:var(--accent); background:rgba(75,224,168,.1); }}

  main {{ padding-top:26px; }}
  main.wrap p {{ color:var(--dim); }}

  h2 {{
    font-size:11.5px; color:var(--faint); text-transform:uppercase; letter-spacing:.09em;
    font-weight:600; margin:30px 0 12px;
  }}

  .cards {{ display:flex; gap:12px; flex-wrap:wrap; }}
  .card {{
    background:linear-gradient(180deg, var(--raised), var(--surface));
    border:1px solid var(--border); border-radius:13px; padding:15px 17px; min-width:150px; flex:1 1 150px;
    box-shadow:0 1px 0 rgba(255,255,255,.03) inset;
  }}
  .label {{ color:var(--faint); font-size:10.5px; text-transform:uppercase; letter-spacing:.07em; font-weight:600; }}
  .big {{
    font-size:23px; font-weight:600; margin-top:6px; letter-spacing:-0.02em;
    font-family:'JetBrains Mono',monospace;
  }}
  .card .muted {{ margin-top:3px; }}

  .panel {{ border:1px solid var(--border); border-radius:13px; overflow:hidden; background:var(--surface); }}
  .panel + .panel {{ margin-top:14px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th {{
    background:var(--surface-2); color:var(--faint); font-weight:600; font-size:10.5px;
    text-transform:uppercase; letter-spacing:.06em; padding:10px 14px; text-align:left;
    border-bottom:1px solid var(--border); white-space:nowrap;
  }}
  td {{
    padding:10px 14px; border-bottom:1px solid var(--border-soft); vertical-align:top;
    font-variant-numeric:tabular-nums;
  }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:rgba(255,255,255,.022); }}

  .up {{ color:var(--up); }} .down {{ color:var(--down); }}
  .why {{ color:var(--dim); max-width:520px; font-size:12.5px; }}
  .muted {{ color:var(--faint); font-size:12px; }}
  .warn {{
    color:#ffcf7a; white-space:pre-wrap; background:rgba(255,180,90,.08);
    border:1px solid rgba(255,180,90,.2); border-radius:10px; padding:12px 14px; font-size:12.5px;
  }}
  .badge {{ padding:3px 9px; border-radius:7px; font-size:10.5px; font-weight:700; letter-spacing:.03em; }}
  .badge.buy {{ background:var(--buy-bg); color:var(--buy-fg); }}
  .badge.sell {{ background:var(--sell-bg); color:var(--sell-fg); }}
  .badge.wait {{ background:var(--wait-bg); color:var(--wait-fg); }}
  .pill {{
    display:inline-block; font-size:10.5px; padding:2px 8px; border-radius:999px;
    background:var(--surface-2); border:1px solid var(--border); color:var(--dim); margin-right:3px;
  }}
  a.tk {{ color:var(--accent); text-decoration:none; font-weight:500; }}
  a.tk:hover {{ text-decoration:underline; }}
  svg {{ display:block; }}
  @media (max-width:640px) {{
    .wrap {{ padding:0 14px; }}
    .big {{ font-size:20px; }}
    .why {{ max-width:none; }}
  }}
</style></head><body>
<header><div class="wrap head-in">
  <h1><span class="dot"></span> Trading Robot</h1>
  <span class="head-meta">paper money · updated {stamp}</span>
</div></header>
<nav><div class="wrap nav-in">{links}</div></nav>
<main class="wrap">{body}</main>
</body></html>"""


# ---- data helpers ---------------------------------------------------
def get_account():
    return cached("account", 20, lambda: trading.get_account())

def get_positions():
    return cached("positions", 20, lambda: list(trading.get_all_positions()))

def _klass(p):
    return str(getattr(p, "asset_class", "")).lower()

def stock_positions():
    return [p for p in get_positions() if _klass(p).endswith("us_equity")]

def option_positions():
    return [p for p in get_positions() if _klass(p).endswith("us_option")]

def crypto_positions():
    return [p for p in get_positions() if _klass(p).endswith("crypto")]

def get_scan():
    def make():
        held = {p.symbol for p in stock_positions()}
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
    w, h = 1000, 240
    padx, padtop, padbot = 8, 20, 22
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    lo -= span * 0.12
    hi += span * 0.12
    span = hi - lo
    n = len(vals)
    up = vals[-1] >= vals[0]
    stroke = "var(--up)" if up else "var(--down)"

    def x(i): return padx + i * (w - 2 * padx) / (n - 1)
    def y(v): return h - padbot - (v - lo) * (h - padtop - padbot) / span

    pts = [(x(i), y(v)) for i, v in enumerate(vals)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{pts[0][0]:.1f},{h-padbot} " + line + f" {pts[-1][0]:.1f},{h-padbot}"
    grid = "".join(
        f'<line x1="{padx}" y1="{padtop + k*(h-padtop-padbot)/3:.0f}" x2="{w-padx}" '
        f'y2="{padtop + k*(h-padtop-padbot)/3:.0f}" stroke="var(--border-soft)" stroke-width="1"/>'
        for k in range(4)
    )
    ex, ey = pts[-1]
    gid = f"g{abs(hash(tuple(vals))) % 99999}"
    return f"""<div class="panel" style="padding:6px 6px 2px">
    <svg viewBox="0 0 {w} {h}" style="width:100%;height:auto">
      <defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="{stroke}" stop-opacity="0.28"/>
        <stop offset="1" stop-color="{stroke}" stop-opacity="0"/>
      </linearGradient></defs>
      {grid}
      <polygon points="{area}" fill="url(#{gid})"/>
      <polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2.5"
        stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      <circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{stroke}"/>
    </svg>
    <div style="display:flex;justify-content:space-between;padding:4px 10px 8px;font-size:11px;color:var(--faint);font-family:'JetBrains Mono',monospace">
      <span>{n} runs</span><span>low {money(min(vals))} · high {money(max(vals))} · now {money(vals[-1])}</span>
    </div></div>"""


# ---- pages --------------------------------------------------------
def page_overview():
    a = get_account()
    equity, cash = float(a.equity), float(a.cash)
    day = equity - float(a.last_equity)
    stocks, opts, coins = stock_positions(), option_positions(), crypto_positions()
    total_pl = sum(float(p.unrealized_pl) for p in get_positions())

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
        for p in stocks
    ) or "<tr><td colspan='4' class='muted'>No stocks held.</td></tr>"

    return f"""
      <div class="cards">
        <div class="card"><div class="label">Account value</div><div class="big">{money(equity)}</div></div>
        <div class="card"><div class="label">Cash</div><div class="big">{money(cash)}</div></div>
        <div class="card"><div class="label">Today's change</div>
          <div class="big {cls_for(day)}">{money(day)}</div></div>
        <div class="card"><div class="label">Open profit/loss</div>
          <div class="big {cls_for(total_pl)}">{money(total_pl)}</div></div>
        <div class="card"><div class="label">Stocks</div><div class="big">{len(stocks)} / {settings.MAX_STOCKS_HELD}</div></div>
        <div class="card"><div class="label">Options</div><div class="big">{len(opts)} / {settings.MAX_OPTION_POSITIONS}</div></div>
        <div class="card"><div class="label">Coins</div><div class="big">{len(coins)} / {settings.MAX_CRYPTO_HELD}</div></div>
      </div>
      <h2>Account value over runs</h2>
      {chart}
      <h2>Scanner's current stock picks</h2>
      <p>{picks}</p>
      <h2>Stocks held now</h2>
      <table><tr><th>Stock</th><th>Shares</th><th>Value</th><th>Profit/Loss</th></tr>{holdings_rows}</table>
    """


def page_holdings():
    positions = stock_positions()
    if not positions:
        return "<p class='muted'>No stocks held right now. (See the Options and Crypto pages too.)</p>"
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


def page_crypto():
    coins = crypto_positions()
    if coins:
        rows = ""
        for p in coins:
            pl = float(p.unrealized_pl)
            rows += (f"<tr><td>{p.symbol}</td><td>{float(p.qty):g}</td>"
                     f"<td>{money(p.avg_entry_price)}</td><td>{money(p.current_price)}</td>"
                     f"<td>{money(p.market_value)}</td>"
                     f"<td class='{cls_for(pl)}'>{money(pl)} ({pct(float(p.unrealized_plpc)*100)})</td></tr>")
        held_html = (f"<table><tr><th>Coin</th><th>Amount</th><th>Bought at</th><th>Price now</th>"
                     f"<th>Value</th><th>Profit/Loss</th></tr>{rows}</table>")
    else:
        held_html = "<p class='muted'>No coins held right now.</p>"

    db = diary.get_db()
    recent = db.execute("""
        SELECT d.ts_utc, d.symbol, d.action, d.reason FROM decisions d JOIN runs r ON d.run_id=r.run_id
        WHERE r.strategy='crypto_sma_v1' ORDER BY d.decision_id DESC LIMIT 30
    """).fetchall()
    dec_html = "".join(
        f"<tr><td>{r['ts_utc'][:16]}</td><td>{r['symbol']}</td>"
        f"<td><span class='badge {r['action'].lower()}'>{r['action']}</span></td>"
        f"<td class='why'>{html.escape(r['reason'])}</td></tr>" for r in recent
    ) or "<tr><td colspan='4' class='muted'>Nothing yet.</td></tr>"

    return f"""<p class="muted">Crypto trades 24/7 — this part never stops. Limits: max {settings.MAX_CRYPTO_HELD} coins,
      ${settings.MAX_DOLLARS_PER_CRYPTO} each, {settings.MAX_CRYPTO_TRADES_PER_DAY} trades/day.
      Signal: 3-day vs 10-day average.</p>
      <h2>Coins held</h2>
      {held_html}
      <h2>Recent crypto decisions</h2>
      <table><tr><th>When (UTC)</th><th>Coin</th><th>Call</th><th>Reason</th></tr>{dec_html}</table>"""


def page_options():
    from options_engine import readable, days_to_expiry
    positions = [p for p in get_positions()
                 if str(getattr(p, "asset_class", "")).lower().endswith("us_option")]

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


STRAT_NAMES = {
    "sma_scan_v1": "Stock robot (scan + trade)",
    "sma_crossover_5_20_v1": "Stock robot (old 3-stock version)",
    "claude_advisor_v1": "AI advisor (opinions only)",
    "options_long_v1": "Options robot",
    "crypto_sma_v1": "Crypto robot",
}


def page_scoreboard():
    db = diary.get_db()

    # --- Part 1: how is the account ACTUALLY doing (real numbers, available now) ---
    first = db.execute("SELECT equity_before FROM runs WHERE equity_before IS NOT NULL ORDER BY run_id LIMIT 1").fetchone()
    try:
        acct = get_account()
        now_equity = float(acct.equity)
    except Exception:
        now_equity = None
    start_equity = float(first["equity_before"]) if first else None

    perf = ""
    if start_equity and now_equity is not None:
        change = now_equity - start_equity
        change_pct = change / start_equity * 100
        perf = f"""<h2>How the account is actually doing</h2>
        <div class="cards">
          <div class="card"><div class="label">Started at</div><div class="big">{money(start_equity)}</div></div>
          <div class="card"><div class="label">Now</div><div class="big">{money(now_equity)}</div></div>
          <div class="card"><div class="label">Change</div>
            <div class="big {cls_for(change)}">{money(change)} ({pct(change_pct)})</div></div>
        </div>
        <p class="muted">This is everything together — stocks, options, crypto, cash. Real paper-account numbers.</p>"""

    # --- Part 2: decision grading (needs a few days to fill in) ---
    counts = db.execute("""
        SELECT r.strategy AS strategy, COUNT(*) AS n, MIN(d.ts_utc) AS first_ts
        FROM decisions d JOIN runs r ON d.run_id = r.run_id
        WHERE r.strategy NOT IN ('options_long_v1', 'crypto_sma_v1')
        GROUP BY r.strategy
    """).fetchall()

    scores = get_scores(3)
    out = [perf, "<h2>Decision grading</h2>",
           "<p class='muted'>Each stock/AI decision gets graded against what the price actually did "
           "3 trading days later. \"Benchmark\" = just staying fully invested. "
           "Options and crypto have their own P/L on their pages.</p>"]

    if not scores:
        out.append("<p class='muted'>No stock or AI decisions logged yet.</p>")
        return "".join(out)

    any_graded = any(s["judged"] for s in scores.values())
    if not any_graded:
        # tell them when to expect the first grades
        import datetime as _dt
        earliest = min((c["first_ts"] for c in counts), default=None)
        eta = ""
        if earliest:
            d0 = _dt.date.fromisoformat(earliest[:10])
            biz = 0
            day = d0
            while biz < 3:
                day += _dt.timedelta(days=1)
                if day.weekday() < 5:
                    biz += 1
            eta = f" First scores expected around <b>{day.isoformat()}</b>."
        total = sum(c["n"] for c in counts)
        out.append(f"<p class='muted'>✅ Working — collecting data. "
                   f"{total} decisions logged so far, none old enough to grade yet.{eta}</p>")

    for strat, s in scores.items():
        out.append(f"<h2 style='text-transform:none;color:#e6e6e6'>{html.escape(STRAT_NAMES.get(strat, strat))}</h2>")
        if not s["judged"]:
            out.append(f"""<div class="cards">
              <div class="card"><div class="label">Decisions collected</div><div class="big">{s['decisions']}</div></div>
              <div class="card"><div class="label">Graded so far</div><div class="big">0</div>
                <div class="muted">{s['pending']} waiting</div></div>
            </div>""")
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
    return "".join(x for x in out if x)


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
    "/crypto": lambda qs: page_crypto(),
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
