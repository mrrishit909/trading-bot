"""
Account profiles — lets one codebase run more than one Alpaca paper account
at the same time, each with its own keys, its own diary, and its own settings.

How it works:
  - `auto_run.py --profile <name>` loads that profile's `.env` file, points the
    diary at that profile's database, and runs only the strategies listed.
  - `settings.py` applies the profile's `overrides` on top of the normal values
    (only when ROBOT_PROFILE is set to a non-"main" profile).
  - The dashboard reads ROBOT_PROFILE the same way (see service.sh web / web2).

The "main" profile = the original ~$100k account, unchanged. Do not add
overrides to it.

This file must NOT import settings (settings imports this).
"""

from crypto_universe import SPRINT_CRYPTO
from universe import UNIVERSE

PROFILES = {
    # ---- the original account: ~$100k, all four strategies, untouched ----
    "main": {
        "label": "Main ($100k)",
        "env_file": ".env",
        "diary": "diary.db",
        "run": ["crypto", "stocks", "options", "ai"],
        "port": 8777,
        "overrides": {},
    },

    # ---- the $500 sprint: stocks + crypto only, sized for a small account ----
    # Goal the user set: +$200 in a week. That's ~40% — a long shot. This config
    # concentrates hard (few positions, big slices, loose daily-loss limit) to
    # give it a chance. Most likely outcome is still a sizeable loss.
    "sprint500": {
        "label": "Sprint ($500)",
        "env_file": ".env.sprint500",
        "diary": "diary_sprint500.db",
        "run": ["crypto", "stocks"],          # NO options, NO AI
        "port": 8778,
        "overrides": {
            # stocks — small slices, tight stop (a $500 account can't ride a drawdown)
            "ALLOWED_STOCKS": UNIVERSE,        # the hand-picked 300, not main's ~2000
            "USE_SPY_CASH_SLEEVE": False,      # main-account feature only
            "DOLLARS_PER_BUY": 100,
            "MAX_STOCKS_HELD": 2,
            "MAX_DOLLARS_PER_STOCK": 150,
            "STOCK_STOP_LOSS_PCT": 8,
            "SHORTLIST_SIZE": 6,
            "MAX_TRADES_PER_DAY": 40,
            "DAILY_LOSS_LIMIT": 175,           # ~35% down before it halts for the day

            # crypto — the real engine (only thing that can move ~40% in a week).
            # Hotter coin list (SPRINT_CRYPTO: memecoins + high-beta alts, no BTC/ETH),
            # faster 2/6-day signal (see crypto_scanner.py), near-all-in sizing.
            "TRADE_CRYPTO": True,
            "CRYPTO_UNIVERSE": SPRINT_CRYPTO,
            "CRYPTO_DOLLARS_PER_BUY": 230,
            "MAX_CRYPTO_HELD": 2,
            "MAX_DOLLARS_PER_CRYPTO": 380,
            "CRYPTO_STOP_LOSS_PCT": 20,        # wide — volatile coins wick hard; the
                                              # $175 daily-loss halt is the real backstop
            "MAX_CRYPTO_TRADES_PER_DAY": 30,

            # options off
            "TRADE_OPTIONS": False,
        },
    },
}


def get(name):
    return PROFILES.get(name or "main", PROFILES["main"])
