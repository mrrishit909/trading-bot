# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A learn-by-building paper-money trading bot on Alpaca. Two independent accounts run
side by side from the same codebase (see "Account profiles" below). Everything is
plain Python (no build step, no test suite, no package manager beyond `pip`) — each
`stepN_*.py` file is a standalone script meant to be run directly.

```
./venv/bin/python <script>.py             # always use the venv's python, never bare `python`
```

## Common commands

**Run everything** (both accounts' schedulers + both dashboards, via launchd):
```
./service.sh start | stop | restart | status
./service.sh web              # (re)start only the two dashboards (:8777 main, :8778 sprint500)
./service.sh research-now     # run today's daily review immediately (~$0.09, claude-opus-5)
./service.sh logs | sprint-logs | ai-logs | web-logs | research-logs
```

**Run one thing by hand** (always accepts `--pretend` = log decisions, place no orders):
```
./venv/bin/python auto_run.py --once [--profile sprint500] [--no-ai] [--no-crypto]
./venv/bin/python step10_scan_and_trade.py [--pretend]     # stocks
./venv/bin/python step12_crypto.py [--pretend]             # crypto
./venv/bin/python step11_options.py [--pretend]            # options (currently OFF, see below)
./venv/bin/python step9_ai_advisor.py [--if-open]          # AI opinions only, never trades
```

**Backtest** (real history, no live trading calls):
```
./venv/bin/python backtest.py [--years N]          # stocks
./venv/bin/python backtest_crypto.py [--years N]   # crypto (benchmark: buy & hold BTC)
```
Both call the SAME `signals_from_series` the live robots use (stocks:
`scanner.py`, crypto: `crypto_scanner.py`) over a trailing window — never a
second signal implementation. As of 2026-09-22 (rotation + scale-out
machinery both wired in, both off by default — see `USE_RANK_ROTATION` in
`settings.py`): stocks +13.3% / −5.6% dd over 2.1yr (vs SPY +43.6% — still
losing to buy-and-hold by ~30 points, rotation-off just removed a real leak,
it didn't close the gap); crypto (2026-09-09 run) **−32.5% over the last
year, −60% drawdown, worse than holding BTC** — the crypto SMA sleeve has not
demonstrated an edge in backtest, though it has been the one live sleeve
beating SPY per-trade on both accounts (small sample, still noisy).

**Grade what actually happened:**
```
./venv/bin/python compare.py [lookahead_days]     # CLI scoreboard
./venv/bin/python show_diary.py [trades|decisions|runs]
```

**Reconcile the diary against Alpaca** (fixes fills a step script's confirmation
poll missed — runs automatically after every `auto_run` cycle):
```
./venv/bin/python reconcile.py [--profile sprint500] [--days 45] [--dry-run]
```

There is no lint/build/test step — the closest thing to a smoke test is running a
script with `--pretend` and reading its output, or running `backtest.py`.

## Architecture

### Two accounts, one codebase: the profile system

`profiles.py` defines named profiles (`main` = the original ~$100k account, all
strategies; `sprint500` = a $500 account, stocks+crypto only, tighter/more
aggressive settings). A profile bundles: which `.env` file to load, which
`diary.db` file to use, which strategies to run, and a dict of `settings.py`
overrides.

The mechanism (important — this is not obvious from any single file):
- `auto_run.py --profile X` loads that profile's `.env`, builds a child
  environment (`ROBOT_PROFILE=X`, `ROBOT_DIARY_PATH=...`, the profile's Alpaca
  keys), and runs each `stepN_*.py` as a **subprocess** with that environment.
- Every `stepN_*.py` calls `load_dotenv()` on import, but `python-dotenv` never
  overrides an already-set env var — so the subprocess's injected keys win and
  the step scripts themselves needed no profile-awareness added to them.
- `settings.py` reads `ROBOT_PROFILE` from the environment at import time and,
  if it's not `"main"`, overwrites its own module globals with that profile's
  `overrides` dict. Any file that does `import settings` and reads
  `settings.SOME_CONST` automatically gets the right profile's value — there is
  no per-call profile parameter anywhere.
- `diary.py`'s `DB_PATH` reads `ROBOT_DIARY_PATH` the same way.
- `dashboard.py` does this same env-setup dance itself (it's a long-running
  process, not a per-run subprocess), keyed off `ROBOT_PROFILE` in *its own*
  process environment, and serves on the profile's configured port.

When adding a new setting that should differ between accounts, add it to
`settings.py` as normal, then add an override in `profiles.py` if `sprint500`
needs a different value — nothing else needs to change.

### The signal math is shared between live trading and the backtest

`scanner.signals_from_series(closes, highs, lows)` is the one place every
number the bot trades on gets computed (SMA fast/slow, RSI14, ATR%, 3-/6-month
momentum, crossover flags). `analyze_all()` is a thin wrapper that fetches bars
once and calls this per symbol for "today." `backtest.py` calls the *exact same
function* with a truncated trailing window ending on each simulated day — this
is deliberate: the backtest tests the real signal code, not a second
implementation that could quietly drift out of sync with live trading. If you
change the signal math, both live trading and the backtest pick it up for free;
if you're tempted to special-case something for the backtest, put it in
`signals_from_series` instead.

`crypto_scanner.py` mirrors this pattern for crypto but is not wired into the
backtest (stocks only, for now).

### Decision flow per run (`step10_scan_and_trade.py`, mirrored in `backtest.py`)

SELL pass over current holdings, in priority order — first match wins:
1. Hard stop-loss (volatility-adaptive: `min(STOCK_STOP_LOSS_PCT, max(4%, ATR_MULT * atr_pct))`)
2. Trailing stop — **only if the position is currently profitable** (protects
   gains; losers are handled by #1 and #5, never by this)
3. Momentum-breakdown exit — sell if 3-month momentum has broken down hard
   even though the short-term average still says "trending up" (a bounce
   inside a real downtrend; added after the daily-review routine caught ORCL
   sitting in exactly this state)
4. News "avoid" — sell if today's pre-market news scan flagged a clear
   negative catalyst on the name (see the news filter below)
5. SMA sell-signal (fast average clearly below slow, with a buffer against whipsaw)

BUY pass, gated by three independent regime gates (any one can zero out room
for new buys without touching existing holdings) — market trend (SPY's own
63-day return vs `MARKET_TREND_MIN_MOM63`, default −3%; **not** an SMA
crossover — that gate was too twitchy and parked the account in cash through
an up market, see the `settings.py` note), market volatility (SPY's own ATR%,
a no-account-needed VIX stand-in, cap `MAX_MARKET_ATR_PCT` ≈ p95 of history),
and the pre-market news read (`risk_off` → no buys today). Then ranked by momentum
(`scanner.rank_buys`, needs positive 3-month return + not overbought on RSI),
then filtered by the news scan again (a candidate whose overnight news is
`avoid`/`negative` is skipped), the re-buy cooldown, and the sector cap
(`sectors.py`, max N per GICS-ish sector so "8 positions" can't quietly mean
"8 tech stocks"), then sized by volatility (`USE_VOL_SIZING`: smaller dollar
amount for a jumpier stock, so every position carries similar risk, clamped to
`[VOL_SIZING_MIN, VOL_SIZING_MAX]` = 0.6–1.4×) and bought
as a **fractional/notional order** (`place_buy` in `step10_scan_and_trade.py`
tries notional first, falls back to whole shares if the asset isn't
fractionable).

`step12_crypto.py` follows the same shape (stop-loss → trailing → momentum-
breakdown → SMA-reversal, then cooldown + a "don't chase a blow-off top"
guard) with its own settings.

`SCALE_OUT_ENABLED` (default **off**) adds a partial profit-take to the stock
SELL pass: the first time a position is up ≥ `SCALE_OUT_GAIN_PCT`, sell
`SCALE_OUT_FRACTION` of it (tagged `note='scale-out'`, tracked via
`diary.already_scaled_out` so it fires once per holding period) and keep the
rest. The backtest showed it slightly *reduces* return in a trending market
(clips winners) for a slightly smaller drawdown — machinery kept, left off.

`USE_RANK_ROTATION` (default **off**, was on until 2026-09-22) was meant to
fix a gap the daily reviews caught repeatedly: when all `MAX_STOCKS_HELD`
slots are full, a far stronger new signal (e.g. MRNA sitting at +190%
momentum for days, cooldown long lapsed) was permanently locked out — nothing
forces an upgrade. When room is 0 and the best waiting candidate beats the
weakest HELD position's `scanner.momentum_score` by `ROTATION_MARGIN_PTS`, it
sells the weakest (respecting `ROTATION_MIN_HOLD_DAYS` so a name bought
yesterday can't be churned) and lets the normal BUY loop fill the freed slot.
Deliberately **not** sector-matched — the freed slot goes through the
existing sector-cap check, so rotating out a name from an already-over-cap
sector nudges that sector back toward the limit over time instead of
perpetually restocking it. Confirmed live 2026-09-15 (MSFT → TEAM) — but by
2026-09-21 four more live instances (BBY, HOOD, NOW, AAPL, ILMN x2) showed it
routinely rotating out a name right before or after it re-ranked top,
including one sold-low-rebought-high round trip (ILMN, +20.6% worse cost
basis). A same-window backtest confirmed rotation ON net *loses* to rotation
OFF on every axis (return, drawdown, win rate, avg trade) — see
`settings.py`'s note on `USE_RANK_ROTATION`. Machinery kept, switched off.

### The SPY cash sleeve (main account only)

`settings.USE_SPY_CASH_SLEEVE` (on since 2026-09-29; `sprint500` overrides it
off). Idle cash above `SPY_SLEEVE_BUFFER` ($12k, kept for crypto buys) is parked
in SPY at the end of every `step10` run; a stock buy that needs more cash than is
on hand sells SPY first; with `SPY_SLEEVE_RISK_OFF_EXIT` the whole sleeve goes to
cash when the market-trend/volatility gate fails. Trades only when the sleeve is
`SPY_SLEEVE_MIN_TRADE` ($2k) off target, so the 30-min schedule doesn't churn.
`backtest.py` mirrors it. Why: the bot's gap to SPY was mostly idle cash, and a
same-window backtest on the 2000-name list gave no sleeve +24.2%/-9.7% dd, sleeve
with risk-off exit +41.1%/-13.2%, always-in sleeve +51.3%/-19.7% (SPY +41.2%).

**SPY is a sleeve, not a holding** — keep it that way when editing:
`step10.held_positions()` and `safety.py` rule 1b skip SPY (no sell rules, no
slot); sleeve orders call `can_i_trade(..., sleeve=True)` (bad-day + trade-count
rules only); they're logged under their own run with strategy `spy_sleeve_v1`
(and `reconcile.strategy_for("SPY")` maps there), so the stock scoreboard stays
clean. `rank_buys` must keep excluding SPY in both step10 and the backtest.

### Options are currently OFF

`settings.TRADE_OPTIONS = False`. `step11_options.py` still runs on schedule,
but in this state it only *closes* any option position it finds open — it
never opens a new one, and exits instantly once the book is empty. This is
deliberate (the options sleeve was the strategy's clearest loser); the code
is left in place and working in case it's ever turned back on.

### Diary + grading

Every run writes to a per-profile SQLite file (`diary.db` / `diary_sprint500.db`)
via `diary.py`: one row in `runs` per invocation, one row in `decisions` per
symbol considered (BUY/SELL/WAIT + the reasoning text), one row in `trades`
per order attempt (status: filled/blocked/skipped/pretend/error).

Order fills are confirmed by `fills.confirm_fill` (shared by step10 and step12).
Market orders almost always fill, but Alpaca's fill *confirmation* can lag
several seconds — the old code gave up after ~12s and wrote `not_filled` even
though the order filled moments later, silently dropping real round trips from
the record. `confirm_fill` polls longer, keeps checking past the timeout, counts
a partial fill, and for a position-closing sell verifies the position actually
cleared before admitting defeat. `reconcile.py` is the backstop: it compares the
diary to Alpaca's authoritative order history and corrects/backfills rows (it
runs automatically at the end of every `auto_run` cycle). Backfilled rows are
attributed to a strategy by asset class (`sma_scan_v1` / `crypto_sma_v1` /
`options_long_v1`) under a synthetic `mode='reconcile'` run.

`grader.py` has two different scoring functions that answer different
questions and should not be confused:
- `grade_all()` — "was the *signal* right?", judged against price N days
  later. Massively over-counts (a stock held 20 days generates ~20 duplicate
  WAIT rows), so treat its numbers as noisy; the AI advisor (which never
  trades) is graded this way since it has no round trips to match.
- `grade_trades()` — "what did we *actually make*?", FIFO-matches real filled
  buys to the sell that closed them, one row per completed round trip. This
  is the honest number, shown as "REAL TRADES" in `compare.py` and on the
  Scoreboard dashboard page. It applies a slippage haircut
  (`settings.*_SLIPPAGE_PCT`) to both legs so the number reflects realistic
  costs, not optimistic paper fills.

### The pre-market news filter

`news_scan.py` (own LaunchAgent, `com.trading-robot.news`, ~8:45am ET on
trading days only — it clock-checks and no-ops otherwise) reads the overnight
Alpaca news (broad market + the momentum shortlist + current holdings), asks
`claude-opus-5` for a `risk_on|neutral|risk_off` market read plus per-stock
`positive|neutral|negative|avoid` verdicts, and writes `news/YYYY-MM-DD.json`
(+ a `.md` for the dashboard). It is **profile-agnostic** — one scan, one
file, both accounts' `step10` runs read it.

`step10_scan_and_trade.py` loads `news/<today>.json` (only if `date` matches
today — otherwise it silently trades on the signals alone) and uses it three
ways: pause all buys on `risk_off`, skip a buy candidate whose verdict is
`avoid`/`negative`, and add a SELL trigger for a held name whose verdict is
`avoid`. It never selects a stock from news — the momentum strategy still
picks; news only keeps it off landmines. Not replayed in `backtest.py` (no
historical news-sentiment feed).

The scan also enforces an **earnings blackout**: a held or shortlisted stock
that reports earnings within ~2 trading days gets verdict `avoid` (reason
`earnings <when>`) regardless of sentiment — so the bot exits before a binary
event and won't open into one. This is trend-following; earnings is not its
edge, and a gap can blow straight through the stop (ADBE −12.5% on 2026-09-08).

### The AI advisor — currently PAUSED

`step9_ai_advisor.py` (strategy `claude_advisor_v1`, scheduled 2×/weekday) asks
Claude for a BUY/SELL/WAIT opinion on every held stock plus the scanner
shortlist. **It never trades** — the calls go in the diary purely so `grade_all`
can score them head-to-head against the mechanical `sma_scan_v1`. ~$0.018/run
(~$0.80/month) — cost was never the reason to pause it. `settings.AI_ADVISOR_ENABLED`
gates it everywhere (step9 exits immediately, `auto_run` skips spawning it) with
no schedule change. Set to **False** on 2026-09-15: it matured to 270 judged
decisions vs the scanner's 84, with a 31.0% hit rate against the scanner's
56.3% — a 25-point gap that *widened* as the sample grew (was 12 points behind
at 30/21 judged a few days earlier), the real-and-growing-sample condition the
daily-review notes were written to trigger. Flip back to `True` to resume.

### The daily research routine

`daily_review.py` (own LaunchAgent, `com.trading-robot.research`, ~5:20pm
daily) gathers the account state, `grade_trades`/`grade_all` output, recent
decisions/trades, current settings, market context, and news for held stocks,
then asks `claude-opus-5` for an honest ~450-word analysis (what's working,
patterns, market fit, hypotheses to watch — explicitly instructed never to
recommend changing a live setting). It writes `research/YYYY-MM-DD.md` and
prepends a line to `research/LESSONS.md`. **This has already found real bugs
more than once** (the ORCL momentum-breakdown case above; the MRNA/rotation gap;
the AI-advisor underperformance) — when asked to improve the bot, check
whether the daily notes have flagged anything concrete before reaching for a
new indicator. The SYSTEM prompt requires each section use a markdown `##`
heading, not a bold-text line — the LESSONS.md excerpt logic pulls the first
paragraph *after* the first heading, and a bold-only "heading" used to slip
past that filter and produce an empty-looking entry (fixed 2026-09-15, both in
the prompt and defensively in the extraction regex).

### Dashboard

`dashboard.py` is a stdlib-only (`http.server`) multi-page site, one process
per account profile. Pages are plain functions returning an HTML fragment;
`shell()` wraps every page and auto-wraps any literal `<table>` in a
`<div class="panel">` — never wrap a table in `.panel` yourself in a page
function, or you get nested panels. The equity chart on Overview is an
interactive inline-SVG + vanilla-JS chart (no library) with a synthetic-
mousemove note in `daily_review`-adjacent testing: MCP browser automation's
`hover` action does not dispatch a real DOM `mousemove`, so verify chart
interactivity with `javascript_tool` dispatching a `MouseEvent`, not by
screenshotting after a `hover`.

**The intro page (`/`)** is the landing page; the old Overview moved to `/overview`.
It does not go through `shell()`: `page_intro()` serves `web/intro.html` with the
`/api/intro` payload injected as a JSON island (`</` escaped), and `web/intro.js`
does everything else — a WebGL particle field that morphs between shapes built
from live data (wordmark, allocation ring, holdings orbit with SPY as the sun,
equity surface, 2,000-stock galaxy, decision funnel), scroll/tap reveals,
count-ups, a sound toggle (off by default), an auto tour (`T`), and a custom
cursor on fine pointers. Data feeds, all cached because the live bot shares the
Alpaca keys: `/api/intro` (cheap: account, positions, diary — polled every 60s),
`/api/extras` (holding sparklines + real-trade scores, 5 min), `/api/universe`
(derived from `get_scan()` — never call the scan from `/api/intro`). `get_scan()`
takes ~20-30s for 2000 symbols, so it is stale-while-revalidate: pages get the
last scan instantly and a background thread refreshes it once it's >5 min old;
the server pre-warms it on launch (only requests in the first ~20s after a
restart wait). Don't turn it back into a blocking `cached()` call — /overview
used to hang ~30s and looked like "no data".
Static files are an explicit allow-list (`STATIC` in `dashboard.py`); never serve
a path built from the URL. Every dynamic string goes in with `textContent`
(decision reasons and news are LLM-written). Hidden-until-revealed styles only
apply under `html.fx`, which the script sets, and an inline watchdog drops them if
the script never reports in. `?debug` exposes `window.__tr` for poking at the
field from the console. The other pages load `web/fx.js` (first-visit entrance,
count-ups, spotlight) and cross-fade via CSS view transitions.
`stock_positions()` excludes SPY (it's the sleeve; see `sleeve_positions()`).


## Known constraints

- **Never run this project's files from `~/Desktop`, `~/Documents`, or
  `~/Downloads`.** macOS TCC blocks `launchd` background agents from those
  folders (`Operation not permitted`, silent `exit 78`) even though a normal
  terminal session in the same folder works fine. The repo lives at
  `~/trading-robot`; a Finder alias/symlink on the Desktop is fine, the real
  directory is not.
- LaunchAgent plists in `launchd/` (repo copies) and `~/Library/LaunchAgents/`
  (the live ones) hardcode the absolute repo path — if the repo ever moves,
  both copies need the path rewritten and the agents reloaded (`service.sh`
  does not do this for you).
