# Trading Robot 🤖

We're building a robot that trades stocks with **pretend money** first.
Small steps. One at a time. Nothing scary.

## The steps

1. ✅ Say hi to the pretend-money account — `step1_say_hi.py`
2. ✅ Look up a stock price — `step2_look.py`
3. ✅ Buy 1 pretend share — `step3_buy.py`
4. ✅ Sell it back — `step4_sell.py`
5. ✅ "Don't be dumb" safety rules — `safety.py`, `settings.py`, `step5_safety_demo.py`
6. ✅ A simple robot that follows one rule — `robot.py`, `step6_robot.py`
7. ✅ A diary of every move — `diary.py`, `step7_robot.py`, `show_diary.py`
8. ✅ Run by itself + a webpage — `auto_run.py`, `dashboard.py`
9. ✅ The AI brain (advisory only) — `ai_brain.py`, `step9_ai_advisor.py`

## The AI brain

`step9_ai_advisor.py` asks Claude what it would do with each stock (reading
prices + the average signal + recent news) and writes its opinion to the diary.
It does NOT trade — it just gives opinions we can score later.
Costs about a third of a cent per run. Needs `ANTHROPIC_API_KEY` in `.env`.

```
./venv/bin/python step9_ai_advisor.py
```

## Everyday use

Open two terminal windows:

```
# window 1 — let the robot run itself (only trades when market is open)
cd ~/trading-robot && ./venv/bin/python auto_run.py

# window 2 — watch it in your browser
cd ~/trading-robot && ./venv/bin/python dashboard.py
# then open http://localhost:8777
```

Check the diary anytime:
```
./venv/bin/python show_diary.py
./venv/bin/python show_diary.py trades
```

## First-time setup

1. Get free pretend-money keys from Alpaca (see below).
2. Copy `.env.example` to a new file named `.env`.
3. Paste your keys into `.env`.
4. Run step 1:
   ```
   ./venv/bin/python step1_say_hi.py
   ```

## How to get Alpaca keys (free, no money needed)

1. Go to https://alpaca.markets and sign up.
2. After logging in, find the toggle that says **Paper / Live** — set it to **Paper**.
   (Paper = pretend money.)
3. On the Paper account dashboard, find **"API Keys"** and click **Generate**.
4. It shows you a **Key** and a **Secret**. Copy both into your `.env` file.
   The secret is only shown once — if you lose it, just generate new ones.
