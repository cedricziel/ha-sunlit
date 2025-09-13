"""Test the Sunlit data coordinator."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sunlit import SunlitDataUpdateCoordinator
from custom_components.sunlit.const import DEFAULT_SCAN_INTERVAL, DOMAIN


async def test_coordinator_update_success(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    space_index_response,
    space_soc_response,
    current_strategy_response,
    strategy_history_response,
    device_statistics_response,
    battery_io_power_response,
    charging_box_strategy_response,
):
    """Test successful data update from coordinator."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.return_value = space_soc_response["content"]
    api_client.fetch_current_strategy.return_value = current_strategy_response[
        "content"
    ]
    api_client.fetch_space_current_strategy.return_value = current_strategy_response[
        "content"
    ]
    api_client.fetch_space_strategy_history.return_value = strategy_history_response[
        "content"
    ]
    api_client.fetch_device_statistics.return_value = device_statistics_response[
        "content"
    ]
    api_client.fetch_battery_io_power.return_value = battery_io_power_response[
        "content"
    ]
    api_client.get_charging_box_strategy.return_value = charging_box_strategy_response[
        "content"
    ]

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    # Initial update
    data = await coordinator._async_update_data()

    assert data is not None
    assert "family" in data
    assert "devices" in data

    # Check family data
    family_data = data["family"]
    assert family_data["device_count"] == 3
    assert family_data["online_devices"] == 3
    assert family_data["offline_devices"] == 0
    assert family_data["total_ac_power"] == 1500
    assert family_data["average_battery_level"] == 85
    assert family_data["battery_strategy"] == "SELF_CONSUMPTION"
    assert family_data["hw_soc_min"] == 10
    assert family_data["hw_soc_max"] == 95

    # Check device data
    devices = data["devices"]
    assert "meter_001" in devices
    assert "inverter_001" in devices
    assert "battery_001" in devices

    # Verify API calls
    api_client.fetch_space_index.assert_called_once_with("34038")
    api_client.fetch_space_soc.assert_called_once_with("34038")
    api_client.fetch_space_current_strategy.assert_called_once_with("34038")
    # fetch_device_statistics is called for all online devices
    assert api_client.fetch_device_statistics.call_count == 3
    api_client.fetch_device_statistics.assert_any_call("meter_001")
    api_client.fetch_device_statistics.assert_any_call("inverter_001")
    api_client.fetch_device_statistics.assert_any_call("battery_001")


async def test_coordinator_update_partial_failure(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
    device_statistics_response,
):
    """Test coordinator handles partial API failures gracefully."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.side_effect = Exception("SOC API failed")
    api_client.fetch_current_strategy.side_effect = Exception("Strategy API failed")
    api_client.fetch_space_current_strategy.side_effect = Exception("Strategy API failed")
    api_client.fetch_space_strategy_history.side_effect = Exception(
        "History API failed"
    )
    api_client.get_charging_box_strategy.side_effect = Exception(
        "Charging box API failed"
    )
    # Mock fetch_device_statistics to return valid data
    api_client.fetch_device_statistics.return_value = device_statistics_response["content"]

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    # Should not raise, but continue with partial data
    data = await coordinator._async_update_data()

    assert data is not None
    assert "family" in data
    assert "devices" in data

    # Should have device data from space_index
    assert data["family"]["device_count"] == 3
    assert len(data["devices"]) == 3


async def test_coordinator_battery_module_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
    device_statistics_response,
):
    """Test creation of virtual battery module devices."""
    api_client = AsyncMock()

    # Modify space_index to have a battery device
    space_index_response["content"]["deviceList"] = [
        {
            "deviceId": "battery_001",
            "deviceName": "Energy Storage",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "status": "Online",
            "batteryLevel": 85,
        }
    ]

    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.return_value = {}
    api_client.fetch_current_strategy.return_value = {}
    api_client.fetch_space_current_strategy.return_value = {}
    api_client.fetch_space_strategy_history.return_value = []
    api_client.fetch_device_statistics.return_value = device_statistics_response[
        "content"
    ]
    api_client.fetch_battery_io_power.return_value = {}
    api_client.get_charging_box_strategy.return_value = {}

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    data = await coordinator._async_update_data()

    # Check that battery device has module data
    devices = data["devices"]
    assert "battery_001" in devices

    # Check battery has module SOC data from statistics
    battery = devices["battery_001"]
    assert battery["battery1Soc"] == 84
    assert battery["battery2Soc"] == 86
    assert battery["battery1Mppt1InVol"] == 398.2
    assert battery["battery1Mppt1InPower"] == 2190.1


async def test_coordinator_solar_energy_aggregation(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
):
    """Test solar energy aggregation across inverters."""
    api_client = AsyncMock()

    # Add multiple inverters
    space_index_response["content"]["deviceList"] = [
        {
            "deviceId": "inverter_001",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "status": "Online",
            "currentPower": 1500,
            "totalPowerGeneration": 1000.0,
        },
        {
            "deviceId": "inverter_002",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "status": "Online",
            "currentPower": 2000,
            "totalPowerGeneration": 1500.0,
        },
    ]

    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.return_value = {}
    api_client.fetch_current_strategy.return_value = {}
    api_client.fetch_space_current_strategy.return_value = {}
    api_client.fetch_space_strategy_history.return_value = []
    api_client.get_charging_box_strategy.return_value = {}
    api_client.fetch_device_statistics.return_value = {}

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    data = await coordinator._async_update_data()

    family_data = data["family"]
    assert family_data["total_solar_power"] == 3500  # 1500 + 2000
    assert family_data["total_solar_energy"] == 2500.0  # 1000 + 1500


async def test_coordinator_update_interval(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
):
    """Test coordinator update interval is correct."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.return_value = {}
    api_client.fetch_current_strategy.return_value = {}
    api_client.fetch_space_current_strategy.return_value = {}
    api_client.fetch_space_strategy_history.return_value = []
    api_client.get_charging_box_strategy.return_value = {}
    api_client.fetch_device_statistics.return_value = {}

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    assert coordinator.update_interval == DEFAULT_SCAN_INTERVAL
    assert coordinator.update_interval == timedelta(seconds=30)


async def test_coordinator_error_handling(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test coordinator error handling when all APIs fail."""
    api_client = AsyncMock()
    api_client.fetch_space_index.side_effect = Exception("Complete API failure")
    api_client.fetch_device_list.side_effect = Exception("Fallback also failed")

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    # Should raise UpdateFailed when calling _async_update_data
    from homeassistant.helpers.update_coordinator import UpdateFailed
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_strategy_history_processing(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
    strategy_history_response,
    device_statistics_response,
):
    """Test strategy history processing."""
    api_client = AsyncMock()
    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.return_value = {}
    api_client.fetch_current_strategy.return_value = {}
    api_client.fetch_space_current_strategy.return_value = {}
    # The API client returns response["content"], which has its own "content" field
    api_client.fetch_space_strategy_history.return_value = strategy_history_response["content"]
    api_client.get_charging_box_strategy.return_value = {}
    # Mock fetch_device_statistics for online devices
    api_client.fetch_device_statistics.return_value = device_statistics_response["content"]

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    data = await coordinator._async_update_data()

    family_data = data["family"]
    assert family_data["last_strategy_type"] == "SELF_CONSUMPTION"
    assert family_data["last_strategy_status"] == "ACTIVE"
    assert family_data["strategy_changes_today"] == 2

    # Verify last_strategy_change is present and is a valid timestamp
    assert "last_strategy_change" in family_data
    timestamp = family_data["last_strategy_change"]
    assert isinstance(timestamp, (int, float)), f"Expected numeric timestamp, got {type(timestamp)}"
    # Timestamp should be within last 24 hours (checking it's reasonable)
    from datetime import datetime
    now = datetime.now()
    timestamp_seconds = timestamp / 1000  # Convert from ms to seconds
    time_diff = now.timestamp() - timestamp_seconds
    assert 0 < time_diff < 86400, f"Timestamp should be within last 24 hours, but diff is {time_diff} seconds"


async def test_coordinator_grid_export_tracking(
    hass: HomeAssistant,
    enable_custom_integrations,
    space_index_response,
):
    """Test grid export energy tracking."""
    api_client = AsyncMock()

    # Add meter with export data
    space_index_response["content"]["deviceList"] = [
        {
            "deviceId": "meter_001",
            "deviceType": "SHELLY_3EM_METER",
            "status": "Online",
            "dailyRetEnergy": 10.5,
            "totalRetEnergy": 1234.5,
        },
        {
            "deviceId": "meter_002",
            "deviceType": "SHELLY_PRO3EM_METER",
            "status": "Online",
            "dailyRetEnergy": 5.3,
            "totalRetEnergy": 567.8,
        },
    ]

    api_client.fetch_space_index.return_value = space_index_response["content"]
    api_client.fetch_device_list.return_value = space_index_response["content"].get("deviceList", [])
    api_client.fetch_space_soc.return_value = {}
    api_client.fetch_current_strategy.return_value = {}
    api_client.fetch_space_current_strategy.return_value = {}
    api_client.fetch_space_strategy_history.return_value = []
    api_client.get_charging_box_strategy.return_value = {}
    api_client.fetch_device_statistics.return_value = {}

    coordinator = SunlitDataUpdateCoordinator(
        hass,
        api_client,
        "34038",
        "Garage",
    )

    data = await coordinator._async_update_data()

    family_data = data["family"]
    assert family_data["daily_grid_export_energy"] == 15.8  # 10.5 + 5.3
    assert family_data["total_grid_export_energy"] == 1802.3  # 1234.5 + 567.8
