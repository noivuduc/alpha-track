"""
Global constants for the portfolio analytics engine.
"""

# Risk-free rate
RF_ANNUAL  = 0.02
RF_DAILY   = RF_ANNUAL / 252

# Annualisation
TRADING_YR = 252

# Calendar labels
MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Common rolling window sizes (trading days)
WINDOW_1W = 5
WINDOW_1M = 21
WINDOW_3M = 63
WINDOW_6M = 126
WINDOW_1Y = 252
