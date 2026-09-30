"""
The crypto "big list" — coins the robot may trade.

All priced in US dollars. These are the big, liquid ones. Crypto trades
24 hours a day, 7 days a week, so this robot never has to stop.

Crypto is more jumpy than stocks — the safety limits for it are smaller.
"""

CRYPTO_UNIVERSE = [
    "BTC/USD",   # Bitcoin
    "ETH/USD",   # Ethereum
    "SOL/USD",   # Solana
    "LTC/USD",   # Litecoin
    "BCH/USD",   # Bitcoin Cash
    "LINK/USD",  # Chainlink
    "AVAX/USD",  # Avalanche
    "UNI/USD",   # Uniswap
    "AAVE/USD",  # Aave
    "DOGE/USD",  # Dogecoin
]

# A hotter, higher-volatility list used ONLY by the $500 sprint account
# (see profiles.py). No BTC/ETH — too slow to move a small account 40% in a
# week. Memecoins and high-beta alts can run 50-200%... or crater just as fast.
# Every symbol checked tradable on Alpaca paper 2026-08-31.
SPRINT_CRYPTO = [
    "SOL/USD", "AVAX/USD", "LINK/USD", "UNI/USD", "AAVE/USD", "DOGE/USD",
    "XRP/USD", "ADA/USD", "DOT/USD", "ARB/USD", "POL/USD", "CRV/USD",
    "LDO/USD", "FIL/USD", "GRT/USD", "RENDER/USD", "ONDO/USD", "HYPE/USD",
    "WIF/USD", "PEPE/USD", "BONK/USD", "SHIB/USD", "TRUMP/USD", "SUSHI/USD",
]
