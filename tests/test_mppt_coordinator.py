"""Test the Sunlit MPPT energy coordinator."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sunlit.coordinators.mppt import SunlitMpptEnergyCoordinator


async def test_mppt_coordinator_energy_calculation(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test MPPT energy accumulation calculation."""
    # Mock device coordinator
    device_coordinator = MagicMock()
    device_coordinator.data = {
        "devices": {
            "battery_001": {
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "batteryMppt1InPower": 500,
                "batteryMppt2InPower": 300,
                "battery1Mppt1InPower": 200,
                "battery2Mppt1InPower": 150,
            }
        }
    }

    coordinator = SunlitMpptEnergyCoordinator(
        hass,
        device_coordinator,
        "34038",
        "Test Family",
    )

    # First update - initializes accumulators
    data = await coordinator._async_update_data()

    assert data is not None
    assert "mppt_energy" in data
    assert "battery_001" in data["mppt_energy"]

    # All energy should be 0 on first update
    battery_mppt = data["mppt_energy"]["battery_001"]
    assert battery_mppt["batteryMppt1Energy"] == 0
    assert battery_mppt["batteryMppt2Energy"] == 0
    assert battery_mppt["battery1Mppt1Energy"] == 0
    assert battery_mppt["battery2Mppt1Energy"] == 0
    assert data["total_mppt_energy"] == 0

    # Manually simulate time passing by modifying the coordinator's time tracking
    import time
    # Set the last update time to 1 hour ago
    key = "battery_001_batteryMppt1Energy"
    current_time = time.time()
    coordinator.last_mppt_update[key] = current_time - 3600  # 1 hour ago
    coordinator.last_mppt_power[key] = 500

    # Update power values
    device_coordinator.data["devices"]["battery_001"]["batteryMppt1InPower"] = 600

    # Second update - should calculate energy (1 hour at avg 550W = 0.55 kWh)
    data = await coordinator._async_update_data()

    # Energy should be accumulated
    battery_mppt = data["mppt_energy"]["battery_001"]
    assert abs(battery_mppt["batteryMppt1Energy"] - 0.55) < 0.01  # Should be ~0.55 kWh
    assert battery_mppt["batteryMppt2Energy"] == 0  # Initial value

    # Total should be sum of all MPPT energy
    assert data["total_mppt_energy"] >= 0


async def test_mppt_coordinator_no_battery_devices(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test MPPT coordinator with no battery devices."""
    device_coordinator = MagicMock()
    device_coordinator.data = {
        "devices": {
            "meter_001": {
                "deviceType": "SHELLY_3EM_METER",
                "totalAcPower": 1500,
            },
            "inverter_001": {
                "deviceType": "YUNENG_MICRO_INVERTER",
                "currentPower": 2000,
            },
        }
    }

    coordinator = SunlitMpptEnergyCoordinator(
        hass,
        device_coordinator,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data is not None
    assert "mppt_energy" in data
    assert len(data["mppt_energy"]) == 0  # No battery devices
    assert data["total_mppt_energy"] == 0


async def test_mppt_coordinator_no_device_data(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test MPPT coordinator when device coordinator has no data."""
    device_coordinator = MagicMock()
    device_coordinator.data = None

    coordinator = SunlitMpptEnergyCoordinator(
        hass,
        device_coordinator,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data == {"mppt_energy": {}}


async def test_mppt_coordinator_partial_mppt_data(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test MPPT coordinator with partial MPPT data."""
    device_coordinator = MagicMock()
    device_coordinator.data = {
        "devices": {
            "battery_001": {
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "batteryMppt1InPower": 500,
                # No Mppt2 power
                "battery1Mppt1InPower": 200,
                # No battery2 or battery3 power
            }
        }
    }

    coordinator = SunlitMpptEnergyCoordinator(
        hass,
        device_coordinator,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    battery_mppt = data["mppt_energy"]["battery_001"]

    # Should only have energy keys for MPPT inputs with power data
    assert "batteryMppt1Energy" in battery_mppt
    assert "batteryMppt2Energy" not in battery_mppt  # No power data
    assert "battery1Mppt1Energy" in battery_mppt
    assert "battery2Mppt1Energy" not in battery_mppt  # No power data


async def test_mppt_coordinator_update_interval(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test MPPT coordinator has correct update interval."""
    device_coordinator = MagicMock()
    device_coordinator.data = {"devices": {}}

    coordinator = SunlitMpptEnergyCoordinator(
        hass,
        device_coordinator,
        "34038",
        "Test Family",
    )

    # Should have 1 minute update interval
    assert coordinator.update_interval == timedelta(minutes=1)


async def test_mppt_coordinator_trapezoidal_integration(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test MPPT coordinator uses trapezoidal integration correctly."""
    device_coordinator = MagicMock()
    device_coordinator.data = {
        "devices": {
            "battery_001": {
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "batteryMppt1InPower": 1000,  # 1000W
            }
        }
    }

    coordinator = SunlitMpptEnergyCoordinator(
        hass,
        device_coordinator,
        "34038",
        "Test Family",
    )

    # First update
    await coordinator._async_update_data()

    # Manually set time tracking for predictable test
    key = "battery_001_batteryMppt1Energy"
    coordinator.last_mppt_update[key] = 0  # Start time
    coordinator.last_mppt_power[key] = 1000  # 1000W
    coordinator.mppt_energy[key] = 0

    # Simulate 1 hour passing with power changing to 2000W
    device_coordinator.data["devices"]["battery_001"]["batteryMppt1InPower"] = 2000

    # Override time calculation for test
    import time
    original_time = time.time
    time.time = lambda: 3600  # 1 hour later

    try:
        data = await coordinator._async_update_data()

        # Trapezoidal integration: avg_power = (1000 + 2000) / 2 = 1500W
        # Energy = 1500W * 1 hour = 1.5 kWh
        battery_mppt = data["mppt_energy"]["battery_001"]
        assert abs(battery_mppt["batteryMppt1Energy"] - 1.5) < 0.01  # Allow small floating point error

    finally:
        time.time = original_time
