"""
The website. A little multi-page site on your own computer for watching
the robot.

Pages:
    /            Intro        - animated landing page (web/intro.html + web/intro.js)
    /overview    Overview     - account value, chart, today's picks
    /holdings    Holdings     - what we own right now
    /decisions   Decisions    - every BUY/SELL/WAIT with the reasoning
    /trades      Trades       - every trade attempt
    /scoreboard  Scoreboard   - robot vs AI, graded against reality
    /universe    Universe     - the whole big list and the scan signal
    /api/intro, /api/extras, /api/universe   JSON feeds for the intro page

Run it like this:
    ./venv/bin/python dashboard.py           (port 8777)
    ./venv/bin/python dashboard.py 9001       (pick your own port)
Then open the address it prints. Ctrl+C to stop.
"""

import os
import sys
import html
import json
import math
import re
import threading
import time
import traceback
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

import profiles

# ---- which account is this dashboard showing? ------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_NAME = os.environ.get("ROBOT_PROFILE", "main")
PROFILE = profiles.get(PROFILE_NAME)
# load that profile's keys and point the diary at its database BEFORE
# importing settings / diary (they read these on import)
load_dotenv(os.path.join(HERE, PROFILE["env_file"]), override=True)
os.environ.setdefault("ROBOT_DIARY_PATH", os.path.join(HERE, PROFILE["diary"]))

import settings
import diary
from scanner import analyze_all, rank_buys
from crypto_scanner import FAST_DAYS as C_FAST, SLOW_DAYS as C_SLOW
from grader import grade_all, grade_trades
from sectors import sector_of

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else PROFILE["port"]

ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)
data = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
crypto_data = CryptoHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
WEB = os.path.join(HERE, "web")


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
NAV = [("/overview", "Overview"), ("/holdings", "Holdings"), ("/crypto", "Crypto"),
       ("/decisions", "Decisions"), ("/trades", "Trades"), ("/scoreboard", "Scoreboard"),
       ("/universe", "Universe"), ("/news", "News"), ("/research", "Research")]

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='6' fill='%23080808'/%3E"
           "%3Cpath d='M6 21l6-7 5 4 9-11' fill='none' stroke='%23f3d484' stroke-width='2.5' "
           "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")


def page_header(title, subtitle=""):
    sub = f'<p class="ph-sub">{subtitle}</p>' if subtitle else ""
    # @@KICKER@@ is filled in by shell() with the page's number + name
    return f'<div class="page-head"><div class="ph-kicker">@@KICKER@@</div><h1 class="ph-title">{title}</h1>{sub}</div>'


def section(title, note=""):
    n = f'<span class="sec-note">{note}</span>' if note else ""
    return f'<div class="sec"><h2>{title}</h2>{n}</div>'


def stat(label, value, sub="", cls=""):
    s = f'<div class="s-sub">{sub}</div>' if sub else ""
    return f'<div class="stat"><div class="s-label">{label}</div><div class="s-val {cls}">{value}</div>{s}</div>'


def _next_run_hint():
    try:
        row = diary.get_db().execute("SELECT MAX(ts_utc) AS ts FROM runs").fetchone()
        if not row or not row["ts"]:
            return "runs every ~30 min"
        gap = 30 * 60 - (datetime.now(timezone.utc) - datetime.fromisoformat(row["ts"])).total_seconds()
        if gap <= 60:
            return "next run: any moment"
        m = int(gap // 60)
        return f"next run: ~{m} min" if m < 60 else f"next run: ~{m // 60}h {m % 60}m"
    except Exception:
        return "runs every ~30 min"


def shell(path, title, body, subtitle_meta=""):
    links = "".join(
        f'<a href="{href}" class="{"on" if href == path else ""}"><span class="n">{k:02d}</span>{label}</a>'
        for k, (href, label) in enumerate(NAV, 1)
    )
    now = datetime.now(timezone.utc)
    stamp = f"{now:%H:%M} UTC"
    meta = subtitle_meta or f"{PROFILE['label']} · paper · {_next_run_hint()}"
    # link to the other account's dashboard
    others = [p for n, p in profiles.PROFILES.items() if n != PROFILE_NAME]
    switch = "".join(f'<a href="http://localhost:{p["port"]}/" class="acct-switch">{p["label"]} ↗</a>'
                     for p in others)
    # wrap plain tables in a panel for the polished look
    body = body.replace("<table>", '<div class="panel"><table>').replace("</table>", "</table></div>")
    # page kicker ("PAGE 03 // CRYPTO") + numbered section labels ("01 / HOLDINGS")
    idx, name = next(((k, lbl) for k, (h, lbl) in enumerate(NAV, 1) if h == path), (0, title))
    body = body.replace("@@KICKER@@", f'<span class="gold">PAGE {idx:02d}</span> // {html.escape(name).upper()}')
    n = iter(range(1, 100))
    body = re.sub(r'<div class="sec"><h2>', lambda m: f'<div class="sec"><h2><span class="sec-n">{next(n):02d} /</span> ', body)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Trading Robot</title>
<link rel="icon" href="{FAVICON}">
<meta http-equiv="refresh" content="60">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  /* look modelled on austensor.com: near-black, Geist + Geist Mono, gold/sky accents,
     hairline borders, bracket-cornered cards, tracked mono labels */
  :root {{
    --bg:#080808; --surface:#0c0c0d; --surface-2:#111113; --raised:#141416;
    --border:rgba(255,255,255,.12); --border-soft:rgba(255,255,255,.07);
    --text:#f0f0f0; --dim:#a1a1aa; --faint:#71717a;
    --accent:#f3d484; --accent-soft:rgba(243,212,132,.10); --sky:#38bdf8;
    --up:#34d399; --down:#f87171; --flat:#a1a1aa;
    --buy-bg:rgba(52,211,153,.08); --buy-fg:#6ee7b7;
    --sell-bg:rgba(248,113,113,.08); --sell-fg:#fca5a5;
    --wait-bg:rgba(255,255,255,.04); --wait-fg:#a1a1aa;
    --mono:'Geist Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --r:.382rem;
  }}
  * {{ box-sizing:border-box; }}
  html {{ -webkit-text-size-adjust:100%; scroll-behavior:smooth; }}
  body {{
    font-family:'Geist',-apple-system,system-ui,'Segoe UI',sans-serif;
    background:var(--bg); color:var(--text); margin:0; padding:0 0 90px;
    font-size:14.5px; line-height:1.55; -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1160px; margin:0 auto; padding:0 28px; }}
  a {{ color:inherit; }}
  .gold {{ color:var(--accent); }}

  header {{
    position:sticky; top:0; z-index:20; backdrop-filter:blur(14px);
    background:rgba(8,8,8,.82); border-bottom:1px solid var(--border);
  }}
  .head-in {{ display:flex; align-items:center; justify-content:space-between; gap:18px; padding:14px 0; }}
  .brand {{
    margin:0; font-size:19px; font-weight:300; letter-spacing:.2em; text-transform:uppercase;
    display:flex; align-items:center; gap:12px; white-space:nowrap;
  }}
  .brand .dot {{ width:6px; height:6px; border-radius:50%; background:var(--accent); box-shadow:0 0 10px var(--accent); flex:none; }}
  .head-meta {{ font-size:10.5px; color:var(--faint); font-family:var(--mono); text-align:right; letter-spacing:.06em; text-transform:uppercase; }}
  .head-meta b {{ color:var(--dim); font-weight:500; }}

  nav {{ border-top:1px solid var(--border-soft); padding:10px 0; }}
  .nav-in {{ display:flex; justify-content:center; }}
  .nav-pill {{
    display:inline-flex; gap:2px; flex-wrap:wrap; justify-content:center;
    border:1px solid var(--border); border-radius:999px; padding:4px;
  }}
  nav a {{
    display:inline-flex; align-items:baseline; gap:7px; padding:6px 13px; border-radius:999px;
    color:var(--dim); text-decoration:none; font:400 11px/1.2 var(--mono);
    letter-spacing:.08em; text-transform:uppercase; transition:color .15s, background .15s;
  }}
  nav a .n {{ color:var(--faint); font-size:10px; }}
  nav a:hover {{ color:var(--text); }}
  nav a.on {{ background:var(--text); color:#080808; }}
  nav a.on .n {{ color:#52525b; }}

  main.wrap {{ padding-top:44px; }}
  p {{ color:var(--dim); margin:10px 0; }}
  b {{ font-weight:600; color:var(--text); }}

  .page-head {{ margin-bottom:30px; }}
  .ph-kicker {{ font:500 11px/1 var(--mono); letter-spacing:.16em; color:var(--faint); margin-bottom:14px; }}
  .ph-title {{ margin:0; font-size:44px; font-weight:500; letter-spacing:-0.035em; line-height:1.05; }}
  .ph-sub {{ margin:12px 0 0; color:var(--dim); font-size:15px; max-width:68ch; }}

  .sec {{ display:flex; align-items:baseline; gap:12px; margin:44px 0 16px; flex-wrap:wrap; }}
  h2 {{ font:400 11px/1 var(--mono); color:var(--dim); text-transform:uppercase; letter-spacing:.16em; margin:0; }}
  h2 .sec-n {{ color:var(--sky); }}
  .sec-note {{ font:400 11px var(--mono); color:var(--faint); letter-spacing:.04em; }}
  .sec-note a {{ color:var(--accent); text-decoration:none; }}

  .cards {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(190px, 1fr)); gap:14px; }}
  .cards.wide {{ grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); }}
  .stat, .card {{
    position:relative; background:linear-gradient(180deg, #0f0f10, var(--surface));
    border:1px solid var(--border-soft); border-radius:var(--r); padding:16px 18px;
  }}
  /* bracket corners, like the reference site's experiment cards */
  .stat::before, .card::before, .stat::after, .card::after {{
    content:""; position:absolute; width:9px; height:9px; pointer-events:none;
    border-color:rgba(255,255,255,.35); border-style:solid;
  }}
  .stat::before, .card::before {{ top:-1px; left:-1px; border-width:1px 0 0 1px; }}
  .stat::after, .card::after {{ bottom:-1px; right:-1px; border-width:0 1px 1px 0; }}
  .s-label, .label {{ color:var(--faint); font:400 10.5px/1.3 var(--mono); text-transform:uppercase; letter-spacing:.14em; }}
  .s-val, .big {{ font-size:24px; font-weight:500; margin-top:10px; letter-spacing:-0.02em; font-family:var(--mono); }}
  .s-val.sm {{ font-size:14px; line-height:1.35; }}
  .s-sub, .card .muted {{ margin-top:5px; font-size:12px; color:var(--faint); }}
  .hero .s-val {{ font-size:32px; }}
  .hero .s-label {{ color:var(--accent); }}

  .panel {{
    border:1px solid var(--border-soft); border-radius:var(--r); background:var(--surface);
    overflow-x:auto; -webkit-overflow-scrolling:touch;
  }}
  .panel + .panel {{ margin-top:14px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th {{
    background:var(--surface-2); color:var(--faint); font:400 10px/1.2 var(--mono);
    text-transform:uppercase; letter-spacing:.14em; padding:11px 16px; text-align:left;
    border-bottom:1px solid var(--border-soft); white-space:nowrap; position:sticky; top:0;
  }}
  th.num, td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-family:var(--mono); }}
  td {{ padding:10px 16px; border-bottom:1px solid var(--border-soft); vertical-align:top; font-variant-numeric:tabular-nums; }}
  td.sym {{ font-weight:500; font-family:var(--mono); letter-spacing:.02em; }}
  tr:last-child td {{ border-bottom:none; }}
  tbody tr:hover td, table tr:hover td {{ background:rgba(255,255,255,.025); }}
  tr.total td {{ border-top:1px solid var(--border); font-weight:600; background:var(--surface-2); }}

  .up {{ color:var(--up); }} .down {{ color:var(--down); }} .flat {{ color:var(--flat); }}
  .why {{ color:var(--dim); max-width:560px; font-size:12.5px; }}
  .muted {{ color:var(--faint); font-size:12.5px; }}
  .empty {{
    border:1px dashed var(--border); border-radius:var(--r); padding:26px; text-align:center;
    color:var(--faint); font:400 12px var(--mono); letter-spacing:.04em; background:var(--surface);
  }}
  .warn {{
    color:var(--accent); white-space:pre-wrap; background:var(--accent-soft);
    border:1px solid rgba(243,212,132,.22); border-radius:var(--r); padding:12px 14px; font-size:12.5px;
  }}
  .badge {{
    display:inline-block; padding:3px 8px; border-radius:4px; font:500 10px/1.3 var(--mono);
    letter-spacing:.1em; text-transform:uppercase; border:1px solid transparent;
  }}
  .badge.buy {{ background:var(--buy-bg); color:var(--buy-fg); border-color:rgba(52,211,153,.25); }}
  .badge.sell {{ background:var(--sell-bg); color:var(--sell-fg); border-color:rgba(248,113,113,.25); }}
  .badge.wait {{ background:var(--wait-bg); color:var(--wait-fg); border-color:var(--border-soft); }}
  .trend-up {{ color:var(--up); font-weight:500; }}
  .trend-down {{ color:var(--down); font-weight:500; }}
  .pill {{
    display:inline-block; font:400 10px/1.4 var(--mono); padding:2px 8px; border-radius:4px;
    letter-spacing:.08em; text-transform:uppercase;
    background:transparent; border:1px solid var(--border); color:var(--dim); margin-right:4px;
  }}
  .pill.hot {{ background:var(--accent-soft); border-color:rgba(243,212,132,.3); color:var(--accent); }}
  a.tk {{ color:var(--accent); text-decoration:none; font-weight:500; }}
  a.tk:hover {{ text-decoration:underline; }}
  svg {{ display:block; }}
  footer {{
    position:fixed; left:0; right:0; bottom:0; z-index:18; text-align:center;
    background:rgba(8,8,8,.9); backdrop-filter:blur(14px); border-top:1px solid var(--border);
    padding:13px 16px; color:var(--dim); font:400 11.5px/1.4 var(--mono); letter-spacing:.06em;
  }}
  footer b {{ color:var(--text); font-weight:500; }}

  .panel h3 {{ font-size:14px; font-weight:500; color:var(--text); margin:20px 0 8px; letter-spacing:-0.01em; }}
  .panel h3:first-child {{ margin-top:0; }}
  .panel ul, .panel ol {{ margin:8px 0; padding-left:20px; color:var(--dim); }}
  .panel li {{ margin:3px 0; }}
  .panel hr {{ border:0; border-top:1px solid var(--border-soft); margin:16px 0; }}
  .panel code {{ background:var(--surface-2); padding:1px 5px; border-radius:4px; font:12px var(--mono); }}

  .acct-tag {{ font:500 10px/1 var(--mono); letter-spacing:.12em; text-transform:uppercase;
    color:var(--accent); border:1px solid rgba(243,212,132,.35); padding:5px 8px; border-radius:4px; }}
  .acct-switch {{
    display:inline-block; color:var(--dim); text-decoration:none; border:1px solid var(--border);
    border-radius:var(--r); padding:5px 10px; margin-bottom:5px; transition:color .15s, border-color .15s;
  }}
  .acct-switch:hover {{ color:var(--accent); border-color:rgba(243,212,132,.4); }}
  .chart {{ cursor:crosshair; }}
  .chart svg .cx-line {{ transition:opacity .1s; }}
  .cx-tip {{
    position:absolute; top:10px; transform:translateX(-50%);
    background:var(--raised); border:1px solid var(--border); border-radius:var(--r);
    padding:5px 9px; font:500 11px/1.3 var(--mono); color:var(--text);
    white-space:nowrap; pointer-events:none; transition:opacity .1s; z-index:3;
    box-shadow:0 4px 14px rgba(0,0,0,.5);
  }}

  a.brand {{ color:inherit; text-decoration:none; }}
  .stat:hover, .card:hover {{ border-color:rgba(255,255,255,.14);
    background:radial-gradient(260px circle at var(--mx,-200px) var(--my,-200px), rgba(243,212,132,.07), transparent 60%),
               linear-gradient(180deg, #0f0f10, var(--surface)); }}
  .stat, .card, .panel {{ transition:border-color .4s; }}

  /* cross-page transitions + first-visit entrance (web/fx.js) */
  @view-transition {{ navigation:auto; }}
  header {{ view-transition-name:site-header; }}
  ::view-transition-old(root) {{ animation:vt-out .45s cubic-bezier(.16,1,.3,1) both; }}
  ::view-transition-new(root) {{ animation:vt-in .6s cubic-bezier(.16,1,.3,1) both; }}
  @keyframes vt-out {{ to {{ opacity:0; filter:blur(8px); transform:scale(.99); }} }}
  @keyframes vt-in {{ from {{ opacity:0; filter:blur(10px); transform:scale(1.008); }} }}
  html.fx .fx-in {{ opacity:0; transform:translateY(14px); filter:blur(6px);
    transition:opacity .9s cubic-bezier(.16,1,.3,1) var(--d,0s), transform .9s cubic-bezier(.16,1,.3,1) var(--d,0s),
               filter .9s cubic-bezier(.16,1,.3,1) var(--d,0s); }}
  html.fx .fx-in.in {{ opacity:1; transform:none; filter:none; }}
  @media (prefers-reduced-motion:reduce) {{
    ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) {{ animation:none !important; }}
    html.fx .fx-in {{ opacity:1 !important; transform:none !important; filter:none !important; }}
  }}

  @media (max-width:760px) {{
    .wrap {{ padding:0 16px; }}
    .head-in {{ flex-direction:column; align-items:flex-start; gap:8px; }}
    .head-meta {{ text-align:left; }}
    header {{ position:static; }}
    .nav-pill {{ border-radius:var(--r); }}
    .ph-title {{ font-size:32px; }}
    .s-val, .big {{ font-size:20px; }}
    .hero .s-val {{ font-size:26px; }}
    .why {{ max-width:none; }}
    footer {{ font-size:10px; }}
  }}
</style></head><body>
<header><div class="wrap head-in">
  <a class="brand" href="/" title="Back to the intro"><span class="dot"></span>Trading Robot <span class="acct-tag">{PROFILE['label']}</span></a>
  <span class="head-meta">{switch}<br>{meta} · <b>updated {stamp}</b></span>
</div>
<nav><div class="wrap nav-in"><div class="nav-pill">{links}</div></div></nav></header>
<main class="wrap">{body}
</main>
<footer>© {now:%Y} <b>Trading Robot</b> · paper money only · not financial advice · auto-refreshes every 60s</footer>
<script src="/static/fx.js" defer></script>
</body></html>"""


# ---- data helpers ---------------------------------------------------
def get_account():
    return cached("account", 20, lambda: trading.get_account())

def get_positions():
    return cached("positions", 20, lambda: list(trading.get_all_positions()))

def _klass(p):
    return str(getattr(p, "asset_class", "")).lower()

def stock_positions():
    # SPY is the cash sleeve (settings.USE_SPY_CASH_SLEEVE), never a stock pick
    return [p for p in get_positions() if _klass(p).endswith("us_equity") and p.symbol != "SPY"]

def sleeve_positions():
    return [p for p in get_positions() if _klass(p).endswith("us_equity") and p.symbol == "SPY"]

def crypto_positions():
    return [p for p in get_positions() if _klass(p).endswith("crypto")]

_scan_lock = threading.Lock()


def _scan_now():
    held = {p.symbol for p in stock_positions()}
    a = analyze_all(data, list(settings.ALLOWED_STOCKS) + list(held))
    short = rank_buys(a, exclude=held | {"SPY"})
    _cache["scan"] = (time.time(), (a, short, held))
    return a, short, held


def refresh_scan_in_background():
    if not _scan_lock.acquire(blocking=False):
        return                                   # a scan is already running
    def run():
        try:
            _scan_now()
        except Exception:
            pass
        finally:
            _scan_lock.release()
    threading.Thread(target=run, daemon=True).start()


def get_scan():
    """The ~2000-stock scan takes ~20-30s, so no page ever waits for it: serve the
    last one instantly and, once it's 5 min old, refresh it in a background thread.
    Only a request that arrives before the very first scan finishes has to wait
    (the server starts that first scan on launch)."""
    hit = _cache.get("scan")
    if hit:
        if time.time() - hit[0] > 300:
            refresh_scan_in_background()
        return hit[1]
    with _scan_lock:                             # first scan: wait for whoever is running it
        hit = _cache.get("scan")
        return hit[1] if hit else _scan_now()

def get_scores(lookahead=10):
    return cached(f"scores{lookahead}", 300, lambda: grade_all(data, diary.get_db(), lookahead))

def get_trade_scores():
    """The honest money view — real completed buy->sell round trips."""
    return cached("trade_scores", 120, lambda: grade_trades(data, diary.get_db()))


# ---- SVG line chart -------------------------------------------------
def _dedupe_by_time(points, minutes=20):
    """points = list of (iso_ts, value). Keep the last value per time bucket
    (so many runs/hour from 3 strategies don't make a jagged mess), and drop
    obvious bad readings. Returns list of (bucket_datetime, value)."""
    buckets = {}
    for ts, v in points:
        if v is None:
            continue
        try:
            t = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            continue
        buckets[int(t.timestamp() // (minutes * 60))] = (t, v)   # last write wins
    rows = [buckets[k] for k in sorted(buckets)]
    # drop isolated spikes: a point that jumps >0.6% from BOTH neighbours is a
    # bad reading (equity snapshotted mid-trade), not a real move.
    if len(rows) >= 4:
        clean = [rows[0]]
        for i in range(1, len(rows) - 1):
            a, b, c = rows[i - 1][1], rows[i][1], rows[i + 1][1]
            if abs(b / a - 1) > 0.006 and abs(b / c - 1) > 0.006 and abs(a / c - 1) < 0.006:
                continue
            clean.append(rows[i])
        clean.append(rows[-1])
        rows = clean
    return rows


def equity_chart(points, baseline=None):
    """points = list of (iso_ts, value). baseline draws a dashed reference line.
    Hover anywhere on the chart for a crosshair + tooltip with the value & time."""
    rows = _dedupe_by_time(points)
    if len(rows) < 2:
        return "<p class='muted'>Need a couple of runs to draw a chart.</p>"
    times = [t for t, _ in rows]
    vals = [v for _, v in rows]
    w, h = 1000, 230
    padx, padtop, padbot = 8, 18, 20
    lo, hi = min(vals), max(vals)
    if baseline is not None:
        lo, hi = min(lo, baseline), max(hi, baseline)
    mid = (lo + hi) / 2
    min_span = mid * 0.014
    if (hi - lo) < min_span:
        lo, hi = mid - min_span / 2, mid + min_span / 2
    span = (hi - lo) or 1
    lo -= span * 0.16
    hi += span * 0.16
    span = hi - lo
    n = len(vals)
    up = vals[-1] >= (baseline if baseline is not None else vals[0])
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
    base_svg = ""
    if baseline is not None:
        by = y(baseline)
        base_svg = (f'<line x1="{padx}" y1="{by:.1f}" x2="{w-padx}" y2="{by:.1f}" '
                    f'stroke="var(--faint)" stroke-width="1" stroke-dasharray="4 4"/>'
                    f'<text x="{w-padx}" y="{by-5:.1f}" text-anchor="end" font-size="11" '
                    f'fill="var(--faint)" font-family="monospace">start {money(baseline)}</text>')
    ex, ey = pts[-1]
    gid = f"g{abs(hash(tuple(vals))) % 99999}"
    cid = f"c{abs(hash((tuple(vals), n))) % 999999}"

    # data for the hover interaction: SVG-x, SVG-y, dollar value, time label
    pdata = json.dumps([
        {"x": round(px, 1), "y": round(py, 1),
         "v": money(v), "t": times[i].strftime("%b %-d, %H:%M UTC")}
        for i, ((px, py), v) in enumerate(zip(pts, vals))
    ])

    return f"""<div class="panel chart" id="{cid}" style="position:relative;padding:6px 6px 2px">
    <svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block">
      <defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="{stroke}" stop-opacity="0.28"/>
        <stop offset="1" stop-color="{stroke}" stop-opacity="0"/>
      </linearGradient></defs>
      {grid}
      <polygon points="{area}" fill="url(#{gid})"/>
      <polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2.5"
        stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      {base_svg}
      <line class="cx-line" x1="0" y1="{padtop}" x2="0" y2="{h-padbot}"
        stroke="var(--dim)" stroke-width="1" style="opacity:0"/>
      <circle class="cx-dot" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{stroke}"/>
    </svg>
    <div class="cx-tip" style="opacity:0"></div>
    <div style="display:flex;justify-content:space-between;padding:2px 12px 9px;font-size:10.5px;color:var(--faint);font-family:var(--mono)">
      <span>{n} points</span><span>low {money(min(vals))} &nbsp;·&nbsp; high {money(max(vals))} &nbsp;·&nbsp; now {money(vals[-1])}</span>
    </div>
    <script>(function(){{
      var box=document.getElementById("{cid}"); if(!box) return;
      var svg=box.querySelector("svg"), W={w};
      var pts={pdata};
      var vline=box.querySelector(".cx-line"), dot=box.querySelector(".cx-dot"), tip=box.querySelector(".cx-tip");
      var lastX=pts[pts.length-1].x, lastY=pts[pts.length-1].y;
      function move(e){{
        var r=svg.getBoundingClientRect();
        var cx=(e.touches?e.touches[0].clientX:e.clientX)-r.left;
        var sx=cx/r.width*W;
        var best=0,bd=1e9;
        for(var i=0;i<pts.length;i++){{var d=Math.abs(pts[i].x-sx); if(d<bd){{bd=d;best=i;}}}}
        var p=pts[best];
        vline.setAttribute("x1",p.x); vline.setAttribute("x2",p.x); vline.style.opacity=1;
        dot.setAttribute("cx",p.x); dot.setAttribute("cy",p.y);
        tip.textContent=p.v+"  ·  "+p.t; tip.style.opacity=1;
        var frac=p.x/W;
        tip.style.left=Math.min(Math.max(frac*r.width,54),r.width-54)+"px";
      }}
      function leave(){{
        vline.style.opacity=0; tip.style.opacity=0;
        dot.setAttribute("cx",lastX); dot.setAttribute("cy",lastY);
      }}
      box.addEventListener("mousemove",move);
      box.addEventListener("touchmove",move,{{passive:true}});
      box.addEventListener("mouseleave",leave);
      box.addEventListener("touchend",leave);
    }})();</script>
    </div>"""


# ---- pages --------------------------------------------------------
STRAT_NAMES = {
    "sma_scan_v1": "Stock robot",
    "sma_crossover_5_20_v1": "Stock robot (old 3-stock version)",
    "claude_advisor_v1": "AI advisor",
    "options_long_v1": "Options robot",
    "crypto_sma_v1": "Crypto robot",
    "spy_sleeve_v1": "SPY cash sleeve",
    "ml_brain_v1": "ML brain (opinions only)",
}


def _pl_cell(pl, plpc):
    return f"<td class='num {cls_for(pl)}'>{money(pl)} <span class='muted'>({pct(plpc)})</span></td>"


def _pos_table(positions, kind="stock"):
    """kind: 'stock' | 'crypto' | 'option'"""
    if not positions:
        return f"<div class='empty'>Nothing held right now.</div>"
    label = "Coin" if kind == "crypto" else "Stock"
    qty = (lambda p: f"{float(p.qty):g}")
    head = (f"<th>{label}</th><th class='num'>Qty</th><th class='num'>Bought&nbsp;at</th>"
            "<th class='num'>Price&nbsp;now</th><th class='num'>Value</th><th class='num'>Profit / Loss</th>")
    rows = "".join(
        f"<tr><td class='sym'>{p.symbol}</td><td class='num'>{qty(p)}</td>"
        f"<td class='num'>{money(p.avg_entry_price)}</td>"
        f"<td class='num'>{money(p.current_price)}</td>"
        f"<td class='num'>{money(p.market_value)}</td>"
        + _pl_cell(float(p.unrealized_pl), float(p.unrealized_plpc)*100) + "</tr>"
        for p in positions)
    return f"<table><tr>{head}</tr>{rows}</table>"


def _decisions_table(rows, sym_label="Symbol"):
    if not rows:
        return "<div class='empty'>Nothing logged yet.</div>"
    body = "".join(
        f"<tr><td class='num muted'>{r['ts_utc'][:16].replace('T',' ')}</td>"
        f"<td class='sym'>{r['symbol']}</td>"
        f"<td><span class='badge {r['action'].lower()}'>{r['action']}</span></td>"
        f"<td class='why'>{html.escape(r['reason'])}</td></tr>" for r in rows)
    return (f"<table><tr><th>When (UTC)</th><th>{sym_label}</th><th>Call</th><th>Reason</th></tr>"
            f"{body}</table>")


def page_overview():
    a = get_account()
    equity, cash = float(a.equity), float(a.cash)
    day = equity - float(a.last_equity)
    stocks, coins = stock_positions(), crypto_positions()
    total_pl = sum(float(p.unrealized_pl) for p in get_positions())
    invested = equity - cash

    db = diary.get_db()
    runs = db.execute("SELECT ts_utc, equity_after FROM runs WHERE equity_after IS NOT NULL ORDER BY run_id").fetchall()
    first = db.execute("SELECT equity_before FROM runs WHERE equity_before IS NOT NULL ORDER BY run_id LIMIT 1").fetchone()
    baseline = float(first["equity_before"]) if first else None
    chart = equity_chart([(r["ts_utc"], r["equity_after"]) for r in runs], baseline=baseline)

    # ---- what happened today (real actions only — filled trades) ----
    today = f"{datetime.now(timezone.utc):%Y-%m-%d}"
    todays = db.execute("""
        SELECT t.ts_utc, r.strategy AS strategy, t.symbol, t.side, t.shares, t.fill_price
        FROM trades t JOIN runs r ON t.run_id = r.run_id
        WHERE substr(t.ts_utc,1,10) = ? AND t.status = 'filled'
        ORDER BY t.trade_id DESC
    """, (today,)).fetchall()
    ai_today = db.execute("""
        SELECT COUNT(*) AS n FROM decisions d JOIN runs r ON d.run_id = r.run_id
        WHERE substr(d.ts_utc,1,10) = ? AND r.strategy = 'claude_advisor_v1'
    """, (today,)).fetchone()

    def _t_line(r):
        verb = {"buy": "bought", "sell": "sold"}.get(r["side"], r["side"])
        vcls = "up" if r["side"] == "buy" else "down"
        mult = 100 if r["strategy"] == "options_long_v1" else 1   # legacy option rows
        amt = ""
        if r["fill_price"]:
            amt = f"{money(r['fill_price'])}"
            if r["shares"]:
                amt += f" <span class='muted'>({money(float(r['fill_price']) * float(r['shares']) * mult)})</span>"
        tag = STRAT_NAMES.get(r["strategy"], r["strategy"])
        return (f"<tr><td class='num muted'>{r['ts_utc'][11:16]}</td><td class='muted'>{tag}</td>"
                f"<td><span class='{vcls}'>{verb}</span> <b>{r['symbol']}</b></td><td class='num'>{amt}</td></tr>")

    if todays:
        today_html = ("<table><tr><th>Time</th><th>Robot</th><th>Action</th><th class='num'>Price</th></tr>"
                      + "".join(_t_line(r) for r in todays) + "</table>")
    else:
        today_html = ("<div class='empty'>No trades today — holding steady "
                      "(waiting for a signal, or the market's closed).</div>")
    if ai_today and ai_today["n"]:
        today_html += (f"<p class='muted'>The AI advisor logged {ai_today['n']} "
                       f"opinion(s) today — see the <a class='tk' href='/scoreboard'>Scoreboard</a>.</p>")

    try:
        _, short, held = get_scan()
        picks = " ".join(f'<a class="pill hot" href="/universe">{s}</a>' for s in short[:10]) or \
            "<span class='muted'>nothing trending up right now</span>"
    except Exception:
        picks = "<span class='muted'>scan unavailable</span>"

    since = ""
    if baseline:
        d = equity - baseline
        since = stat("Since start", f"{money(d)}", pct(d / baseline * 100), cls_for(d))

    return f"""
      {page_header("Overview", "Live paper-account snapshot, updated every run.")}
      <div class="cards wide">
        <div class="stat hero"><div class="s-label">Account value</div>
          <div class="s-val">{money(equity)}</div>
          <div class="s-sub">{money(cash)} cash · {money(invested)} invested</div></div>
        <div class="stat"><div class="s-label">Today</div>
          <div class="s-val {cls_for(day)}">{money(day)}</div>
          <div class="s-sub">since yesterday's close</div></div>
        {since}
        <div class="stat"><div class="s-label">Open profit / loss</div>
          <div class="s-val {cls_for(total_pl)}">{money(total_pl)}</div>
          <div class="s-sub">across all open positions</div></div>
      </div>
      <div class="cards" style="margin-top:11px">
        {stat("Stocks held", f"{len(stocks)} <span class='muted'>/ {settings.MAX_STOCKS_HELD}</span>")}
        {stat("SPY cash sleeve", money(sum(float(p.market_value) for p in sleeve_positions())), "idle cash parked in the index")}
        {stat("Coins held", f"{len(coins)} <span class='muted'>/ {settings.MAX_CRYPTO_HELD}</span>")}
      </div>

      {section("Account value over time", "hover for value &amp; time · dashed line = start")}
      {chart}

      {section("What the robot did today")}
      {today_html}

      {section("Scanner's current stock picks", "trending up, fresh crossovers first")}
      <p>{picks}</p>

      {section("Stocks held now")}
      {_pos_table(stocks, "stock")}
    """


def page_holdings():
    stocks, coins = stock_positions(), crypto_positions()
    tot = sum(float(p.market_value) for p in stocks)
    pl = sum(float(p.unrealized_pl) for p in stocks)
    return f"""
      {page_header("Stock holdings", "Every stock position the robot currently owns.")}
      <div class="cards">
        {stat("Positions", f"{len(stocks)} <span class='muted'>/ {settings.MAX_STOCKS_HELD}</span>")}
        {stat("Market value", money(tot))}
        {stat("Open P / L", money(pl), "unrealized", cls_for(pl))}
      </div>
      {section("Positions")}
      {_pos_table(stocks, "stock")}
      {section("SPY cash sleeve", "idle cash parked in the index · not a stock pick, doesn't use a stock slot") if sleeve_positions() else ""}
      {_pos_table(sleeve_positions(), "stock") if sleeve_positions() else ""}
      <p class="muted">Crypto is on its own page (<a class="tk" href="/crypto">{len(coins)} coin(s)</a>).</p>
    """


def page_crypto():
    coins = crypto_positions()
    tot = sum(float(p.market_value) for p in coins)
    pl = sum(float(p.unrealized_pl) for p in coins)
    db = diary.get_db()
    ts = {}
    try:
        ts = get_trade_scores().get("crypto_sma_v1", {})
    except Exception:
        pass
    recent = db.execute("""
        SELECT d.ts_utc, d.symbol, d.action, d.reason FROM decisions d JOIN runs r ON d.run_id=r.run_id
        WHERE r.strategy='crypto_sma_v1' ORDER BY d.decision_id DESC LIMIT 40
    """).fetchall()
    realised = ""
    if ts.get("round_trips"):
        realised = stat("Realised P / L", money(ts["realised_pnl"]),
                        f"{ts['round_trips']} closed trade(s)", cls_for(ts["realised_pnl"]))
    return f"""
      {page_header("Crypto", f"Trades 24/7 — this sleeve never stops. {C_FAST}-day vs {C_SLOW}-day average signal, {len(settings.CRYPTO_UNIVERSE)} coins.")}
      <div class="cards">
        {stat("Coins held", f"{len(coins)} <span class='muted'>/ {settings.MAX_CRYPTO_HELD}</span>")}
        {stat("Market value", money(tot))}
        {stat("Open P / L", money(pl), "unrealized", cls_for(pl))}
        {realised}
      </div>
      <p class="muted">Limits: ${settings.CRYPTO_DOLLARS_PER_BUY} per buy, ${settings.MAX_DOLLARS_PER_CRYPTO} max per coin,
        {settings.MAX_CRYPTO_TRADES_PER_DAY} trades/day. Emergency stop at &minus;{settings.CRYPTO_STOP_LOSS_PCT}%.</p>
      {section("Coins held")}
      {_pos_table(coins, "crypto")}
      {section("Recent crypto decisions")}
      {_decisions_table(recent, "Coin")}
    """


def page_decisions(qs):
    db = diary.get_db()
    strat = qs.get("strategy", [None])[0]
    all_strats = [r["strategy"] for r in db.execute("SELECT DISTINCT strategy FROM runs ORDER BY strategy")]
    filt = "WHERE r.strategy = ?" if strat else ""
    args = (strat,) if strat else ()
    rows = db.execute(f"""
        SELECT d.*, r.strategy AS strategy FROM decisions d JOIN runs r ON d.run_id = r.run_id
        {filt} ORDER BY d.decision_id DESC LIMIT 250
    """, args).fetchall()

    def chip(href, label, on):
        return f'<a href="{href}" class="pill{" hot" if on else ""}">{label}</a>'
    chips = chip("/decisions", "all", not strat) + " " + " ".join(
        chip(f"/decisions?strategy={html.escape(s)}", STRAT_NAMES.get(s, s), strat == s) for s in all_strats)

    body = "".join(
        f"<tr><td class='num muted'>{r['ts_utc'][:16].replace('T',' ')}</td>"
        f"<td class='muted'>{html.escape(STRAT_NAMES.get(r['strategy'], r['strategy']))}</td>"
        f"<td class='sym'>{r['symbol']}</td>"
        f"<td><span class='badge {r['action'].lower()}'>{r['action']}</span></td>"
        f"<td class='num'>{money(r['ref_price'])}</td>"
        f"<td class='why'>{html.escape(r['reason'])}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='6' class='muted'>No decisions yet.</td></tr>"

    return f"""
      {page_header("Decisions", "Every BUY / SELL / WAIT the robots considered, newest first (last 250).")}
      <p>{chips}</p>
      <table><tr><th>When (UTC)</th><th>Robot</th><th>Symbol</th><th>Call</th><th class='num'>Price</th><th>Reason</th></tr>
      {body}</table>"""


def page_trades():
    db = diary.get_db()
    rows = db.execute("""
        SELECT t.*, r.strategy AS strategy FROM trades t JOIN runs r ON t.run_id = r.run_id
        ORDER BY t.trade_id DESC LIMIT 250
    """).fetchall()
    status_cls = {"filled": "up", "blocked": "down", "not_filled": "down", "skipped": "flat",
                  "pretend": "flat", "advisory": "flat"}
    body = "".join(
        f"<tr><td class='num muted'>{r['ts_utc'][:16].replace('T',' ')}</td>"
        f"<td class='muted'>{html.escape(STRAT_NAMES.get(r['strategy'], r['strategy']))}</td>"
        f"<td class='sym'>{r['symbol']}</td><td>{r['side']}</td>"
        f"<td class='{status_cls.get(r['status'],'')}'>{r['status']}</td>"
        f"<td class='num'>{r['shares'] if r['shares'] is not None else '—'}</td>"
        f"<td class='num'>{money(r['fill_price'])}</td><td class='num'>{money(r['gross_amount'])}</td>"
        f"<td class='why'>{html.escape(r['note'] or '')}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='9' class='muted'>No trades yet.</td></tr>"
    return f"""
      {page_header("Trades", "Every order the robots attempted — filled, blocked, or skipped (last 250).")}
      <table>
      <tr><th>When (UTC)</th><th>Robot</th><th>Symbol</th><th>Side</th><th>Status</th>
          <th class='num'>Shares</th><th class='num'>Price</th><th class='num'>Amount</th><th>Note</th></tr>{body}</table>"""


def page_scoreboard():
    db = diary.get_db()
    out = [page_header("Scoreboard",
                       "Is it actually working? Real completed trades vs. the S&P 500 — the number that matters.")]

    # --- Part 1: whole account ---
    first = db.execute("SELECT equity_before FROM runs WHERE equity_before IS NOT NULL ORDER BY run_id LIMIT 1").fetchone()
    try:
        now_equity = float(get_account().equity)
    except Exception:
        now_equity = None
    start_equity = float(first["equity_before"]) if first else None
    if start_equity and now_equity is not None:
        change = now_equity - start_equity
        out.append(section("The whole account", "stocks + options + crypto + cash"))
        out.append('<div class="cards">'
                   + stat("Started at", money(start_equity))
                   + stat("Now", money(now_equity))
                   + stat("Change", f"{money(change)}", pct(change / start_equity * 100), cls_for(change))
                   + '</div>')

    # --- Part 2: real completed trades ---
    out.append(section("Real completed trades",
                       f"each finished buy→sell counted once · a {settings.STOCK_SLIPPAGE_PCT}%/"
                       f"{settings.CRYPTO_SLIPPAGE_PCT}% slippage cost is already priced in"))
    try:
        ts = get_trade_scores()
    except Exception as e:
        ts = {}
        out.append(f"<p class='warn'>Trade grading unavailable: {html.escape(str(e))}</p>")

    if not any(v["round_trips"] for v in ts.values()):
        out.append("<div class='empty'>No round trips closed yet — every position is still open. "
                   "Check back once the robot has sold something it bought.</div>")

    for strat, s in sorted(ts.items()):
        name = STRAT_NAMES.get(strat, strat)
        n = s["round_trips"]
        if not n:
            out.append(f"<p><b>{html.escape(name)}</b> &nbsp;<span class='muted'>— 0 completed, "
                       f"{s['still_open']} still open ({money(s['open_cost'])} at cost)</span></p>")
            continue
        out.append(section(name))
        vs_txt, vcls = "—", ""
        if s["avg_spy_return_pct"] is not None:
            d = s["avg_return_pct"] - s["avg_spy_return_pct"]
            vs_txt = f"{'Beat' if d > 0 else 'Lost to'} SPY<br>by {abs(d):.2f}%/trade"
            vcls = "up" if d > 0 else "down"
        out.append('<div class="cards">'
                   + stat("Completed", str(n), f"{s['still_open']} still open")
                   + stat("Win rate", f"{s['win_rate']:.0f}%", f"{s['wins']} won / {n - s['wins']} lost")
                   + stat("Avg / trade", pct(s['avg_return_pct']), cls=cls_for(s['avg_return_pct']))
                   + stat("Realised", money(s['realised_pnl']), cls=cls_for(s['realised_pnl']))
                   + f'<div class="stat"><div class="s-label">vs. S&amp;P 500</div>'
                     f'<div class="s-val sm {vcls}">{vs_txt}</div></div>'
                   + '</div>')
        recent = sorted(s["closed"], key=lambda c: c["sell_ts"], reverse=True)[:12]
        px_mult = 100 if strat == "options_long_v1" else 1
        out.append("<table><tr><th>Closed</th><th>Symbol</th><th class='num'>Bought</th>"
                   "<th class='num'>Sold</th><th class='num'>Result</th><th class='num'>P / L</th>"
                   "<th class='num'>SPY then</th></tr>" + "".join(
            f"<tr><td class='num muted'>{c['sell_ts'][:10]}</td><td class='sym'>{c['symbol']}</td>"
            f"<td class='num'>{money(c['buy_price'] * px_mult)}</td><td class='num'>{money(c['sell_price'] * px_mult)}</td>"
            f"<td class='num {cls_for(c['ret_pct'])}'>{pct(c['ret_pct'])}</td>"
            f"<td class='num {cls_for(c['pnl'])}'>{money(c['pnl'])}</td>"
            f"<td class='num muted'>{pct(c['spy_ret_pct']) if c['spy_ret_pct'] is not None else '—'}</td></tr>"
            for c in recent) + "</table>")

    # --- Part 3: AI advisor ---
    ai = get_scores(10).get("claude_advisor_v1")
    if ai:
        out.append(section("AI advisor", "never trades — we just check whether its call pointed the right way after 3 days"))
        if not ai["judged"]:
            out.append(f"<div class='empty'>{ai['decisions']} opinions logged, {ai['pending']} waiting "
                       f"to be graded (need 10 trading days to pass).</div>")
        else:
            out.append('<div class="cards">'
                       + stat("Opinions graded", str(ai['judged']))
                       + stat("Pointed right", f"{ai['hit_rate']:.0f}%", f"{ai['right']} of {ai['judged']}")
                       + stat("Avg move called", pct(ai['avg_earned_pct']), cls=cls_for(ai['avg_earned_pct']))
                       + '</div>')

    return "".join(out)


def page_universe():
    try:
        analysis, short, held = get_scan()
    except Exception as e:
        return page_header("Universe") + f"<p class='warn'>Scan unavailable: {html.escape(str(e))}</p>"
    short_set = set(short[:settings.SHORTLIST_SIZE])
    n_up = sum(1 for a in analysis.values() if a.get("enough_data") and a["trending_up"])
    n_cross = sum(1 for a in analysis.values() if a.get("enough_data") and a["crossed_up"])
    rows = []
    for sym in settings.ALLOWED_STOCKS:
        a = analysis.get(sym, {})
        if not a.get("enough_data"):
            rows.append((99, sym, f"<tr><td class='sym'>{sym}</td>"
                                  f"<td class='muted' colspan='5'>not enough data</td></tr>"))
            continue
        trend = ("<span class='trend-up'>▲ up</span>" if a["trending_up"]
                 else "<span class='trend-down'>▼ down</span>")
        tags = []
        if sym in held: tags.append("<span class='pill'>held</span>")
        if sym in short_set: tags.append("<span class='pill'>shortlist</span>")
        if a["crossed_up"]: tags.append("<span class='pill hot'>fresh crossover</span>")
        rsi = a.get("rsi14")
        rsi_cls = ("down" if (rsi is not None and rsi > settings.RSI_OVERBOUGHT)
                   else "up" if (rsi is not None and rsi < 35) else "muted")
        rsi_txt = f"{rsi:.0f}" if rsi is not None else "—"
        m3 = a.get("mom_63d")
        m3_txt = pct(m3) if m3 is not None else "—"
        atr = a.get("atr_pct")
        atr_txt = f"{atr:.1f}%" if atr else "—"
        sort_key = (0 if sym in held else 1, 0 if sym in short_set else 1,
                    -(m3 if m3 is not None else a["move_5d_pct"]))
        rows.append((sort_key, sym,
                     f"<tr><td class='sym'>{sym}</td><td class='num'>{money(a['price'])}</td><td>{trend}</td>"
                     f"<td class='num {cls_for(m3)}'>{m3_txt}</td>"
                     f"<td class='num {rsi_cls}'>{rsi_txt}</td>"
                     f"<td class='num muted'>{atr_txt}</td>"
                     f"<td class='num {cls_for(a['move_5d_pct'])}'>{pct(a['move_5d_pct'])}</td>"
                     f"<td>{' '.join(tags)}</td></tr>"))
    rows.sort(key=lambda t: (t[0], t[1]))
    body = "".join(r for _, _, r in rows)
    return f"""
      {page_header("Universe", f"The {len(settings.ALLOWED_STOCKS)} stocks the robot may consider. Held first, then the shortlist, then by 3-month momentum.")}
      <div class="cards">
        {stat("In the list", str(len(settings.ALLOWED_STOCKS)))}
        {stat("Trending up", str(n_up), "5-day avg above 20-day")}
        {stat("Fresh crossovers", str(n_cross), "crossed up today")}
      </div>
      {section("All stocks", "3mo = 3-month return · RSI &gt;78 = overbought (skipped) · ATR% = daily volatility")}
      <table><tr><th>Stock</th><th class='num'>Price</th><th>Trend</th><th class='num'>3mo</th>
        <th class='num'>RSI</th><th class='num'>ATR%</th><th class='num'>5-day</th><th>Tags</th></tr>{body}</table>"""


def _md(text):
    """Tiny markdown -> HTML for the daily-review notes (headings, bold, lists,
    links, rules, inline code). Good enough for Claude's plain prose."""
    import re
    out, in_ul, in_ol = [], False, False

    def inline(s):
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        s = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a class="tk" href="\2">\1</a>', s)
        return s

    for raw in text.split("\n"):
        line = raw.rstrip()
        m_ul = re.match(r"\s*[-*]\s+(.*)", line)
        m_ol = re.match(r"\s*\d+\.\s+(.*)", line)
        if not m_ul and in_ul:
            out.append("</ul>"); in_ul = False
        if not m_ol and in_ol:
            out.append("</ol>"); in_ol = False
        if not line:
            continue
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("# "):
            out.append(f"<h3>{inline(line[2:])}</h3>")
        elif line.strip() in ("---", "***", "___"):
            out.append("<hr>")
        elif m_ul:
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{inline(m_ul.group(1))}</li>")
        elif m_ol:
            if not in_ol:
                out.append("<ol>"); in_ol = True
            out.append(f"<li>{inline(m_ol.group(1))}</li>")
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_ul:
        out.append("</ul>")
    if in_ol:
        out.append("</ol>")
    return "\n".join(out)


def page_research(qs):
    rdir = os.path.join(HERE, "research")
    files = sorted(__import__("glob").glob(os.path.join(rdir, "20*.md")), reverse=True)
    if not files:
        return (page_header("Research", "The bot's daily 'research & learn' notes.")
                + "<div class='empty'>No daily reviews yet. The first one runs tonight "
                  "(or run <code>./service.sh research-now</code>).</div>")
    want = qs.get("d", [None])[0]
    path = next((f for f in files if os.path.basename(f).startswith(want or "")), files[0])
    with open(path) as fh:
        raw = fh.read()
    # drop the collapsible raw-data dump + the model/token footer
    note = raw.split("\n---\n\n<details>", 1)[0]
    dates = [os.path.basename(f)[:-3] for f in files]
    cur = os.path.basename(path)[:-3]
    picker = " ".join(
        f'<a href="/research?d={d}" class="pill{" hot" if d == cur else ""}">{d}</a>' for d in dates[:30])
    return f"""
      {page_header("Research", "Every day the bot reviews its own results, the market, and the news, and writes an honest note. It never changes a setting — you read these and decide.")}
      <p>{picker}</p>
      <div class="panel" style="padding:20px 24px">{_md(note)}</div>
    """


def page_news(qs):
    ndir = os.path.join(HERE, "news")
    files = sorted(__import__("glob").glob(os.path.join(ndir, "20*.md")), reverse=True)
    hdr = page_header("Pre-market news",
                      "Before the open each trading day the bot reads the overnight news and "
                      "decides a market read + per-stock verdicts. It uses these to pause "
                      "buying on risk-off days, skip a candidate with bad news, and exit a "
                      "holding whose news turns to a clear disaster — it never picks stocks "
                      "on news alone.")
    if not files:
        return hdr + ("<div class='empty'>No news scan yet. It runs ~8:45am ET on trading "
                      "days (or run <code>./service.sh news-now</code>).</div>")
    want = qs.get("d", [None])[0]
    path = next((f for f in files if os.path.basename(f).startswith(want or "")), files[0])
    with open(path) as fh:
        note = fh.read()
    dates = [os.path.basename(f)[:-3] for f in files]
    cur = os.path.basename(path)[:-3]
    picker = " ".join(f'<a href="/news?d={d}" class="pill{" hot" if d == cur else ""}">{d}</a>'
                      for d in dates[:30])
    return f"""{hdr}<p>{picker}</p>
      <div class="panel" style="padding:20px 24px">{_md(note)}</div>"""


# ---- intro page (web/intro.html) + its JSON feeds -------------------
SECTOR_ORDER = ["Information Technology", "Communication Services", "Consumer Discretionary",
                "Consumer Staples", "Health Care", "Financials", "Real Estate", "Industrials",
                "Materials", "Energy", "Utilities", "Miscellaneous", "ETF", "Other"]


def _r(x, nd=2):
    try:
        return None if x is None else round(float(x), nd)
    except (TypeError, ValueError):
        return None


def get_clock():
    return cached("clock", 60, lambda: trading.get_clock())


def _pos_json(p, kind):
    sector = {"crypto": "Crypto", "sleeve": "Index sleeve"}.get(kind) or sector_of(p.symbol)
    return {"sym": p.symbol, "kind": kind, "qty": _r(p.qty, 6), "value": _r(p.market_value),
            "pl": _r(p.unrealized_pl), "plpc": _r(float(p.unrealized_plpc) * 100),
            "entry": _r(p.avg_entry_price, 4), "price": _r(p.current_price, 4), "sector": sector}


def _latest_lesson():
    """First entry of research/LESSONS.md for this account: (heading, first paragraph)."""
    try:
        with open(os.path.join(HERE, "research", "LESSONS.md")) as fh:
            text = fh.read()
    except OSError:
        return None
    entries = re.findall(r"^## (.+?)\n\n(.+?)\n", text, flags=re.M)
    pick = next((e for e in entries if PROFILE["label"] in e[0]), entries[0] if entries else None)
    if not pick:
        return None
    return {"head": pick[0], "text": re.sub(r"\*\*|`", "", pick[1])[:700]}


def _latest_news():
    import glob
    files = sorted(glob.glob(os.path.join(HERE, "news", "20*.json")))
    if not files:
        return None
    try:
        with open(files[-1]) as fh:
            n = json.load(fh)
    except (OSError, ValueError):
        return None
    return {"date": n.get("date"), "read": n.get("market", {}).get("read"),
            "reason": n.get("market", {}).get("reason", ""),
            "today": n.get("date") == f"{datetime.now(timezone.utc):%Y-%m-%d}",
            "verdicts": sorted([[s, v.get("verdict")] for s, v in n.get("stocks", {}).items()])[:40]}


def intro_data():
    """Everything the intro page needs that's cheap (no 2000-stock scan, no bar fetches)."""
    a = get_account()
    equity, cash, last = float(a.equity), float(a.cash), float(a.last_equity)
    stocks, sleeve, coins = stock_positions(), sleeve_positions(), crypto_positions()
    db = diary.get_db()
    first = db.execute("SELECT equity_before FROM runs WHERE equity_before IS NOT NULL "
                       "ORDER BY run_id LIMIT 1").fetchone()
    baseline = float(first["equity_before"]) if first else None
    runs = db.execute("SELECT ts_utc, equity_after FROM runs WHERE equity_after IS NOT NULL "
                      "ORDER BY run_id").fetchall()
    rows = _dedupe_by_time([(r["ts_utc"], r["equity_after"]) for r in runs])
    step = max(1, math.ceil(len(rows) / 360))
    pts = rows[::step] + ([rows[-1]] if rows and (len(rows) - 1) % step else [])
    n_runs = db.execute("SELECT COUNT(*) AS n FROM runs WHERE mode != 'pretend'").fetchone()["n"]
    today = f"{datetime.now(timezone.utc):%Y-%m-%d}"
    fills_today = db.execute(
        "SELECT COUNT(*) AS n FROM trades t JOIN runs r ON t.run_id = r.run_id "
        "WHERE substr(t.ts_utc,1,10) = ? AND t.status = 'filled' AND r.mode != 'pretend'", (today,)).fetchone()["n"]
    decisions = db.execute("""
        SELECT d.ts_utc, d.symbol, d.action, d.reason, r.strategy FROM decisions d
        JOIN runs r ON d.run_id = r.run_id WHERE r.mode != 'pretend'
        ORDER BY d.decision_id DESC LIMIT 36""").fetchall()
    ml = db.execute("""
        SELECT d.symbol FROM decisions d JOIN runs r ON d.run_id = r.run_id
        WHERE r.run_id = (SELECT MAX(run_id) FROM runs WHERE strategy = 'ml_brain_v1')
        ORDER BY d.decision_id""").fetchall()
    try:
        clk = get_clock()
        market = {"open": bool(clk.is_open), "next_open": str(clk.next_open), "next_close": str(clk.next_close)}
    except Exception:
        market = None
    val = lambda ps: round(sum(float(p.market_value) for p in ps), 2)
    return {
        "profile": PROFILE["label"], "profile_key": PROFILE_NAME,
        "others": [{"label": p["label"], "url": f"http://localhost:{p['port']}/"}
                   for n, p in profiles.PROFILES.items() if n != PROFILE_NAME],
        "now": datetime.now(timezone.utc).isoformat(), "next_run": _next_run_hint(), "market": market,
        "equity": round(equity, 2), "cash": round(cash, 2), "last_equity": round(last, 2),
        "baseline": _r(baseline), "runs": n_runs, "fills_today": fills_today,
        "alloc": {"cash": round(cash, 2), "sleeve": val(sleeve), "stocks": val(stocks), "crypto": val(coins)},
        "holdings": [_pos_json(p, "stock") for p in stocks] + [_pos_json(p, "crypto") for p in coins],
        "sleeve": [_pos_json(p, "sleeve") for p in sleeve],
        "series": [[int(t.timestamp()), round(float(v), 2)] for t, v in pts],
        "decisions": [{"t": r["ts_utc"][:16].replace("T", " "), "sym": r["symbol"], "act": r["action"],
                       "why": (r["reason"] or "")[:180], "who": STRAT_NAMES.get(r["strategy"], r["strategy"])}
                      for r in decisions],
        "ml_picks": [r["symbol"] for r in ml],
        "news": _latest_news(), "lesson": _latest_lesson(),
        "rules": {
            "universe": len(settings.ALLOWED_STOCKS), "shortlist": settings.SHORTLIST_SIZE,
            "max_held": settings.MAX_STOCKS_HELD, "per_buy": settings.DOLLARS_PER_BUY,
            "max_per_stock": settings.MAX_DOLLARS_PER_STOCK, "vol_min": settings.VOL_SIZING_MIN,
            "vol_max": settings.VOL_SIZING_MAX, "stop": settings.STOCK_STOP_LOSS_PCT,
            "trail": settings.TRAILING_STOP_PCT, "mom_break": settings.MOMENTUM_BREAKDOWN_PCT,
            "rsi": settings.RSI_OVERBOUGHT, "sector_cap": settings.MAX_STOCKS_PER_SECTOR,
            "cooldown": settings.REBUY_COOLDOWN_DAYS, "loss_limit": settings.DAILY_LOSS_LIMIT,
            "sleeve": bool(getattr(settings, "USE_SPY_CASH_SLEEVE", False)),
            "sleeve_buffer": getattr(settings, "SPY_SLEEVE_BUFFER", None),
            "news": bool(getattr(settings, "USE_NEWS_FILTER", False)),
            "crypto": bool(getattr(settings, "TRADE_CRYPTO", False)), "crypto_max": settings.MAX_CRYPTO_HELD,
            "options": bool(getattr(settings, "TRADE_OPTIONS", False)),
            "trend_min": settings.MARKET_TREND_MIN_MOM63, "max_mkt_atr": settings.MAX_MARKET_ATR_PCT,
        },
    }


def extras_data():
    """Slower bits, fetched after the page loads: 90-day price lines for each
    holding + the real-trade scoreboard. Cached 5 min (shares the bot's API budget)."""
    def make():
        out = {"spark": {}, "scores": []}
        start = datetime.now(timezone.utc) - timedelta(days=140)
        syms = [p.symbol for p in stock_positions() + sleeve_positions()]
        if syms:
            try:
                bars = data.get_stock_bars(StockBarsRequest(
                    symbol_or_symbols=syms, timeframe=TimeFrame.Day, start=start,
                    adjustment=Adjustment.ALL)).data
                for s in syms:
                    out["spark"][s] = [round(b.close, 4) for b in bars.get(s, [])][-90:]
            except Exception:
                pass
        pairs = {p.symbol: (p.symbol[:-3] + "/USD" if p.symbol.endswith("USD") else p.symbol)
                 for p in crypto_positions()}
        if pairs:
            try:
                cb = crypto_data.get_crypto_bars(CryptoBarsRequest(
                    symbol_or_symbols=list(pairs.values()), timeframe=TimeFrame.Day, start=start)).data
                for sym, pair in pairs.items():
                    out["spark"][sym] = [round(b.close, 6) for b in cb.get(pair, [])][-90:]
            except Exception:
                pass
        try:
            for strat, sc in sorted(get_trade_scores().items()):
                out["scores"].append({
                    "key": strat, "name": STRAT_NAMES.get(strat, strat), "n": sc["round_trips"],
                    "open": sc.get("still_open"), "win": _r(sc.get("win_rate")), "wins": sc.get("wins"),
                    "avg": _r(sc.get("avg_return_pct")), "spy": _r(sc.get("avg_spy_return_pct")),
                    "pnl": _r(sc.get("realised_pnl"))})
        except Exception:
            pass
        return out
    return cached("extras", 300, make)


def universe_data():
    """The whole scan, compact, for the galaxy. The heavy part (one bar request for
    ~2000 symbols, shared API keys with the live bot) is get_scan's background refresh."""
    def make():
        analysis, short, held = get_scan()
        top = short[:settings.SHORTLIST_SIZE]
        rows = []
        for sym in settings.ALLOWED_STOCKS:
            a = analysis.get(sym) or {}
            if not a.get("enough_data"):
                continue
            sec = sector_of(sym)
            flags = (1 if sym in held else 0) | (2 if sym in top else 0) | (4 if a.get("crossed_up") else 0)
            rows.append([sym, SECTOR_ORDER.index(sec) if sec in SECTOR_ORDER else len(SECTOR_ORDER) - 1,
                         _r(a.get("mom_63d"), 1), _r(a.get("mom_126d"), 1), _r(a.get("rsi14"), 0),
                         _r(a.get("atr_pct"), 2), 1 if a.get("trending_up") else 0, flags])
        return {"sectors": SECTOR_ORDER, "rows": rows, "shortlist": top,
                "n_list": len(settings.ALLOWED_STOCKS),
                "n_up": sum(1 for r in rows if r[6]), "n_cross": sum(1 for r in rows if r[7] & 4)}
    return cached("universe", 120, make)   # cheap: derived from the (background-refreshed) scan


def page_intro():
    try:
        boot = intro_data()
    except Exception as e:
        boot = {"error": str(e)}
    with open(os.path.join(WEB, "intro.html")) as fh:
        tpl = fh.read()
    # no raw "<" inside the JSON island (reasons/news are LLM-written); JSON.parse reads \u003c back as "<"
    return tpl.replace("__BOOT_DATA__", json.dumps(boot).replace("<", "\\u003c"))


API = {"/api/intro": intro_data, "/api/extras": extras_data, "/api/universe": universe_data}
STATIC = {"/static/intro.js": ("intro.js", "application/javascript; charset=utf-8"),
          "/static/fx.js": ("fx.js", "application/javascript; charset=utf-8")}


ROUTES = {
    "/overview": lambda qs: page_overview(),
    "/holdings": lambda qs: page_holdings(),
    "/crypto": lambda qs: page_crypto(),
    "/decisions": lambda qs: page_decisions(qs),
    "/trades": lambda qs: page_trades(),
    "/scoreboard": lambda qs: page_scoreboard(),
    "/universe": lambda qs: page_universe(),
    "/news": lambda qs: page_news(qs),
    "/research": lambda qs: page_research(qs),
}
TITLES = {h: t for h, t in NAV}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(page_intro().encode("utf-8"), "text/html; charset=utf-8")
        if u.path in API:
            try:
                payload = API[u.path]()
            except Exception as e:
                payload = {"error": str(e)}
            return self._send(json.dumps(payload).encode("utf-8"), "application/json")
        if u.path in STATIC:            # fixed allow-list, never a path built from the URL
            name, ctype = STATIC[u.path]
            with open(os.path.join(WEB, name), "rb") as fh:
                return self._send(fh.read(), ctype)
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
        # the page is live data and changes every run — never let the browser
        # serve a stale copy, so a plain refresh always shows the latest.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    refresh_scan_in_background()          # warm the slow scan so the first Overview/Universe visit is instant
    print(f"Website running. Open this in your browser:\n\n    http://localhost:{PORT}\n")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWebsite stopped.")
