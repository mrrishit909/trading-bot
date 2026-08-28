# Cheat Sheet

Everything is in this folder: `~/trading-robot`

**First, in every terminal window, go to the folder:**
```
cd ~/trading-robot
```

Every command starts with `./venv/bin/python` (the project's own Python).

## Leaving it running for weeks (the background schedule)

```
./service.sh start     turn the schedule ON
./service.sh stop      turn it OFF
./service.sh status     is it running? what did it last do?
./service.sh logs       watch the robot's log live (Ctrl+C to stop watching)
./service.sh ai-logs    watch the AI advisor's log live
```

When ON: the robot runs every 30 min, the AI advisor twice on weekdays.
It only trades while the market is open. **Your Mac must be awake** — if it's
asleep or shut down, nothing runs until it wakes up.

## Watching it — the website

```
./venv/bin/python dashboard.py
```
Run it in its own terminal window whenever you want to look.
Then open http://localhost:8777 in your browser. Pages:
- **Overview** — account value, chart, today's picks, holdings
- **Holdings** — what you own, with profit/loss
- **Decisions** — every BUY/SELL/WAIT + the reasoning (filter by strategy)
- **Trades** — every trade attempt
- **Scoreboard** — robot vs AI, graded against what prices actually did
- **Universe** — all ~70 stocks and the current scan signal

## One-off commands

| Goal | Command |
|---|---|
| See pretend money | `./venv/bin/python step1_say_hi.py` |
| Check a price | `./venv/bin/python step2_look.py NVDA` |
| Run robot once (scan + trade) | `./venv/bin/python step10_scan_and_trade.py` |
| Run robot, no trades, just talk | `./venv/bin/python step10_scan_and_trade.py --pretend` |
| AI opinions | `./venv/bin/python step9_ai_advisor.py` |
| See the diary summary | `./venv/bin/python show_diary.py` |
| See every trade / decision / run | `./venv/bin/python show_diary.py trades` (or `decisions`, `runs`) |
| Grade robot vs AI | `./venv/bin/python compare.py` (or `compare.py 5` for 5 days) |

## Files you might edit

| File | What's in it |
|---|---|
| `settings.py` | The safety limits (max per stock, max stocks held, daily loss limit) |
| `universe.py` | The ~70 stocks the robot is allowed to consider |
| `.env` | Your secret keys (never share, never commit) |

## If something breaks

- "can't find keys" → check `.env` exists and has all 3 keys
- "address already in use" → something's on port 8777; run `./venv/bin/python dashboard.py 9001` and use http://localhost:9001
- weird Python errors → make sure you typed `./venv/bin/python`, not just `python`
