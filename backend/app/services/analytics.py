"""
Compatibility shim — all analytics logic lives in portfolio_analytics/.

This module re-exports every public symbol so that existing import statements
of the form `from app.services import analytics as A` continue to work
without modification.
"""
# noqa: F401, F403
from app.services.portfolio_analytics import (
    compute_engine,
    build_portfolio_returns,
    align_series,
    build_price_lookup,
    compute_position_summary,
    RF_ANNUAL,
    RF_DAILY,
    TRADING_YR,
    MONTHS,
)
from app.services.portfolio_analytics.return_series import (
    daily_returns,
    cumulative_series,
    annualized_return,
    annualized_vol,
)
from app.services.portfolio_analytics.math_utils import mean as _mean, std as _std, pct_change as _pct_change
from app.services.portfolio_analytics.risk_metrics import (
    sharpe,
    sortino,
    max_drawdown,
    beta,
    alpha,
    calmar,
    win_rate,
    information_ratio,
    value_at_risk,
    pearson_corr,
    compute_downside_risk,
)
from app.services.portfolio_analytics.rolling_metrics import (
    compute_rolling_returns,
    compute_rolling_risk_metrics,
    compute_rolling_correlation,
    compute_volatility_regime,
    compute_rolling_max_drawdown,
)
from app.services.portfolio_analytics.contribution import compute_contribution
from app.services.portfolio_analytics.positions import compute_position_analytics
from app.services.portfolio_analytics.performance import (
    performance_series,
    monthly_returns,
    drawdown_series,
    compute_growth_of_100,
    compute_return_distribution,
    compute_derived_metrics,
)
from app.services.portfolio_analytics.exposure import (
    compute_exposure_metrics,
    compute_capture_ratios,
    compute_turnover_pct,
)
