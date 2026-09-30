# Cheat Sheet

Everything is in this folder: `~/trading-robot`

**First, in every terminal window, go to the folder:**
```
cd ~/trading-robot
```

Every command starts with `./venv/bin/python` (the project's own Python).

## Two accounts

| Account | Money | Trades | Dashboard | Runs every |
|---|---|---|---|---|
| **main** | ~$100k | stocks + crypto + AI | http://localhost:8777 | 30 min |
| **sprint500** | ~$500 | stocks + crypto | http://localhost:8778 | 15 min |

Options trading is OFF on both accounts (`TRADE_OPTIONS = False` in `settings.py`).
Set it back to `True` to re-enable.

`main` uses `.env` + `diary.db`. `sprint500` uses `.env.sprint500` + `diary_sprint500.db`
and its own tighter settings (see `profiles.py`). They're fully independent.

Run one by hand:
```
./venv/bin/python auto_run.py --once                     (main)
./venv/bin/python auto_run.py --once --profile sprint500  ($500 account)
```

## Running the whole thing (both accounts + both websites)

```
./service.sh start      turn EVERYTHING on
./service.sh stop       turn EVERYTHING off
./service.sh restart     stop it all, then start it again  <-- the "whole thing" command
./service.sh status      what's running? what did it last do?
./service.sh logs        watch the MAIN robot log live (Ctrl+C to stop)
./service.sh sprint-logs watch the $500 sprint robot log live
./service.sh ai-logs     watch the AI advisor's log live
./service.sh web-logs    watch the websites' log live
./service.sh web         (re)start ONLY the websites
./service.sh web-stop    stop ONLY the websites
```

When ON, every 30 minutes (main) / 15 minutes (sprint):
- **crypto robot runs always** (crypto trades 24/7)
- **stock + options robots run only when the US market is open**
- AI advisor runs twice on weekdays

**Your Mac must be awake** — if it's asleep or shut down, nothing runs until
it wakes up.

## Watching it — the website

`./service.sh start` (or `./service.sh web`) launches it in the background.
Then open http://localhost:8777 in your browser. Pages:
- **Overview** — account value, chart, today's picks, holdings
- **Holdings** — stocks you own, with profit/loss
- **Options** — open call/put bets, live + realized P/L, recent option decisions
- **Crypto** — coins held (24/7), profit/loss, recent crypto decisions
- **Decisions** — every BUY/SELL/WAIT + the reasoning (filter by strategy)
- **Trades** — every trade attempt
- **Scoreboard** — real completed trades (actual $ won/lost, win rate, vs SPY) + AI accuracy
- **Universe** — all 300 stocks and the current scan signal

## One-off commands

| Goal | Command |
|---|---|
| See pretend money | `./venv/bin/python step1_say_hi.py` |
| Check a price | `./venv/bin/python step2_look.py NVDA` |
| Run stock robot once (scan + trade) | `./venv/bin/python step10_scan_and_trade.py` |
| Run stock robot, no trades, just talk | `./venv/bin/python step10_scan_and_trade.py --pretend` |
| Run options robot once (calls/puts) | `./venv/bin/python step11_options.py` |
| Run options robot, just talk | `./venv/bin/python step11_options.py --pretend` |
| Run crypto robot once (24/7) | `./venv/bin/python step12_crypto.py` |
| Run crypto robot, just talk | `./venv/bin/python step12_crypto.py --pretend` |
| AI opinions | `./venv/bin/python step9_ai_advisor.py` |
| See the diary summary | `./venv/bin/python show_diary.py` |
| See every trade / decision / run | `./venv/bin/python show_diary.py trades` (or `decisions`, `runs`) |
| Grade robot vs AI | `./venv/bin/python compare.py` (or `compare.py 5` for 5 days) |

## Files you might edit

| File | What's in it |
|---|---|
| `settings.py` | All the knobs — position sizes, stop-losses, `USE_MARKET_FILTER`, `REBUY_COOLDOWN_DAYS`, `TRADE_OPTIONS` |
| `profiles.py` | The two accounts (main / sprint500) and the $500 account's tighter overrides |
| `universe.py` | The 300 stocks the robot may consider |
| `crypto_universe.py` | `CRYPTO_UNIVERSE` (main, 10 coins) and `SPRINT_CRYPTO` (the $500 account's 24 hot coins) |
| `.env` | Your secret keys (never share, never commit) |

## If something breaks

- "can't find keys" → check `.env` exists and has all 3 keys
- "address already in use" → something's on port 8777; run `./venv/bin/python dashboard.py 9001` and use http://localhost:9001
- weird Python errors → make sure you typed `./venv/bin/python`, not just `python`

## Daily research & learning

Every day at 17:20 the bot writes an honest self-review to `research/YYYY-MM-DD.md`
and adds a line to `research/LESSONS.md`. It reviews completed trades vs the S&P,
what's working/not, the market, news on what it holds, and its own past notes —
then Claude writes ~450 words of analysis. It never changes a setting or trades;
you read it and decide.

- See it on the dashboard: the **Research** tab
- Run one now: `./service.sh research-now`  (costs ~$0.09, uses claude-opus-5)
- Watch the log: `./service.sh research-logs`
- Cheaper model: change `MODEL` in `daily_review.py` to `claude-sonnet-5` (~$0.03) or `claude-haiku-4-5` (~$0.015)

## Backtest the strategy

```
./venv/bin/python backtest.py                (last ~2.5 years, current stock strategy)
./venv/bin/python backtest.py --years 1.5
```

Simulates the CURRENT stock rules (momentum rank, market filter, ATR stop, trailing
stop, momentum-breakdown exit, sector cap, vol-scaled sizing) day-by-day over real
history, using the exact same signal math as the live bot. Answers "does this
approach work" in ~10 seconds instead of waiting weeks. Stocks only. Writes a report
to `research/backtest_<start>_<end>.md`. Read the limitations at the top of the file
before trusting the number — closing-price fills, one historical path, some rules
were tuned after watching live results.
