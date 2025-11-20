"""Tests for device coordinator validation logic."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator
from custom_components.sunlit.coordinators.family import SunlitFamilyCoordinator


# Device Daily Energy Validation Tests
async def test_validate_daily_energy_negative_clamped_to_zero(hass: HomeAssistant):
    """Negative values should be clamped to 0.0."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    # Test negative value
    result = coordinator._validate_daily_energy(-5.2, "daily_buy_energy", "meter_001")
    assert result == 0.0

    # Test another negative value
    result = coordinator._validate_daily_energy(-0.01, "daily_ret_energy", "meter_002")
    assert result == 0.0


async def test_validate_daily_energy_positive_unchanged(hass: HomeAssistant):
    """Positive values should pass through unchanged."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    # Test positive value
    result = coordinator._validate_daily_energy(3.5, "daily_buy_energy", "meter_001")
    assert result == 3.5

    # Test large positive value
    result = coordinator._validate_daily_energy(
        123.456, "total_power_generation", "inverter_001"
    )
    assert result == 123.456


async def test_validate_daily_energy_zero_unchanged(hass: HomeAssistant):
    """Zero values should pass through unchanged."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    result = coordinator._validate_daily_energy(0.0, "daily_buy_energy", "meter_001")
    assert result == 0.0


async def test_validate_daily_energy_none_returns_none(hass: HomeAssistant):
    """None values should return None."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    result = coordinator._validate_daily_energy(None, "daily_buy_energy", "meter_001")
    assert result is None


async def test_validate_daily_energy_warning_logged_for_negative(
    hass: HomeAssistant, caplog
):
    """Warning should be logged when negative value detected."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    # Call with negative value
    coordinator._validate_daily_energy(-2.5, "daily_buy_energy", "meter_001")

    # Check that warning was logged
    assert "Negative daily energy value detected" in caplog.text
    assert "daily_buy_energy" in caplog.text
    assert "meter_001" in caplog.text
    assert "-2.5" in caplog.text


# Family Daily Value Validation Tests
async def test_validate_daily_value_negative_clamped_to_zero(hass: HomeAssistant):
    """Negative values should be clamped to 0.0."""
    api_client = AsyncMock()
    coordinator = SunlitFamilyCoordinator(hass, api_client, "test_family", "Test Family")

    # Test negative yield
    result = coordinator._validate_daily_value(-1.5, "daily_yield")
    assert result == 0.0

    # Test negative earnings
    result = coordinator._validate_daily_value(-0.5, "daily_earnings")
    assert result == 0.0


async def test_validate_daily_value_positive_unchanged(hass: HomeAssistant):
    """Positive values should pass through unchanged."""
    api_client = AsyncMock()
    coordinator = SunlitFamilyCoordinator(hass, api_client, "test_family", "Test Family")

    result = coordinator._validate_daily_value(10.5, "daily_yield")
    assert result == 10.5


async def test_validate_daily_value_none_returns_none(hass: HomeAssistant):
    """None values should return None."""
    api_client = AsyncMock()
    coordinator = SunlitFamilyCoordinator(hass, api_client, "test_family", "Test Family")

    result = coordinator._validate_daily_value(None, "daily_yield")
    assert result is None


# Midnight Window Detection Tests - Device Coordinator
@patch("custom_components.sunlit.coordinators.device.datetime")
async def test_device_is_midnight_window_before_midnight(mock_datetime, hass: HomeAssistant):
    """23:50-23:59 should return True."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    # Test 23:50
    mock_now = type("MockDateTime", (), {"hour": 23, "minute": 50})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True

    # Test 23:55
    mock_now = type("MockDateTime", (), {"hour": 23, "minute": 55})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True

    # Test 23:59
    mock_now = type("MockDateTime", (), {"hour": 23, "minute": 59})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True


@patch("custom_components.sunlit.coordinators.device.datetime")
async def test_device_is_midnight_window_after_midnight(mock_datetime, hass: HomeAssistant):
    """00:00-00:10 should return True."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    # Test 00:00
    mock_now = type("MockDateTime", (), {"hour": 0, "minute": 0})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True

    # Test 00:05
    mock_now = type("MockDateTime", (), {"hour": 0, "minute": 5})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True

    # Test 00:10
    mock_now = type("MockDateTime", (), {"hour": 0, "minute": 10})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True


@patch("custom_components.sunlit.coordinators.device.datetime")
async def test_device_is_midnight_window_outside_window(mock_datetime, hass: HomeAssistant):
    """Other times should return False."""
    api_client = AsyncMock()
    coordinator = SunlitDeviceCoordinator(hass, api_client, "test_family", "Test Family")

    # Test 14:30 (afternoon)
    mock_now = type("MockDateTime", (), {"hour": 14, "minute": 30})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is False

    # Test 23:49 (just before window)
    mock_now = type("MockDateTime", (), {"hour": 23, "minute": 49})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is False

    # Test 00:11 (just after window)
    mock_now = type("MockDateTime", (), {"hour": 0, "minute": 11})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is False


# Midnight Window Detection Tests - Family Coordinator
@patch("custom_components.sunlit.coordinators.family.datetime")
async def test_family_is_midnight_window_before_midnight(mock_datetime, hass: HomeAssistant):
    """Family coordinator: 23:50-23:59 should return True."""
    api_client = AsyncMock()
    coordinator = SunlitFamilyCoordinator(hass, api_client, "test_family", "Test Family")

    mock_now = type("MockDateTime", (), {"hour": 23, "minute": 55})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True


@patch("custom_components.sunlit.coordinators.family.datetime")
async def test_family_is_midnight_window_after_midnight(mock_datetime, hass: HomeAssistant):
    """Family coordinator: 00:00-00:10 should return True."""
    api_client = AsyncMock()
    coordinator = SunlitFamilyCoordinator(hass, api_client, "test_family", "Test Family")

    mock_now = type("MockDateTime", (), {"hour": 0, "minute": 5})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is True


@patch("custom_components.sunlit.coordinators.family.datetime")
async def test_family_is_midnight_window_outside_window(mock_datetime, hass: HomeAssistant):
    """Family coordinator: Other times should return False."""
    api_client = AsyncMock()
    coordinator = SunlitFamilyCoordinator(hass, api_client, "test_family", "Test Family")

    mock_now = type("MockDateTime", (), {"hour": 12, "minute": 0})()
    mock_datetime.now.return_value = mock_now
    assert coordinator._is_midnight_window() is False
