"""
STEP 8 (part 1): Let the robot run by itself.

Wakes up every 30 minutes. Each time:
  - CRYPTO always runs (crypto trades 24/7)      -> step12_crypto.py
  - if the STOCK market is open:
      step10_scan_and_trade.py  - paper-trades stocks
      step11_options.py         - buys calls/puts on fresh crossovers (paper)
      step9_ai_advisor.py       - the AI brain (opinions only), unless --no-ai
All write to diary.db.

Leave this running in a terminal window and the robot takes care of itself.
Press Ctrl+C to stop it.

Run it like this:
    ./venv/bin/python auto_run.py             (loop forever)
    ./venv/bin/python auto_run.py --once       (do one check and stop)
    ./venv/bin/python auto_run.py --no-ai      (skip the AI brain, save pennies)
    ./venv/bin/python auto_run.py --no-crypto  (skip crypto)
"""

import os
import sys
import time
import functools
import subprocess
from datetime import datetime, timezone
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

# Always flush prints right away so messages appear in the right order.
print = functools.partial(print, flush=True)

CHECK_EVERY_MINUTES = 30

load_dotenv()
trading = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)

HERE = os.path.dirname(__file__)
run_once_only = "--once" in sys.argv
skip_ai = "--no-ai" in sys.argv
skip_crypto = "--no-crypto" in sys.argv


def run(script):
    subprocess.run([sys.executable, os.path.join(HERE, script)])


def one_check():
    now = f"{datetime.now(timezone.utc):%H:%M} UTC"

    if not skip_crypto:
        print(f"\n>>> {now}  Running the crypto robot (crypto never closes)...")
        run("step12_crypto.py")

    clock = trading.get_clock()
    if clock.is_open:
        print(f">>> {now}  Stock market is OPEN. Running the stock + options robots...")
        run("step10_scan_and_trade.py")
        run("step11_options.py")
        if not skip_ai:
            print(f">>> {now}  Asking the AI brain for its opinion...")
            run("step9_ai_advisor.py")
    else:
        print(f">>> {now}  Stock market is CLOSED. Next open: "
              f"{clock.next_open:%A %H:%M %Z}. (Crypto still ran.)")


print("Auto-runner started. Ctrl+C to stop.")
one_check()

if not run_once_only:
    try:
        while True:
            time.sleep(CHECK_EVERY_MINUTES * 60)
            one_check()
    except KeyboardInterrupt:
        print("\nStopped. The robot will not run again until you restart this.")
