"""Test the Sunlit device coordinator."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator


async def test_device_coordinator_update_success(
    hass: HomeAssistant,
    enable_custom_integrations,
    device_statistics_response,
):
    """Test successful device data update."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = [
        {
            "deviceId": "meter_001",
            "deviceType": "SHELLY_3EM_METER",
            "status": "Online",
            "totalAcPower": 1500,
            "dailyRetEnergy": 10.5,
            "totalRetEnergy": 1234.5,
        },
        {
            "deviceId": "inverter_001",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "status": "Online",
            "currentPower": 2500,
            "totalPowerGeneration": 5678.9,
        },
        {
            "deviceId": "battery_001",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "status": "Online",
            "batteryLevel": 85,
            "inputPowerTotal": 500,
            "outputPowerTotal": 0,
            "deviceCount": 3,  # Fix: Add deviceCount for dynamic module discovery
        },
    ]
    api_client.fetch_device_statistics.return_value = device_statistics_response[
        "content"
    ]

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data is not None
    assert "devices" in data
    assert "aggregates" in data

    devices = data["devices"]
    assert len(devices) == 3
    assert "meter_001" in devices
    assert "inverter_001" in devices
    assert "battery_001" in devices

    # Check meter data
    meter = devices["meter_001"]
    assert meter["status"] == "Online"
    assert meter["deviceType"] == "SHELLY_3EM_METER"
    assert meter["total_ac_power"] == 1500

    # Check inverter data
    inverter = devices["inverter_001"]
    assert inverter["current_power"] == 2500
    assert inverter["total_power_generation"] == 5678.9

    # Check battery data with detailed statistics
    battery = devices["battery_001"]
    assert battery["battery_level"] == 85
    assert battery["batterySoc"] == 85
    assert battery["battery1Soc"] == 84
    assert battery["battery2Soc"] == 86

    # Check aggregates
    aggregates = data["aggregates"]
    # Inverter power should NOT be included in total_solar_power (it's OUTPUT not solar)
    # Total should be sum of battery MPPT inputs from device_statistics_response fixture:
    # batteryMppt1InPower: 3284.1
    # batteryMppt2InPower: 3083.34
    # battery1Mppt1InPower: 2190.1
    # battery2Mppt1InPower: 2332.18
    # Total: 10889.72
    expected_solar = 3284.1 + 3083.34 + 2190.1 + 2332.18
    assert aggregates["total_solar_power"] == pytest.approx(expected_solar, rel=1e-3)
    assert aggregates["total_solar_energy"] == 5678.9
    assert aggregates["daily_grid_export_energy"] == 10.5
    assert aggregates["total_grid_export_energy"] == 1234.5

    # Verify device statistics were fetched for online devices
    assert api_client.fetch_device_statistics.call_count == 3


async def test_device_coordinator_offline_devices(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test device coordinator skips statistics for offline devices."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = [
        {
            "deviceId": "meter_001",
            "deviceType": "SHELLY_3EM_METER",
            "status": "Offline",
            "totalAcPower": 0,
        },
    ]

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data is not None
    devices = data["devices"]
    assert "meter_001" in devices
    assert devices["meter_001"]["status"] == "Offline"

    # Should not fetch statistics for offline devices
    api_client.fetch_device_statistics.assert_not_called()


async def test_device_coordinator_global_devices(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test device coordinator for global/unassigned devices."""
    api_client = AsyncMock()
    api_client.get_device_list.return_value = [
        {
            "deviceId": "dev1",
            "deviceType": "SHELLY_3EM_METER",
            "spaceId": None,
            "status": "Online",
        },
        {
            "deviceId": "dev2",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "spaceId": "123",  # Has spaceId, should be filtered
            "status": "Online",
        },
    ]
    api_client.fetch_device_statistics.return_value = {}

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "global",
        "Unassigned Devices",
        is_global=True,
    )

    data = await coordinator._async_update_data()

    assert data is not None
    devices = data["devices"]

    # Should only include device without spaceId
    assert len(devices) == 1
    assert "dev1" in devices
    assert "dev2" not in devices


async def test_device_coordinator_inverter_variations(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test device coordinator handles different inverter data structures."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = [
        {
            "deviceId": "inv1",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "status": "Online",
            "today": {
                "currentPower": 1000,
                "totalPowerGeneration": 100,
                "totalEarnings": {"earnings": 10.5},
            },
        },
        {
            "deviceId": "inv2",
            "deviceType": "SOLAR_MICRO_INVERTER",
            "status": "Online",
            "currentPower": 2000,
            "totalPowerGeneration": 200,
            "dailyEarnings": 20.5,
        },
    ]
    api_client.fetch_device_statistics.return_value = {"totalYield": 150}

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    devices = data["devices"]

    # Check first inverter with "today" structure
    assert devices["inv1"]["current_power"] == 1000
    assert devices["inv1"]["total_power_generation"] == 100
    assert devices["inv1"]["daily_earnings"] == 10.5

    # Check second inverter with direct fields
    assert devices["inv2"]["current_power"] == 2000
    assert devices["inv2"]["total_power_generation"] == 200
    assert devices["inv2"]["daily_earnings"] == 20.5

    # Check aggregates
    aggregates = data["aggregates"]
    # Inverters are OUTPUT devices, not solar generators, so total_solar_power should be 0
    assert aggregates["total_solar_power"] == 0  # No MPPT inputs = 0W solar
    assert aggregates["total_solar_energy"] == 300  # 100 + 200


# Tests for Issue #62 - DEYE 2000 and Shelly Pro 3EM support with negative value handling
async def test_device_coordinator_negative_meter_energy_clamped(
    hass: HomeAssistant,
    enable_custom_integrations,
    device_list_with_negative_energy,
):
    """Test that negative daily energy values from meters are clamped to 0."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = device_list_with_negative_energy
    api_client.fetch_device_statistics.return_value = {
        "totalAcPower": 1500,
        "dailyBuyEnergy": -0.3,  # Negative in statistics too
        "dailyRetEnergy": -0.8,  # Negative in statistics too
        "totalBuyEnergy": 1234.5,
        "totalRetEnergy": 2345.6,
    }

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    devices = data["devices"]

    # Verify negative values were clamped to 0
    assert devices["meter_pro_001"]["daily_buy_energy"] == 0.0
    assert devices["meter_pro_001"]["daily_ret_energy"] == 0.0
    # Positive totals should be unchanged
    assert devices["meter_pro_001"]["total_buy_energy"] == 1234.5
    assert devices["meter_pro_001"]["total_ret_energy"] == 2345.6


async def test_device_coordinator_negative_inverter_energy_clamped(
    hass: HomeAssistant,
    enable_custom_integrations,
    device_list_with_negative_energy,
):
    """Test that negative daily energy values from inverters are clamped to 0."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = device_list_with_negative_energy
    api_client.fetch_device_statistics.return_value = {"totalYield": 150.5}

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    devices = data["devices"]

    # Verify negative totalPowerGeneration was clamped to 0
    assert devices["inverter_deye_001"]["total_power_generation"] == 0.0
    # Current power should be unchanged
    assert devices["inverter_deye_001"]["current_power"] == 2000


async def test_device_coordinator_shelly_pro3em_processing(
    hass: HomeAssistant,
    enable_custom_integrations,
    device_list_with_shelly_pro3em,
):
    """Test that Shelly Pro 3EM meters are processed correctly."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = device_list_with_shelly_pro3em
    api_client.fetch_device_statistics.return_value = {
        "totalAcPower": 2400,
        "dailyBuyEnergy": 8.5,
        "dailyRetEnergy": 12.7,
        "totalBuyEnergy": 5678.9,
        "totalRetEnergy": 6789.0,
    }

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    devices = data["devices"]

    # Verify Shelly Pro 3EM is processed same as regular 3EM
    assert "meter_pro_002" in devices
    assert devices["meter_pro_002"]["daily_buy_energy"] == 8.5
    assert devices["meter_pro_002"]["daily_ret_energy"] == 12.7
    assert devices["meter_pro_002"]["total_ac_power"] == 2400


async def test_device_coordinator_solar_micro_inverter_processing(
    hass: HomeAssistant,
    enable_custom_integrations,
    device_list_with_deye_inverter,
):
    """Test that SOLAR_MICRO_INVERTER (DEYE) is processed correctly."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = device_list_with_deye_inverter
    api_client.fetch_device_statistics.return_value = {"totalYield": 250.3}

    coordinator = SunlitDeviceCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()
    devices = data["devices"]

    # Verify DEYE inverter is processed (uses flat structure, not "today" object)
    assert "inverter_deye_002" in devices
    assert devices["inverter_deye_002"]["current_power"] == 1800
    assert devices["inverter_deye_002"]["total_power_generation"] == 156.7
    assert devices["inverter_deye_002"]["daily_earnings"] == 15.2
    assert devices["inverter_deye_002"]["total_yield"] == 250.3
