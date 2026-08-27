"""
STEP 8 (part 1): Let the robot run by itself.

This wakes the robot up every 30 minutes, but ONLY when the stock market
is actually open. When the market is closed it just waits and tells you
when the market opens next.

Each time it wakes up it runs TWO things:
  1. step10_scan_and_trade.py - scans the big list, really paper-trades the picks
  2. step9_ai_advisor.py      - the AI brain (only gives opinions, never trades)
Both write to diary.db so we can compare them later with compare.py.

Leave this running in a terminal window and the robot takes care of itself.
Press Ctrl+C to stop it.

Run it like this:
    ./venv/bin/python auto_run.py             (loop forever)
    ./venv/bin/python auto_run.py --once       (do one check and stop)
    ./venv/bin/python auto_run.py --no-ai      (skip the AI brain, save pennies)
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


def wake_the_robot():
    print(f"\n>>> {datetime.now(timezone.utc):%H:%M} UTC  Market is OPEN. Waking the robot...")
    subprocess.run([sys.executable, os.path.join(HERE, "step10_scan_and_trade.py")])
    if not skip_ai:
        print(f">>> {datetime.now(timezone.utc):%H:%M} UTC  Asking the AI brain for its opinion...")
        subprocess.run([sys.executable, os.path.join(HERE, "step9_ai_advisor.py")])


def one_check():
    clock = trading.get_clock()
    if clock.is_open:
        wake_the_robot()
    else:
        print(f">>> {datetime.now(timezone.utc):%H:%M} UTC  Market is CLOSED. "
              f"Next open: {clock.next_open:%A %H:%M %Z}. Waiting...")


print("Auto-runner started. Ctrl+C to stop.")
one_check()

if not run_once_only:
    try:
        while True:
            time.sleep(CHECK_EVERY_MINUTES * 60)
            one_check()
    except KeyboardInterrupt:
        print("\nStopped. The robot will not run again until you restart this.")
