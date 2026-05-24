"""Test the Sunlit family coordinator."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sunlit.coordinators.family import SunlitFamilyCoordinator


async def test_family_coordinator_update_success(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
    space_soc_response,
    current_strategy_response,
    charging_box_strategy_response,
):
    """Test successful family data update."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_space_soc.return_value = space_soc_response["content"]
    api_client.fetch_space_current_strategy.return_value = current_strategy_response[
        "content"
    ]
    api_client.get_charging_box_strategy.return_value = charging_box_strategy_response[
        "content"
    ]
    api_client.fetch_space_statistics_static.return_value = {
        "totalYield": 1547.04,
        "totalEarnings": {"earnings": 473.38, "currency": "EUR"},
    }
    api_client.fetch_strategy_device_status.return_value = {
        "batteryLocalModeEnabled": True,
        "aioLocalModeEnabled": False,
        "aioUpsEnabled": False,
        "deviceModel": "BK_215",
    }
    api_client.fetch_tariff_index.return_value = {
        "rabotHasContract": True,
        "rabotHourPriceDTO": {
            "priceInCentPerKwh": -0.2,
            "avgPriceInCentPerKwh": 6.67,
            "highestPriceInCentPerKwh": 15.32,
            "lowestPriceInCentPerKwh": -7.59,
            "priceTag": "CHEAP",
            "hour": 16,
        },
    }

    coordinator = SunlitFamilyCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data is not None
    assert "family" in data
    family_data = data["family"]

    # Check today's metrics from space index
    assert family_data["daily_yield"] == 25.3
    assert family_data["daily_earnings"] == 5.2
    assert family_data["home_power"] == 1234

    # Check battery data
    assert family_data["average_battery_level"] == 85
    assert family_data["total_input_power"] == 500
    assert family_data["total_output_power"] == 0

    # Check SOC limits
    assert family_data["hw_soc_min"] == 10
    assert family_data["hw_soc_max"] == 95

    # Check current strategy
    assert family_data["battery_strategy"] == "SELF_CONSUMPTION"
    assert family_data["battery_full"] == False

    # Check lifetime statistics
    assert family_data["lifetime_yield"] == 1547.04
    assert family_data["lifetime_earnings"] == 473.38

    # Check local-mode / UPS device status
    assert family_data["battery_local_mode_enabled"] is True
    assert family_data["aio_local_mode_enabled"] is False
    assert family_data["aio_ups_enabled"] is False

    # Check dynamic tariff / pricing
    assert family_data["rabot_has_contract"] is True
    assert family_data["electricity_price"] == -0.2
    assert family_data["electricity_price_avg"] == 6.67
    assert family_data["electricity_price_high"] == 15.32
    assert family_data["electricity_price_low"] == -7.59
    assert family_data["electricity_price_tag"] == "CHEAP"

    # Verify API calls
    api_client.fetch_space_index.assert_called_once_with("34038")
    api_client.fetch_space_soc.assert_called_once_with("34038")
    api_client.fetch_space_statistics_static.assert_called_once_with("34038")
    api_client.fetch_tariff_index.assert_called_once_with("34038")
    api_client.fetch_strategy_device_status.assert_called_once_with("34038")
    api_client.fetch_space_current_strategy.assert_called_once_with("34038")
    api_client.get_charging_box_strategy.assert_called_once_with("34038")


async def test_family_coordinator_partial_failure(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
):
    """Test family coordinator handles partial API failures gracefully."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_space_soc.side_effect = Exception("SOC API failed")
    api_client.fetch_space_statistics_static.side_effect = Exception("Stats API failed")
    api_client.fetch_strategy_device_status.side_effect = Exception("Status API failed")
    api_client.fetch_tariff_index.side_effect = Exception("Tariff API failed")
    api_client.fetch_space_current_strategy.side_effect = Exception("Strategy API failed")
    api_client.get_charging_box_strategy.side_effect = Exception("Charging box API failed")

    coordinator = SunlitFamilyCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    # Should not raise, but continue with partial data
    data = await coordinator._async_update_data()

    assert data is not None
    assert "family" in data
    family_data = data["family"]

    # Should have data from space_index
    assert family_data["daily_yield"] == 25.3
    assert family_data["average_battery_level"] == 85
    assert family_data["total_ac_power"] == 1500  # From meter data

    # Should not have SOC, strategy, lifetime-stats, device-status, or tariff data
    assert "hw_soc_min" not in family_data
    assert "battery_strategy" not in family_data
    assert "lifetime_yield" not in family_data
    assert "battery_local_mode_enabled" not in family_data
    assert "electricity_price" not in family_data


async def test_family_coordinator_complete_failure(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test family coordinator handles complete API failure gracefully."""
    api_client = AsyncMock()
    api_client.fetch_space_index.side_effect = Exception("Complete API failure")
    api_client.fetch_device_list.side_effect = Exception("Device list API failed")
    api_client.fetch_space_soc.side_effect = Exception("SOC API failed")
    api_client.fetch_space_statistics_static.side_effect = Exception("Stats API failed")
    api_client.fetch_strategy_device_status.side_effect = Exception("Status API failed")
    api_client.fetch_tariff_index.side_effect = Exception("Tariff API failed")
    api_client.fetch_space_current_strategy.side_effect = Exception("Strategy API failed")
    api_client.get_charging_box_strategy.side_effect = Exception("Charging box API failed")

    coordinator = SunlitFamilyCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    # When all APIs fail, should still return empty family data
    data = await coordinator._async_update_data()
    assert data == {"family": {}}


# Tests for Issue #62 - Negative daily value validation
async def test_family_coordinator_negative_daily_yield_clamped(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_with_negative_yield,
):
    """Test that negative daily yield values are clamped to 0."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_with_negative_yield["content"]
    api_client.fetch_device_list.return_value = []
    api_client.fetch_space_soc.return_value = {
        "hwSbmsLimitedDiscSocMin": 10,
        "hwSbmsLimitedChgSocMax": 95,
    }
    api_client.fetch_space_current_strategy.return_value = {"strategy": "SELF_CONSUMPTION"}
    api_client.get_charging_box_strategy.return_value = {
        "ev3600AutoStrategyMode": "AUTO"
    }

    coordinator = SunlitFamilyCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    family_data = data["family"]

    # Verify negative daily values were clamped to 0
    assert family_data["daily_yield"] == 0.0
    assert family_data["daily_earnings"] == 0.0

    # Verify other values remain correct
    assert family_data["home_power"] == 1234
    assert family_data["average_battery_level"] == 75


async def test_family_coordinator_positive_daily_values_unchanged(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
):
    """Test that positive daily values pass through unchanged."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = []
    api_client.fetch_space_soc.return_value = {
        "hwSbmsLimitedDiscSocMin": 10,
        "hwSbmsLimitedChgSocMax": 95,
    }
    api_client.fetch_space_current_strategy.return_value = {"strategy": "SELF_CONSUMPTION"}
    api_client.get_charging_box_strategy.return_value = {
        "ev3600AutoStrategyMode": "AUTO"
    }

    coordinator = SunlitFamilyCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    family_data = data["family"]

    # Verify positive values unchanged
    assert family_data["daily_yield"] == 25.3
    assert family_data["daily_earnings"] == 5.2
