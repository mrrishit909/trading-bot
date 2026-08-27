# Trading Robot 🤖

We're building a robot that trades stocks with **pretend money** first.
Small steps. One at a time. Nothing scary.

## The steps

1. 🔌 Say hi to the pretend-money account  ← we are here
2. 👀 Look up a stock price
3. 🛒 Buy 1 pretend share
4. 💰 Sell it back
5. 🛡️ Add "don't be dumb" safety rules
6. 🤖 A simple robot that follows one rule
7. 📓 A diary of every move
8. 📊 A webpage to watch it
9. 🧠 The AI brain (much later)

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
