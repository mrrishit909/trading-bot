"""
STEP 8 (part 1): Let the robot run by itself.

Wakes up every 30 minutes. Each time:
  - CRYPTO always runs (crypto trades 24/7)      -> step12_crypto.py
  - if the STOCK market is open:
      step10_scan_and_trade.py  - paper-trades stocks
      step11_options.py         - buys calls/puts on fresh crossovers (paper)
      step9_ai_advisor.py       - the AI brain (opinions only), unless --no-ai

Run it like this:
    ./venv/bin/python auto_run.py                    (loop forever, main account)
    ./venv/bin/python auto_run.py --once             (one check, then stop)
    ./venv/bin/python auto_run.py --no-ai            (skip the AI brain)
    ./venv/bin/python auto_run.py --no-crypto        (skip crypto)
    ./venv/bin/python auto_run.py --profile sprint500 (run the $500 account instead)

Each --profile has its own keys, its own diary, and its own strategy list
(see profiles.py). Without --profile it's the original ~$100k account.
"""

import os
import sys
import time
import functools
import subprocess
from datetime import datetime, timezone
from dotenv import dotenv_values
from alpaca.trading.client import TradingClient

import profiles

print = functools.partial(print, flush=True)

CHECK_EVERY_MINUTES = 30
HERE = os.path.dirname(os.path.abspath(__file__))

run_once_only = "--once" in sys.argv
skip_ai = "--no-ai" in sys.argv
skip_crypto = "--no-crypto" in sys.argv

profile_name = "main"
if "--profile" in sys.argv:
    profile_name = sys.argv[sys.argv.index("--profile") + 1]
PROFILE = profiles.get(profile_name)

# ---- build the environment every child script will run with -------------
env_file = os.path.join(HERE, PROFILE["env_file"])
keys = dotenv_values(env_file)
CHILD_ENV = {**os.environ, **{k: v for k, v in keys.items() if v}}
CHILD_ENV["ROBOT_PROFILE"] = profile_name
CHILD_ENV["ROBOT_DIARY_PATH"] = os.path.join(HERE, PROFILE["diary"])

trading = TradingClient(keys.get("ALPACA_API_KEY"), keys.get("ALPACA_SECRET_KEY"), paper=True)

WANT = set(PROFILE["run"])
if skip_ai:
    WANT.discard("ai")
if skip_crypto:
    WANT.discard("crypto")
if "ai" in WANT:
    import settings as _s
    if not getattr(_s, "AI_ADVISOR_ENABLED", True):
        WANT.discard("ai")

STEP = {
    "crypto": "step12_crypto.py",
    "stocks": "step10_scan_and_trade.py",
    "options": "step11_options.py",
    "ai": "step9_ai_advisor.py",
}


def run(script):
    subprocess.run([sys.executable, os.path.join(HERE, script)], env=CHILD_ENV)


def one_check():
    now = f"{datetime.now(timezone.utc):%H:%M} UTC"
    tag = f"[{profile_name}]"

    if "crypto" in WANT:
        print(f"\n>>> {now} {tag}  Running the crypto robot (crypto never closes)...")
        run(STEP["crypto"])

    market_steps = [s for s in ("stocks", "options", "ai") if s in WANT]
    if not market_steps:
        return

    clock = trading.get_clock()
    if clock.is_open:
        print(f">>> {now} {tag}  Stock market is OPEN. Running: {', '.join(market_steps)}")
        for s in market_steps:
            run(STEP[s])
    else:
        print(f">>> {now} {tag}  Stock market is CLOSED. Next open: "
              f"{clock.next_open:%A %H:%M %Z}. (Crypto still ran.)")

    # keep the diary honest: fix any fill that Alpaca recorded but a step script
    # missed (confirmation lag). Cheap — one orders API call. Never fatal.
    try:
        run("reconcile.py")
    except Exception as e:
        print(f"    (reconcile skipped: {str(e)[:100]})")

    # keep the public read-only snapshot in step with the live account (main only --
    # it's the one shown locally at :8777 and the one people are meant to see)
    if profile_name == "main":
        try:
            run("publish_dashboard.py")
        except Exception as e:
            print(f"    (dashboard publish skipped: {str(e)[:100]})")


print(f"Auto-runner started for profile '{profile_name}' ({PROFILE['label']}). "
      f"Strategies: {', '.join(sorted(WANT))}. Ctrl+C to stop.")
one_check()

if not run_once_only:
    try:
        while True:
            time.sleep(CHECK_EVERY_MINUTES * 60)
            one_check()
    except KeyboardInterrupt:
        print("\nStopped. The robot will not run again until you restart this.")
