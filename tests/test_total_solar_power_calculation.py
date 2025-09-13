"""Test that total_solar_power correctly sums all solar inputs."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator


@pytest.mark.asyncio
async def test_total_solar_power_includes_all_sources():
    """Test that total_solar_power includes inverter + battery MPPT + module MPPT power."""

    # Create mock hass
    hass = MagicMock()

    # Create mock API client
    api_client = MagicMock()

    # Mock device list with inverter and battery with modules
    api_client.fetch_device_list = AsyncMock(return_value=[
        {
            "deviceId": "inv_001",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "status": "Online",
            "today": {
                "currentPower": 1500,  # Inverter producing 1500W
                "totalPowerGeneration": 100
            }
        },
        {
            "deviceId": "bat_001",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "status": "Online",
            "batteryLevel": 75,
            "deviceCount": 3,  # Has 3 modules
        }
    ])

    # Mock device statistics for battery with MPPT inputs
    battery_stats = {
        "batterySoc": 75,
        "inputPowerTotal": 2800,  # Total input to battery
        "outputPowerTotal": 500,   # Battery output (should NOT be in solar total)
        "batteryMppt1InPower": 800,   # Main battery MPPT1: 800W solar
        "batteryMppt2InPower": 600,   # Main battery MPPT2: 600W solar
        "battery1Mppt1InPower": 500,  # Module 1 MPPT: 500W solar
        "battery2Mppt1InPower": 400,  # Module 2 MPPT: 400W solar
        "battery3Mppt1InPower": 300,  # Module 3 MPPT: 300W solar
    }

    # Mock fetch_device_statistics to return different data per device
    def mock_fetch_stats(device_id):
        if device_id == "bat_001":
            return AsyncMock(return_value=battery_stats)()
        return AsyncMock(return_value={})()

    api_client.fetch_device_statistics = mock_fetch_stats

    # Create coordinator
    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client=api_client,
        family_id="test_family",
        family_name="Test Family",
    )

    # Update data
    data = await coordinator._async_update_data()

    # Verify aggregates
    aggregates = data["aggregates"]

    # Total solar power should be:
    # Inverter: 1500W
    # Battery MPPT1: 800W
    # Battery MPPT2: 600W
    # Module 1 MPPT: 500W
    # Module 2 MPPT: 400W
    # Module 3 MPPT: 300W
    # Total: 4100W
    expected_total = 1500 + 800 + 600 + 500 + 400 + 300

    assert aggregates["total_solar_power"] == expected_total, \
        f"Expected total solar power to be {expected_total}W, got {aggregates['total_solar_power']}W"

    # Verify battery output power is NOT included in solar total
    assert aggregates["total_solar_power"] != expected_total + 500, \
        "Battery output power should NOT be included in total solar power"

    # Verify individual device data
    battery_data = data["devices"]["bat_001"]
    assert battery_data["batteryMppt1InPower"] == 800
    assert battery_data["batteryMppt2InPower"] == 600
    assert battery_data["battery1Mppt1InPower"] == 500
    assert battery_data["battery2Mppt1InPower"] == 400
    assert battery_data["battery3Mppt1InPower"] == 300
    assert battery_data["output_power_total"] == 500  # This should NOT be in solar total


@pytest.mark.asyncio
async def test_total_solar_power_without_battery_mppt():
    """Test total_solar_power with only inverters (no battery MPPT)."""

    hass = MagicMock()
    api_client = MagicMock()

    # Only inverters, no batteries
    api_client.fetch_device_list = AsyncMock(return_value=[
        {
            "deviceId": "inv_001",
            "deviceType": "SOLAR_MICRO_INVERTER",
            "status": "Online",
            "currentPower": 2000,
            "totalPowerGeneration": 100
        },
        {
            "deviceId": "inv_002",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "status": "Online",
            "today": {
                "currentPower": 1800,
                "totalPowerGeneration": 90
            }
        }
    ])

    api_client.fetch_device_statistics = AsyncMock(return_value={})

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client=api_client,
        family_id="test_family",
        family_name="Test Family",
    )

    data = await coordinator._async_update_data()
    aggregates = data["aggregates"]

    # Total should be sum of inverters only
    assert aggregates["total_solar_power"] == 2000 + 1800, \
        f"Expected 3800W (2000+1800), got {aggregates['total_solar_power']}W"


@pytest.mark.asyncio
async def test_total_solar_power_battery_only():
    """Test total_solar_power with only battery MPPT (no inverters)."""

    hass = MagicMock()
    api_client = MagicMock()

    # Only battery with MPPT, no inverters
    api_client.fetch_device_list = AsyncMock(return_value=[
        {
            "deviceId": "bat_001",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "status": "Online",
            "deviceCount": 1,
        }
    ])

    battery_stats = {
        "batteryMppt1InPower": 1200,
        "batteryMppt2InPower": 900,
        "outputPowerTotal": 2000,  # Battery outputting 2kW (should NOT be in solar)
    }

    api_client.fetch_device_statistics = AsyncMock(return_value=battery_stats)

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client=api_client,
        family_id="test_family",
        family_name="Test Family",
    )

    data = await coordinator._async_update_data()
    aggregates = data["aggregates"]

    # Total should be MPPT inputs only, NOT output
    assert aggregates["total_solar_power"] == 1200 + 900, \
        f"Expected 2100W (1200+900 MPPT), got {aggregates['total_solar_power']}W"

    # Verify output is not included
    assert aggregates["total_solar_power"] != 2000, \
        "Battery output should not be counted as solar power"
