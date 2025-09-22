"""Integration tests for energy sensor data flow."""

import time
from datetime import timedelta
from unittest.mock import MagicMock, Mock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.sunlit.const import DOMAIN
from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator
from custom_components.sunlit.coordinators.family import SunlitFamilyCoordinator
from custom_components.sunlit.coordinators.mppt import SunlitMpptEnergyCoordinator
from custom_components.sunlit.sensor import async_setup_entry


@pytest.fixture
def mock_device_coordinator():
    """Create a mock device coordinator with battery data."""
    coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    coordinator.family_id = "test_family"
    coordinator.family_name = "Test Family"
    coordinator.last_update_success = True

    # Mock the get_battery_module_count method
    coordinator.get_battery_module_count.return_value = 3

    # Set up device data with battery
    coordinator.data = {
        "devices": {
            "battery_001": {
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "batterySoc": 85,
                "batteryMppt1InPower": 1000,
                "batteryMppt2InPower": 500,
                "battery1Mppt1InPower": 300,
                "battery2Mppt1InPower": 200,
                "battery3Mppt1InPower": 100,
                "module_count": 3,
            }
        }
    }

    coordinator.devices = {
        "battery_001": {
            "deviceId": "battery_001",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "deviceName": "Test Battery",
            "deviceSn": "BAT001",
        }
    }

    return coordinator


@pytest.fixture
def mock_mppt_coordinator(mock_device_coordinator):
    """Create a mock MPPT coordinator with energy data."""
    coordinator = MagicMock(spec=SunlitMpptEnergyCoordinator)
    coordinator.family_id = "test_family"
    coordinator.family_name = "Test Family"
    coordinator.last_update_success = True
    coordinator.update_interval = timedelta(minutes=1)

    # Set the device coordinator reference
    coordinator.device_coordinator = mock_device_coordinator

    # Set up MPPT energy data
    coordinator.data = {
        "mppt_energy": {
            "battery_001": {
                "batteryMppt1Energy": 12.5,
                "batteryMppt2Energy": 8.3,
                "battery1Mppt1Energy": 5.2,
                "battery2Mppt1Energy": 3.7,
                "battery3Mppt1Energy": 1.8,
            }
        },
        "total_mppt_energy": 31.5,
    }

    # Mock internal state for testing energy accumulation
    coordinator.mppt_energy = {
        "battery_001_batteryMppt1Energy": 12.5,
        "battery_001_batteryMppt2Energy": 8.3,
        "battery_001_battery1Mppt1Energy": 5.2,
        "battery_001_battery2Mppt1Energy": 3.7,
        "battery_001_battery3Mppt1Energy": 1.8,
    }

    coordinator.last_mppt_power = {
        "battery_001_batteryMppt1Energy": 1000,
        "battery_001_batteryMppt2Energy": 500,
        "battery_001_battery1Mppt1Energy": 300,
        "battery_001_battery2Mppt1Energy": 200,
        "battery_001_battery3Mppt1Energy": 100,
    }

    coordinator.last_mppt_update = {
        "battery_001_batteryMppt1Energy": time.time(),
        "battery_001_batteryMppt2Energy": time.time(),
        "battery_001_battery1Mppt1Energy": time.time(),
        "battery_001_battery2Mppt1Energy": time.time(),
        "battery_001_battery3Mppt1Energy": time.time(),
    }

    return coordinator


@pytest.fixture
def mock_family_coordinator():
    """Create a mock family coordinator."""
    coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    coordinator.family_id = "test_family"
    coordinator.family_name = "Test Family"
    coordinator.last_update_success = True
    coordinator.data = {
        "family": {
            "device_count": 1,
            "online_devices": 1,
        }
    }
    return coordinator


async def test_battery_mppt_energy_sensors_receive_data(
    hass: HomeAssistant,
    mock_config_entry,
    mock_device_coordinator,
    mock_mppt_coordinator,
    mock_family_coordinator,
):
    """Test that battery MPPT energy sensors receive data from MPPT coordinator."""
    mock_config_entry.add_to_hass(hass)

    # Set up coordinators in hass data
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family": {
                "family": mock_family_coordinator,
                "device": mock_device_coordinator,
                "strategy": None,
                "mppt": mock_mppt_coordinator,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find battery MPPT energy sensors
    battery_mppt1_energy = None
    battery_mppt2_energy = None

    for sensor in sensors:
        if hasattr(sensor, "_device_id") and sensor._device_id == "battery_001":
            if hasattr(sensor, "entity_description"):
                if sensor.entity_description.key == "batteryMppt1Energy":
                    battery_mppt1_energy = sensor
                elif sensor.entity_description.key == "batteryMppt2Energy":
                    battery_mppt2_energy = sensor

    # Verify sensors were created
    assert battery_mppt1_energy is not None, "batteryMppt1Energy sensor not found"
    assert battery_mppt2_energy is not None, "batteryMppt2Energy sensor not found"

    # Verify sensors have mppt_coordinator
    assert hasattr(battery_mppt1_energy, "_mppt_coordinator")
    assert battery_mppt1_energy._mppt_coordinator is mock_mppt_coordinator

    # Verify sensors return correct values from MPPT coordinator
    assert battery_mppt1_energy.native_value == 12.5
    assert battery_mppt2_energy.native_value == 8.3

    # Verify sensor attributes
    assert battery_mppt1_energy.entity_description.device_class == SensorDeviceClass.ENERGY
    assert battery_mppt1_energy.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
    assert (
        battery_mppt1_energy.entity_description.native_unit_of_measurement
        == UnitOfEnergy.KILO_WATT_HOUR
    )


async def test_battery_module_energy_sensors_receive_data(
    hass: HomeAssistant,
    mock_config_entry,
    mock_device_coordinator,
    mock_mppt_coordinator,
    mock_family_coordinator,
):
    """Test that battery module MPPT energy sensors receive data from MPPT coordinator."""
    mock_config_entry.add_to_hass(hass)

    # Set up coordinators in hass data
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family": {
                "family": mock_family_coordinator,
                "device": mock_device_coordinator,
                "strategy": None,
                "mppt": mock_mppt_coordinator,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find battery module energy sensors
    module_energy_sensors = {}

    for sensor in sensors:
        if hasattr(sensor, "_module_number"):
            if hasattr(sensor, "entity_description"):
                key = sensor.entity_description.key
                if "Mppt1Energy" in key:
                    module_num = sensor._module_number
                    module_energy_sensors[module_num] = sensor

    # Verify all 3 module energy sensors were created
    assert len(module_energy_sensors) == 3, (
        f"Expected 3 module energy sensors, found {len(module_energy_sensors)}"
    )

    # Verify sensors have mppt_coordinator and return correct values
    assert module_energy_sensors[1].native_value == 5.2
    assert module_energy_sensors[2].native_value == 3.7
    assert module_energy_sensors[3].native_value == 1.8

    # Verify sensor attributes
    for sensor in module_energy_sensors.values():
        assert hasattr(sensor, "_mppt_coordinator")
        assert sensor._mppt_coordinator is mock_mppt_coordinator
        assert sensor.entity_description.device_class == SensorDeviceClass.ENERGY
        assert sensor.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
        assert (
            sensor.entity_description.native_unit_of_measurement
            == UnitOfEnergy.KILO_WATT_HOUR
        )


async def test_energy_sensor_updates_when_coordinator_updates(
    hass: HomeAssistant,
    mock_config_entry,
    mock_device_coordinator,
    mock_mppt_coordinator,
    mock_family_coordinator,
):
    """Test that energy sensors update when MPPT coordinator data changes."""
    mock_config_entry.add_to_hass(hass)

    # Set up coordinators in hass data
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family": {
                "family": mock_family_coordinator,
                "device": mock_device_coordinator,
                "strategy": None,
                "mppt": mock_mppt_coordinator,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    sensors = async_add_entities.call_args[0][0]

    # Find a battery MPPT energy sensor
    battery_mppt1_energy = None
    for sensor in sensors:
        if hasattr(sensor, "_device_id") and sensor._device_id == "battery_001":
            if hasattr(sensor, "entity_description"):
                if sensor.entity_description.key == "batteryMppt1Energy":
                    battery_mppt1_energy = sensor
                    break

    assert battery_mppt1_energy is not None

    # Initial value
    assert battery_mppt1_energy.native_value == 12.5

    # Update MPPT coordinator data
    mock_mppt_coordinator.data["mppt_energy"]["battery_001"]["batteryMppt1Energy"] = 15.0

    # Sensor should now return updated value
    assert battery_mppt1_energy.native_value == 15.0


async def test_energy_sensors_unavailable_when_no_mppt_data(
    hass: HomeAssistant,
    mock_config_entry,
    mock_device_coordinator,
    mock_family_coordinator,
):
    """Test that energy sensors are unavailable when MPPT coordinator has no data."""
    mock_config_entry.add_to_hass(hass)

    # Create MPPT coordinator with no data
    mppt_coordinator_no_data = MagicMock(spec=SunlitMpptEnergyCoordinator)
    mppt_coordinator_no_data.family_id = "test_family"
    mppt_coordinator_no_data.family_name = "Test Family"
    mppt_coordinator_no_data.last_update_success = True
    mppt_coordinator_no_data.data = {"mppt_energy": {}}

    # Set up coordinators in hass data
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family": {
                "family": mock_family_coordinator,
                "device": mock_device_coordinator,
                "strategy": None,
                "mppt": mppt_coordinator_no_data,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    sensors = async_add_entities.call_args[0][0]

    # Find battery MPPT energy sensor
    battery_mppt1_energy = None
    for sensor in sensors:
        if hasattr(sensor, "_device_id") and sensor._device_id == "battery_001":
            if hasattr(sensor, "entity_description"):
                if sensor.entity_description.key == "batteryMppt1Energy":
                    battery_mppt1_energy = sensor
                    break

    assert battery_mppt1_energy is not None

    # Sensor should return None when no data available
    assert battery_mppt1_energy.native_value is None


async def test_non_energy_sensors_use_device_coordinator(
    hass: HomeAssistant,
    mock_config_entry,
    mock_device_coordinator,
    mock_mppt_coordinator,
    mock_family_coordinator,
):
    """Test that non-energy sensors still use device coordinator for data."""
    mock_config_entry.add_to_hass(hass)

    # Add power data to device coordinator
    mock_device_coordinator.data["devices"]["battery_001"]["batteryMppt1InPower"] = 1000

    # Set up coordinators in hass data
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family": {
                "family": mock_family_coordinator,
                "device": mock_device_coordinator,
                "strategy": None,
                "mppt": mock_mppt_coordinator,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    sensors = async_add_entities.call_args[0][0]

    # Find battery MPPT power sensor (not energy)
    battery_mppt1_power = None
    for sensor in sensors:
        if hasattr(sensor, "_device_id") and sensor._device_id == "battery_001":
            if hasattr(sensor, "entity_description"):
                if sensor.entity_description.key == "batteryMppt1InPower":
                    battery_mppt1_power = sensor
                    break

    assert battery_mppt1_power is not None

    # Power sensor should get data from device coordinator, not MPPT coordinator
    assert battery_mppt1_power.native_value == 1000

    # Verify it's using device coordinator
    assert battery_mppt1_power.coordinator is mock_device_coordinator


async def test_total_solar_energy_aggregation(
    hass: HomeAssistant,
    mock_config_entry,
    mock_family_coordinator,
):
    """Test that total_solar_energy family sensor aggregates correctly."""
    mock_config_entry.add_to_hass(hass)

    # Create device coordinator with multiple inverters
    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family"
    device_coordinator.family_name = "Test Family"
    device_coordinator.last_update_success = True
    device_coordinator.get_battery_module_count.return_value = 0

    device_coordinator.data = {
        "devices": {
            "inverter_001": {
                "deviceType": "YUNENG_MICRO_INVERTER",
                "total_power_generation": 100.5,
            },
            "inverter_002": {
                "deviceType": "YUNENG_MICRO_INVERTER",
                "total_power_generation": 200.3,
            },
        },
        "aggregates": {
            "total_solar_energy": 300.8,  # Sum of inverter energies
        }
    }

    device_coordinator.devices = {
        "inverter_001": {
            "deviceId": "inverter_001",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "deviceName": "Inverter 1",
        },
        "inverter_002": {
            "deviceId": "inverter_002",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "deviceName": "Inverter 2",
        },
    }

    # Update family coordinator data
    mock_family_coordinator.data["family"]["total_solar_energy"] = 300.8

    # Set up coordinators in hass data
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family": {
                "family": mock_family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    sensors = async_add_entities.call_args[0][0]

    # Find total_solar_energy family sensor
    total_solar_energy = None
    for sensor in sensors:
        if hasattr(sensor, "_family_id") and not hasattr(sensor, "_device_id"):
            if hasattr(sensor, "entity_description"):
                if sensor.entity_description.key == "total_solar_energy":
                    total_solar_energy = sensor
                    break

    assert total_solar_energy is not None, "total_solar_energy sensor not found"

    # Should use device coordinator for this aggregate
    assert total_solar_energy.coordinator is device_coordinator

    # Verify sensor attributes
    assert total_solar_energy.entity_description.device_class == SensorDeviceClass.ENERGY
    assert total_solar_energy.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
    assert (
        total_solar_energy.entity_description.native_unit_of_measurement
        == UnitOfEnergy.KILO_WATT_HOUR
    )
