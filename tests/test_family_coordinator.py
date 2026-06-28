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
    api_client.fetch_space_statistics_dynamic_energy.return_value = {
        "totalSelfUseRate": 1.0,
        "selfSufficiencyRate": 0.85,
        "totalConsumption": 0,
    }
    api_client.fetch_notification_list.return_value = {
        "content": [
            {
                "id": 1,
                "title": "Older",
                "createDate": 1000,
                "space": {"id": 34038, "name": "Garage"},
            },
            {
                "id": 2,
                "title": "Speicher beginnt das Heizen",
                "content": "Sie müssen nichts tun.",
                "type": "push",
                "deviceSn": "dcbdccbffe3d",
                "read": True,
                "createDate": 2000,
                "space": {"id": 34038, "name": "Garage"},
            },
            {
                "id": 3,
                "title": "Other family",
                "createDate": 3000,
                "space": {"id": 99999, "name": "Test"},
            },
        ]
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

    # Total stored energy (issue #190): avg SOC x batteryCount x 2.15 kWh
    assert family_data["total_stored_energy"] == round(85 / 100 * 1 * 2.15, 3)

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

    # Check energy self-consumption rates (ratios × 100)
    assert family_data["self_use_rate"] == 100.0
    assert family_data["self_sufficiency_rate"] == 85.0

    # Check latest notification (newest for THIS family; other family excluded)
    assert family_data["latest_notification"] == "Speicher beginnt das Heizen"
    detail = family_data["latest_notification_detail"]
    assert detail["id"] == 2
    assert detail["device_sn"] == "dcbdccbffe3d"

    # Verify API calls
    api_client.fetch_space_index.assert_called_once_with("34038")
    api_client.fetch_space_soc.assert_called_once_with("34038")
    api_client.fetch_space_statistics_static.assert_called_once_with("34038")
    api_client.fetch_tariff_index.assert_called_once_with("34038")
    api_client.fetch_space_statistics_dynamic_energy.assert_called_once()
    api_client.fetch_notification_list.assert_called_once()
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
    api_client.fetch_space_statistics_dynamic_energy.side_effect = Exception(
        "Energy API failed"
    )
    api_client.fetch_notification_list.side_effect = Exception("Notif API failed")
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
    assert "self_use_rate" not in family_data
    assert "latest_notification" not in family_data


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
    api_client.fetch_space_statistics_dynamic_energy.side_effect = Exception(
        "Energy API failed"
    )
    api_client.fetch_notification_list.side_effect = Exception("Notif API failed")
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


async def test_family_coordinator_null_heater_status(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """A null heaterStatusList must not crash the coordinator (regression).

    The API can return ``"heaterStatusList": null``; iterating it directly
    raised 'NoneType' object is not iterable and failed the whole family.
    """
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = {
        "battery": {
            "deviceStatus": "Online",
            "batteryLevel": 80,
            "heaterStatusList": None,
        },
    }
    # Keep this test focused on _process_space_index; skip the rest.
    for method in (
        "fetch_device_list",
        "fetch_space_soc",
        "fetch_space_statistics_static",
        "fetch_strategy_device_status",
        "fetch_tariff_index",
        "fetch_space_current_strategy",
        "get_charging_box_strategy",
    ):
        getattr(api_client, method).side_effect = Exception("skip")

    coordinator = SunlitFamilyCoordinator(hass, api_client, "34038", "Test Family")

    # Must not raise UpdateFailed.
    data = await coordinator._async_update_data()

    family_data = data["family"]
    assert family_data["average_battery_level"] == 80
    assert "battery_heater_1" not in family_data


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


async def test_charging_box_strategy_null_booleans_normalized_to_false(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
):
    """Cloud returns explicit ``null`` for uninitialised boolean flags.

    Real-world ``chargingBoxCheckStrategy`` responses include
    ``"tariffStrategyExist": null`` when no tariff strategy has been
    configured yet (see fixtures/api/charging_box_strategy_family_10001.json).
    ``dict.get(key, False)`` returns the cloud's None in that case, which
    surfaces as ``unknown`` in HA instead of ``off``. The coordinator must
    coerce these to a proper ``False`` so the binary sensors report a
    deterministic state.
    """
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = []
    api_client.fetch_space_soc.return_value = {
        "hwSbmsLimitedDiscSocMin": 10,
        "hwSbmsLimitedChgSocMax": 95,
    }
    api_client.fetch_space_current_strategy.return_value = {
        "strategy": "SELF_CONSUMPTION"
    }
    # Mirror the shape of the captured production response: real booleans
    # for most flags, explicit None for the uninitialised tariff flag.
    api_client.get_charging_box_strategy.return_value = {
        "ev3600AutoStrategyExist": False,
        "ev3600AutoStrategyRunning": False,
        "tariffStrategyExist": None,
        "enableLocalSmartStrategy": False,
        "acCoupleEnabled": False,
        "boostOn": False,
    }

    coordinator = SunlitFamilyCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    family_data = data["family"]

    # Every boolean flag must be a real bool — never None.
    for key in (
        "ev3600_auto_strategy_exist",
        "ev3600_auto_strategy_running",
        "tariff_strategy_exist",
        "enable_local_smart_strategy",
        "ac_couple_enabled",
        "charging_box_boost_on",
    ):
        assert family_data[key] is False, (
            f"{key} should be False, got {family_data[key]!r}"
        )
