"""
Global constants for the portfolio analytics engine.

RF_ANNUAL is read from app.config.Settings.RISK_FREE_RATE so it can be
overridden via the RISK_FREE_RATE environment variable without code changes.
Falls back to 0.02 (2 %) when the settings module is unavailable (e.g. in
isolated unit tests that don't initialise the full application).
"""

# Risk-free rate — configurable via RISK_FREE_RATE env var
RF_ANNUAL: float = 0.02  # default
try:
    from app.config import get_settings as _get_settings  # type: ignore[import]
    RF_ANNUAL = _get_settings().RISK_FREE_RATE
except Exception:
    pass  # keep default when running outside full app context

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
