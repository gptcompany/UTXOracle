"""
Unit tests for Bitcoin Price Power Law Model (spec-034)

Tests for:
- T005: days_since_genesis, fit_power_law, predict_price, zone classification
- T014: Model fitting from database data (User Story 2)
"""

from datetime import date

import numpy as np
import pytest

from scripts.models.price_power_law import (
    DEFAULT_MODEL,
    GENESIS_DATE,
    MIN_SAMPLES_FOR_FIT,
    ZONE_OVERVALUED_THRESHOLD,
    ZONE_UNDERVALUED_THRESHOLD,
    classify_zone,
    days_since_genesis,
    fit_power_law,
    predict_price,
)


class TestDaysSinceGenesis:
    """Tests for days_since_genesis function."""

    def test_known_date(self) -> None:
        """Test with a known date calculation."""
        # 2009-01-04 is 1 day after genesis
        assert days_since_genesis(date(2009, 1, 4)) == 1

    def test_one_year_after_genesis(self) -> None:
        """Test date one year after genesis."""
        # 2010-01-03 is 365 days after genesis
        assert days_since_genesis(date(2010, 1, 3)) == 365

    def test_current_era(self) -> None:
        """Test a date in current era."""
        # 2025-12-25 should be approximately 6200 days
        days = days_since_genesis(date(2025, 12, 25))
        assert 6000 < days < 6400

    def test_genesis_date_raises(self) -> None:
        """Test that genesis date itself raises ValueError."""
        with pytest.raises(ValueError, match="before or on genesis"):
            days_since_genesis(GENESIS_DATE)

    def test_before_genesis_raises(self) -> None:
        """Test that date before genesis raises ValueError."""
        with pytest.raises(ValueError, match="before or on genesis"):
            days_since_genesis(date(2008, 12, 31))


class TestClassifyZone:
    """Tests for zone classification."""

    def test_undervalued_zone(self) -> None:
        """Test undervalued classification (<-20%)."""
        assert classify_zone(-0.25) == "undervalued"
        assert classify_zone(-0.50) == "undervalued"
        assert classify_zone(ZONE_UNDERVALUED_THRESHOLD - 0.01) == "undervalued"

    def test_fair_zone(self) -> None:
        """Test fair value classification (-20% to +50%)."""
        assert classify_zone(0.0) == "fair"
        assert classify_zone(-0.19) == "fair"
        assert classify_zone(0.49) == "fair"
        assert classify_zone(ZONE_UNDERVALUED_THRESHOLD) == "fair"
        assert classify_zone(ZONE_OVERVALUED_THRESHOLD) == "fair"

    def test_overvalued_zone(self) -> None:
        """Test overvalued classification (>+50%)."""
        assert classify_zone(0.51) == "overvalued"
        assert classify_zone(1.0) == "overvalued"
        assert classify_zone(ZONE_OVERVALUED_THRESHOLD + 0.01) == "overvalued"


class TestPredictPrice:
    """Tests for predict_price function."""

    def test_prediction_structure(self) -> None:
        """Test that prediction returns all expected fields."""
        prediction = predict_price(DEFAULT_MODEL, date(2025, 12, 25))

        assert prediction.date == date(2025, 12, 25)
        assert prediction.days_since_genesis > 0
        assert prediction.fair_value > 0
        assert prediction.lower_band > 0
        assert prediction.upper_band > 0
        assert prediction.lower_band < prediction.fair_value < prediction.upper_band

    def test_prediction_with_current_price(self) -> None:
        """Test prediction with current price for zone calculation."""
        prediction = predict_price(
            DEFAULT_MODEL, date(2025, 12, 25), current_price=100000
        )

        assert prediction.current_price == 100000
        assert prediction.deviation_pct is not None
        assert prediction.zone in ["undervalued", "fair", "overvalued"]

    def test_prediction_without_current_price(self) -> None:
        """Test prediction without current price returns unknown zone."""
        prediction = predict_price(DEFAULT_MODEL, date(2025, 12, 25))

        assert prediction.current_price is None
        assert prediction.deviation_pct is None
        assert prediction.zone == "unknown"

    def test_fair_value_increases_over_time(self) -> None:
        """Test that fair value increases with days."""
        pred_early = predict_price(DEFAULT_MODEL, date(2024, 1, 1))
        pred_late = predict_price(DEFAULT_MODEL, date(2025, 12, 25))

        assert pred_late.fair_value > pred_early.fair_value

    def test_bands_symmetry_in_log_space(self) -> None:
        """Test that bands are symmetric in log10 space."""
        prediction = predict_price(DEFAULT_MODEL, date(2025, 12, 25))

        log_fair = np.log10(prediction.fair_value)
        log_lower = np.log10(prediction.lower_band)
        log_upper = np.log10(prediction.upper_band)

        # Difference should be approximately std_error
        assert abs((log_fair - log_lower) - DEFAULT_MODEL.std_error) < 0.001
        assert abs((log_upper - log_fair) - DEFAULT_MODEL.std_error) < 0.001

    def test_prediction_before_genesis_raises(self) -> None:
        """Test that prediction for date before genesis raises."""
        with pytest.raises(ValueError):
            predict_price(DEFAULT_MODEL, date(2008, 1, 1))


class TestFitPowerLaw:
    """Tests for fit_power_law function."""

    def test_insufficient_data_raises(self) -> None:
        """Test that too few data points raises ValueError."""
        # Generate 99 valid dates (less than MIN_SAMPLES_FOR_FIT=365)
        dates = [
            date(2020, 1, 1) + __import__("datetime").timedelta(days=i)
            for i in range(99)
        ]
        prices = [10000.0] * 99

        with pytest.raises(ValueError, match="Insufficient data"):
            fit_power_law(dates, prices)

    def test_length_mismatch_raises(self) -> None:
        """Test that mismatched lengths raises ValueError."""
        # Generate 399 valid dates but only 100 prices
        dates = [
            date(2020, 1, 1) + __import__("datetime").timedelta(days=i)
            for i in range(399)
        ]
        prices = [10000.0] * 100  # Fewer prices than dates

        with pytest.raises(ValueError, match="Length mismatch"):
            fit_power_law(dates, prices)

    def test_fit_with_synthetic_power_law_data(self) -> None:
        """Test fitting with perfect power law data recovers parameters."""
        # Generate synthetic data following power law
        # price = 10^(alpha + beta * log10(days))
        test_alpha = -15.0
        test_beta = 5.0

        dates = []
        prices = []

        for i in range(400):
            d = date(2010 + i // 365, 1 + (i % 12), 1 + (i % 28))
            try:
                days = days_since_genesis(d)
                price = 10 ** (test_alpha + test_beta * np.log10(days))
                dates.append(d)
                prices.append(price)
            except ValueError:
                continue

        if len(dates) >= MIN_SAMPLES_FOR_FIT:
            model = fit_power_law(dates, prices)

            # With perfect data, should recover parameters closely
            assert abs(model.alpha - test_alpha) < 0.5
            assert abs(model.beta - test_beta) < 0.2
            assert model.r_squared > 0.99

    def test_fit_returns_valid_model(self) -> None:
        """Test that fit returns a valid PowerLawModel."""
        # Generate enough data points
        dates = []
        prices = []

        for i in range(400):
            d = date(2015 + i // 365, 1 + (i % 12), 1 + min(28, 1 + (i % 28)))
            price = 1000 * (1 + i * 0.01)  # Increasing prices
            dates.append(d)
            prices.append(price)

        model = fit_power_law(dates, prices)

        assert model.sample_size >= MIN_SAMPLES_FOR_FIT
        assert 0.0 <= model.r_squared <= 1.0
        assert model.std_error > 0
        assert model.fitted_on == max(dates)


class TestDefaultModel:
    """Tests for DEFAULT_MODEL constant."""

    def test_default_model_values(self) -> None:
        """Test default model has expected values."""
        assert DEFAULT_MODEL.alpha == pytest.approx(-17.01)
        assert DEFAULT_MODEL.beta == pytest.approx(5.82)
        assert DEFAULT_MODEL.r_squared == pytest.approx(0.95)
        assert DEFAULT_MODEL.std_error == pytest.approx(0.32)

    def test_default_model_produces_reasonable_prices(self) -> None:
        """Test default model produces reasonable price predictions."""
        # For late 2025, should predict price in tens of thousands
        prediction = predict_price(DEFAULT_MODEL, date(2025, 12, 25))
        assert 10000 < prediction.fair_value < 500000

    def test_default_model_metadata(self) -> None:
        """Test default model has valid metadata."""
        assert DEFAULT_MODEL.sample_size > 0
        assert DEFAULT_MODEL.fitted_on >= date(2024, 1, 1)
