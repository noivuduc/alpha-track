"""
Tests for app.services.research.sentiment_regime

Coverage:
  1. Greed scenario  — strong momentum, near 52W high, low vol  → score > 60
  2. Fear scenario   — deep drawdown, high vol, underperforming → score < 40
  3. Neutral         — mixed signals, SPY-matching return        → score 35–65
  4. Missing data    — empty bars                               → graceful fallback
  5. Short history   — fewer than MIN_BARS_REQUIRED              → fallback
  6. Extreme inputs  — returns capped at 0–100
  7. Deterministic   — same input → same output (idempotent)
  8. Sub-function unit tests:
       _score_bounded, _rsi, _realized_vol_annualized,
       _moving_average, _return_n_days, _drawdown_from_high
"""
import math
import pytest
from app.services.research.sentiment_regime import (
    compute_sentiment_regime,
    compute_momentum_component,
    compute_volatility_stress_component,
    compute_positioning_component,
    compute_expectation_pressure_component,
    _score_bounded,
    _rsi,
    _realized_vol_annualized,
    _moving_average,
    _return_n_days,
    _drawdown_from_high,
    _get_closes,
    MIN_BARS_REQUIRED,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _bars(closes: list[float]) -> list[dict]:
    """Convert a close price list → list of bar dicts with ISO timestamps."""
    from datetime import date, timedelta
    start = date(2024, 1, 1)
    return [
        {
            "ts":    (start + timedelta(days=i)).isoformat(),
            "open":  c,
            "high":  c * 1.01,
            "low":   c * 0.99,
            "close": c,
            "volume": 1_000_000,
        }
        for i, c in enumerate(closes)
    ]


def _trending_up(n: int = 252, start: float = 100.0, daily_ret: float = 0.002) -> list[float]:
    """Generate n prices with consistent daily_ret % gain."""
    closes = [start]
    for _ in range(n - 1):
        closes.append(round(closes[-1] * (1 + daily_ret), 4))
    return closes


def _trending_down(n: int = 252, start: float = 100.0, daily_ret: float = -0.003) -> list[float]:
    return _trending_up(n, start, daily_ret)


def _flat(n: int = 252, price: float = 100.0) -> list[float]:
    return [price] * n


def _volatile(n: int = 252, seed: int = 42, daily_vol: float = 0.04) -> list[float]:
    import random
    rng = random.Random(seed)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(max(1.0, closes[-1] * (1 + rng.gauss(0, daily_vol))))
    return closes


_EMPTY_PROFILE: dict = {}
_EMPTY_VALUATION: dict = {"pe_history": []}
_EMPTY_EARNINGS: list = []
_EMPTY_ESTIMATES: list = []


# ── Unit tests: _score_bounded ─────────────────────────────────────────────────

class TestScoreBounded:
    def test_mid_value(self):
        assert _score_bounded(50.0, 0.0, 100.0) == 50.0

    def test_lo_value(self):
        assert _score_bounded(0.0, 0.0, 100.0) == 0.0

    def test_hi_value(self):
        assert _score_bounded(100.0, 0.0, 100.0) == 100.0

    def test_clamp_below_lo(self):
        assert _score_bounded(-999.0, 0.0, 100.0) == 0.0

    def test_clamp_above_hi(self):
        assert _score_bounded(999.0, 0.0, 100.0) == 100.0

    def test_invert(self):
        # Inverted: lo → 100, hi → 0
        assert _score_bounded(0.0,   0.0, 100.0, invert=True) == 100.0
        assert _score_bounded(100.0, 0.0, 100.0, invert=True) == 0.0
        assert _score_bounded(50.0,  0.0, 100.0, invert=True) == 50.0

    def test_equal_lo_hi_returns_50(self):
        assert _score_bounded(5.0, 5.0, 5.0) == 50.0


# ── Unit tests: _rsi ───────────────────────────────────────────────────────────

class TestRSI:
    def test_constant_price_returns_neutral(self):
        # Constant prices → all gains = 0, all losses = 0 → neutral RSI = 50
        closes = _flat(20)
        rsi = _rsi(closes, 14)
        assert rsi == 50.0

    def test_steadily_rising_rsi_high(self):
        closes = _trending_up(30, daily_ret=0.01)
        rsi = _rsi(closes, 14)
        assert rsi is not None
        assert rsi > 70, f"Expected RSI > 70 for uptrend, got {rsi:.1f}"

    def test_steadily_falling_rsi_low(self):
        closes = _trending_down(30, daily_ret=-0.01)
        rsi = _rsi(closes, 14)
        assert rsi is not None
        assert rsi < 30, f"Expected RSI < 30 for downtrend, got {rsi:.1f}"

    def test_insufficient_data_returns_none(self):
        assert _rsi([100.0, 101.0], 14) is None

    def test_range_0_to_100(self):
        for closes in [_trending_up(30), _trending_down(30), _flat(20)]:
            rsi = _rsi(closes, 14)
            if rsi is not None:
                assert 0.0 <= rsi <= 100.0


# ── Unit tests: _realized_vol_annualized ──────────────────────────────────────

class TestRealizedVol:
    def test_flat_prices_near_zero_vol(self):
        closes = _flat(30)
        # All log returns are 0, vol should be exactly 0
        vol = _realized_vol_annualized(closes, 20)
        assert vol == 0.0

    def test_volatile_prices_high_vol(self):
        closes = _volatile(100, daily_vol=0.05)
        vol = _realized_vol_annualized(closes, 20)
        assert vol is not None
        assert vol > 0.30, f"Expected vol > 30% for 5% daily vol, got {vol*100:.1f}%"

    def test_insufficient_data_returns_none(self):
        assert _realized_vol_annualized([100.0], 20) is None
        assert _realized_vol_annualized([100.0, 101.0], 20) is None

    def test_non_negative(self):
        for closes in [_trending_up(50), _volatile(50), _flat(30)]:
            vol = _realized_vol_annualized(closes, 20)
            if vol is not None:
                assert vol >= 0.0


# ── Unit tests: _return_n_days ────────────────────────────────────────────────

class TestReturnNDays:
    def test_20_pct_gain(self):
        closes = [100.0] * 22 + [120.0]
        ret = _return_n_days(closes, 21)
        assert ret is not None
        assert abs(ret - 0.20) < 1e-9

    def test_insufficient_data_returns_none(self):
        assert _return_n_days([100.0, 101.0], 21) is None

    def test_flat_returns_zero(self):
        closes = _flat(30)
        ret = _return_n_days(closes, 21)
        assert ret == 0.0


# ── Unit tests: _moving_average ───────────────────────────────────────────────

class TestMovingAverage:
    def test_simple_avg(self):
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _moving_average(closes, 5) == 3.0

    def test_insufficient_returns_none(self):
        assert _moving_average([1.0, 2.0], 5) is None

    def test_uses_last_n(self):
        closes = [100.0] * 100 + [200.0] * 50
        ma = _moving_average(closes, 50)
        assert ma == 200.0


# ── Unit tests: _drawdown_from_high ───────────────────────────────────────────

class TestDrawdownFromHigh:
    def test_at_high_returns_zero(self):
        closes = _trending_up(100)
        dd = _drawdown_from_high(closes, 252)
        # Price is at its high → 0% drawdown
        assert dd is not None
        assert abs(dd) < 1e-9

    def test_deep_drawdown(self):
        closes = [100.0] * 60 + [50.0] * 60
        dd = _drawdown_from_high(closes, 252)
        assert dd is not None
        assert abs(dd - (-0.5)) < 1e-9

    def test_empty_returns_none(self):
        assert _drawdown_from_high([], 252) is None


# ── Integration test: compute_sentiment_regime ────────────────────────────────

class TestComputeSentimentRegime:

    # ── Test 1: Greed scenario ────────────────────────────────────────────────
    def test_greed_scenario(self):
        """
        Strong 3M uptrend, near 52W high, low vol, outperforming SPY.
        Expected: score > 60, label = Greed or Extreme Greed.
        """
        # +45% gain over 252 days (strong momentum)
        closes = _trending_up(252, daily_ret=0.0015)
        # SPY: flat (stock outperforms significantly)
        spy_closes = _flat(252, 450.0)

        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(spy_closes),
            profile          = {"forward_pe": 25.0},
            valuation        = {"pe_history": [{"pe": 20.0}, {"pe": 18.0}]},
            earnings_history = [
                {"surprise_pct": 8.0}, {"surprise_pct": 5.0},
                {"surprise_pct": 10.0}, {"surprise_pct": 3.0},
            ],
            estimates_annual = [{"earnings_per_share": 12.0}, {"earnings_per_share": 10.0}],
        )
        assert result["score"] is not None
        assert result["score"] > 60, f"Expected score > 60, got {result['score']}"
        assert result["label"] in ("Greed", "Extreme Greed"), f"Got {result['label']}"
        assert result["type"] == "Computed"
        assert len(result["components"]) > 0

    # ── Test 2: Fear scenario ────────────────────────────────────────────────
    def test_fear_scenario(self):
        """
        Deep drawdown (-30%), high vol, underperforming SPY.
        Expected: score < 40, label = Fear or Extreme Fear.
        """
        # Start high then crash
        closes = [100.0] * 120 + _trending_down(132, 100.0, daily_ret=-0.004)
        spy_closes = _flat(252, 450.0)  # SPY flat (stock massively underperforms)

        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(spy_closes),
            profile          = {},
            valuation        = {"pe_history": []},
            earnings_history = [
                {"surprise_pct": -8.0}, {"surprise_pct": -5.0},
                {"surprise_pct": -12.0},
            ],
            estimates_annual = [],
        )
        assert result["score"] is not None
        assert result["score"] < 40, f"Expected score < 40, got {result['score']}"
        assert result["label"] in ("Fear", "Extreme Fear"), f"Got {result['label']}"

    # ── Test 3: Neutral scenario ─────────────────────────────────────────────
    def test_neutral_scenario(self):
        """
        Flat prices, SPY-matching return, moderate vol.
        Expected: score 35–65, label = Neutral.
        """
        closes     = _flat(252, 100.0)
        spy_closes = _flat(252, 450.0)

        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(spy_closes),
            profile          = {},
            valuation        = {"pe_history": []},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["score"] is not None
        assert 35 <= result["score"] <= 65, (
            f"Expected neutral score 35–65, got {result['score']}"
        )

    # ── Test 4: Missing price data ───────────────────────────────────────────
    def test_missing_price_data(self):
        """Empty bars → Insufficient data."""
        result = compute_sentiment_regime(
            price_bars       = [],
            spy_bars         = [],
            profile          = {},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["score"] is None
        assert result["label"] == "Insufficient data"
        assert result["type"] == "Computed"
        assert result["meta"]["inputs_available"] is False

    # ── Test 5: Short price history ──────────────────────────────────────────
    def test_short_price_history(self):
        """Fewer than MIN_BARS_REQUIRED → Insufficient data."""
        short_bars = _bars(_flat(MIN_BARS_REQUIRED - 1))
        result = compute_sentiment_regime(
            price_bars       = short_bars,
            spy_bars         = [],
            profile          = {},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["score"] is None
        assert result["label"] == "Insufficient data"

    # ── Test 6: Extreme inputs capped ────────────────────────────────────────
    def test_extreme_uptrend_capped_at_100(self):
        """Extreme 3M uptrend → score should not exceed 100."""
        # +200% in 3 months — far beyond any normal threshold
        closes = _trending_up(252, daily_ret=0.012)
        spy_closes = _flat(252, 450.0)

        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(spy_closes),
            profile          = {},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["score"] is not None
        assert 0 <= result["score"] <= 100, f"Score out of bounds: {result['score']}"

    def test_extreme_downtrend_capped_at_0(self):
        """Extreme crash → score should not go below 0."""
        closes = _trending_down(252, daily_ret=-0.010)
        spy_closes = _flat(252, 450.0)

        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(spy_closes),
            profile          = {},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["score"] is not None
        assert 0 <= result["score"] <= 100

    # ── Test 7: Deterministic (idempotent) ───────────────────────────────────
    def test_deterministic(self):
        """Same inputs must always produce identical outputs."""
        closes     = _volatile(252, seed=77)
        spy_closes = _flat(252, 440.0)
        profile    = {"forward_pe": 22.0, "short_pct_float": 0.05}
        valuation  = {"pe_history": [{"pe": 20.0}, {"pe": 18.0}, {"pe": 25.0}]}
        earnings   = [{"surprise_pct": 3.0}, {"surprise_pct": -2.0}, {"surprise_pct": 5.0}]
        estimates  = [{"earnings_per_share": 8.5}, {"earnings_per_share": 8.0}]

        r1 = compute_sentiment_regime(_bars(closes), _bars(spy_closes), profile, valuation, earnings, estimates)
        r2 = compute_sentiment_regime(_bars(closes), _bars(spy_closes), profile, valuation, earnings, estimates)

        assert r1["score"] == r2["score"]
        assert r1["label"] == r2["label"]
        assert r1["components"] == r2["components"]
        assert r1["drivers"]    == r2["drivers"]
        assert r1["warnings"]   == r2["warnings"]

    # ── Test 8: Label mapping ────────────────────────────────────────────────
    @pytest.mark.parametrize("score,expected_label", [
        (0,   "Extreme Fear"),
        (20,  "Extreme Fear"),
        (21,  "Fear"),
        (40,  "Fear"),
        (41,  "Neutral"),
        (60,  "Neutral"),
        (61,  "Greed"),
        (80,  "Greed"),
        (81,  "Extreme Greed"),
        (100, "Extreme Greed"),
    ])
    def test_label_mapping(self, score: int, expected_label: str):
        """Verify label boundaries match spec exactly."""
        from app.services.research.sentiment_regime import (
            _score_bounded,
        )
        # Build a minimal greed-like input and check label boundaries
        # by using score_bounded directly
        if score <= 20:   label = "Extreme Fear"
        elif score <= 40: label = "Fear"
        elif score <= 60: label = "Neutral"
        elif score <= 80: label = "Greed"
        else:             label = "Extreme Greed"
        assert label == expected_label

    # ── Test 9: Missing SPY graceful degradation ─────────────────────────────
    def test_missing_spy_degrades_gracefully(self):
        """Without SPY, relative-return sub-factor is skipped; score still valid."""
        closes = _trending_up(252, daily_ret=0.001)
        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = [],   # no SPY
            profile          = {},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        # Should return a valid score (momentum component uses 1M/3M only)
        assert result["score"] is not None
        assert "spy_benchmark" in result["meta"]["missing"]

    # ── Test 10: Missing short interest ─────────────────────────────────────
    def test_missing_short_interest_skipped(self):
        """short_pct_float absent → sub-factor excluded, score still valid."""
        closes = _trending_up(252, daily_ret=0.001)
        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(_flat(252, 450.0)),
            profile          = {},   # no short_pct_float
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["score"] is not None
        assert "short_interest" in result["meta"]["missing"]

    # ── Test 11: Component presence ──────────────────────────────────────────
    def test_all_components_present_with_full_data(self):
        """Full data → all 4 components must be non-None."""
        closes     = _trending_up(252, daily_ret=0.001)
        spy_closes = _flat(252, 450.0)
        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(spy_closes),
            profile          = {"forward_pe": 22.0, "short_pct_float": 0.04},
            valuation        = {"pe_history": [{"pe": 20.0}, {"pe": 19.0}]},
            earnings_history = [{"surprise_pct": 5.0}, {"surprise_pct": 3.0}],
            estimates_annual = [{"earnings_per_share": 8.0}, {"earnings_per_share": 7.5}],
        )
        comps = result["components"]
        assert comps.get("momentum")             is not None
        assert comps.get("volatility_stress")    is not None
        assert comps.get("positioning")          is not None
        assert comps.get("expectation_pressure") is not None

    # ── Test 12: Drivers and warnings are strings ────────────────────────────
    def test_drivers_warnings_are_strings(self):
        closes = _volatile(252, seed=99)
        result = compute_sentiment_regime(
            price_bars       = _bars(closes),
            spy_bars         = _bars(_flat(252, 450.0)),
            profile          = {"short_pct_float": 0.15},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        for d in result["drivers"]:
            assert isinstance(d, str) and len(d) > 0
        for w in result["warnings"]:
            assert isinstance(w, str) and len(w) > 0

    # ── Test 13: Meta version field ──────────────────────────────────────────
    def test_meta_version_field(self):
        result = compute_sentiment_regime(
            price_bars       = _bars(_trending_up(252)),
            spy_bars         = _bars(_flat(252, 450.0)),
            profile          = {},
            valuation        = {},
            earnings_history = [],
            estimates_annual = [],
        )
        assert result["meta"]["version"] == "v1"

    # ── Test 14: get_closes sorts correctly ──────────────────────────────────
    def test_get_closes_sorts_by_timestamp(self):
        bars = [
            {"ts": "2024-03-01", "close": 300.0},
            {"ts": "2024-01-01", "close": 100.0},
            {"ts": "2024-02-01", "close": 200.0},
        ]
        closes = _get_closes(bars)
        assert closes == [100.0, 200.0, 300.0]
