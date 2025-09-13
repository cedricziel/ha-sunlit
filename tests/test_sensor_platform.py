"""Tests for the Sunlit sensor platform."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from custom_components.sunlit import SunlitDataUpdateCoordinator
from custom_components.sunlit.const import DOMAIN
from custom_components.sunlit.sensor import async_setup_entry


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with test data."""
    coordinator = MagicMock(spec=SunlitDataUpdateCoordinator)
    coordinator.family_id = "test_family_123"
    coordinator.family_name = "Test Family"

    # Create timestamps for strategy history
    now = datetime.now()
    two_hours_ago = now - timedelta(hours=2)

    coordinator.data = {
        "family": {
            "device_count": 3,
            "online_devices": 2,
            "offline_devices": 1,
            "total_ac_power": 1500,
            "average_battery_level": 85,
            "battery_strategy": "SELF_CONSUMPTION",
            "hw_soc_min": 10,
            "hw_soc_max": 95,
            "last_strategy_change": int(two_hours_ago.timestamp() * 1000),
            "last_strategy_type": "SELF_CONSUMPTION",
            "last_strategy_status": "ACTIVE",
            "strategy_changes_today": 2,
            "total_solar_energy": 1234.5,
            "total_solar_power": 3500,
            "daily_grid_export_energy": 15.8,
            "total_grid_export_energy": 1802.3,
        },
        "devices": {
            "meter_001": {
                "total_ac_power": 1500,
                "daily_buy_energy": 5.2,
                "daily_ret_energy": 8.7,
                "total_buy_energy": 1234.5,
                "total_ret_energy": 987.6,
            },
            "inverter_001": {
                "current_power": 2500,
                "total_power_generation": 5678.9,
                "daily_earnings": 12.34,
            },
            "battery_001": {
                "battery_level": 85,
                "batterySoc": 85,
                "chargeRemaining": 120,
                "dischargeRemaining": 480,
                "input_power_total": 1000,
                "output_power_total": 0,
                "batteryMppt1InVol": 400.5,
                "batteryMppt1InCur": 2.5,
                "batteryMppt1InPower": 1000,
            },
        },
    }

    coordinator.devices = {
        "meter_001": {
            "deviceId": "meter_001",
            "deviceType": "SHELLY_3EM_METER",
            "deviceName": "Smart Meter",
        },
        "inverter_001": {
            "deviceId": "inverter_001",
            "deviceType": "YUNENG_MICRO_INVERTER",
            "deviceName": "Solar Inverter",
        },
        "battery_001": {
            "deviceId": "battery_001",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "deviceName": "Battery Storage",
        },
    }

    return coordinator


async def test_family_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinator,
):
    """Test that family sensors are created with correct attributes."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinator
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": mock_coordinator
        }
    }

    # Create sensors
    async_add_entities = AsyncMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find the last_strategy_change sensor
    timestamp_sensor = None
    for sensor in sensors:
        if hasattr(sensor, 'entity_description') and sensor.entity_description.key == "last_strategy_change":
            timestamp_sensor = sensor
            break

    assert timestamp_sensor is not None, "last_strategy_change sensor not found"
    assert timestamp_sensor.entity_description.device_class == SensorDeviceClass.TIMESTAMP
    assert timestamp_sensor.entity_description.state_class is None

    # Check other important sensors
    sensor_map = {s.entity_description.key: s for s in sensors if hasattr(s, 'entity_description')}

    # Check power sensor
    if "total_ac_power" in sensor_map:
        power_sensor = sensor_map["total_ac_power"]
        assert power_sensor.entity_description.device_class == SensorDeviceClass.POWER
        assert power_sensor.entity_description.state_class == SensorStateClass.MEASUREMENT
        assert power_sensor.entity_description.native_unit_of_measurement == UnitOfPower.WATT

    # Check energy sensor
    if "total_solar_energy" in sensor_map:
        energy_sensor = sensor_map["total_solar_energy"]
        assert energy_sensor.entity_description.device_class == SensorDeviceClass.ENERGY
        assert energy_sensor.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
        assert energy_sensor.entity_description.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR

    # Check battery sensor
    if "average_battery_level" in sensor_map:
        battery_sensor = sensor_map["average_battery_level"]
        assert battery_sensor.entity_description.device_class == SensorDeviceClass.BATTERY
        assert battery_sensor.entity_description.state_class is None
        assert battery_sensor.entity_description.native_unit_of_measurement == "%"


async def test_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinator,
):
    """Test that device sensors are created with correct types."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinator
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": mock_coordinator
        }
    }

    # Create sensors
    async_add_entities = AsyncMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find meter sensors
    meter_sensors = [s for s in sensors if hasattr(s, '_device_id') and s._device_id == "meter_001"]
    assert len(meter_sensors) > 0, "No meter sensors found"

    # Check meter sensor types
    for sensor in meter_sensors:
        if hasattr(sensor, 'entity_description'):
            key = sensor.entity_description.key
            if "energy" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.ENERGY
                if "daily" in key:
                    assert sensor.entity_description.state_class == SensorStateClass.TOTAL
                elif "total" in key:
                    assert sensor.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
            elif "power" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.POWER
                assert sensor.entity_description.state_class == SensorStateClass.MEASUREMENT

    # Find battery sensors
    battery_sensors = [s for s in sensors if hasattr(s, '_device_id') and s._device_id == "battery_001"]
    assert len(battery_sensors) > 0, "No battery sensors found"

    # Check battery sensor types
    for sensor in battery_sensors:
        if hasattr(sensor, 'entity_description'):
            key = sensor.entity_description.key
            if key == "chargeRemaining" or key == "dischargeRemaining":
                assert sensor.entity_description.device_class == SensorDeviceClass.DURATION
            elif "Soc" in key or "battery_level" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.BATTERY
            elif "InVol" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.VOLTAGE
            elif "InCur" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.CURRENT
            elif "InPower" in key or "power" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.POWER


async def test_timestamp_sensor_value(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinator,
):
    """Test that last_strategy_change sensor returns proper datetime value."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinator
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": mock_coordinator
        }
    }

    # Create sensors
    async_add_entities = AsyncMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find the last_strategy_change sensor
    timestamp_sensor = None
    for sensor in sensors:
        if hasattr(sensor, 'entity_description') and sensor.entity_description.key == "last_strategy_change":
            timestamp_sensor = sensor
            break

    assert timestamp_sensor is not None

    # Check that native_value returns a datetime
    value = timestamp_sensor.native_value
    assert isinstance(value, datetime), f"Expected datetime, got {type(value)}"

    # Verify it's approximately 2 hours ago (within 1 minute tolerance)
    now = datetime.now()
    time_diff = now.timestamp() - value.timestamp()
    assert 7100 < time_diff < 7300, f"Timestamp should be ~2 hours ago, but diff is {time_diff} seconds"


async def test_sensor_count(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinator,
):
    """Test that the correct number of sensors are created."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinator
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": mock_coordinator
        }
    }

    # Create sensors
    async_add_entities = AsyncMock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Count family sensors (should match keys in family data minus binary sensors)
    family_sensor_count = len([s for s in sensors if hasattr(s, '_family_id')])

    # Count device sensors
    device_sensor_count = len([s for s in sensors if hasattr(s, '_device_id')])

    # Should have multiple sensors created
    assert family_sensor_count > 0, "No family sensors created"
    assert device_sensor_count > 0, "No device sensors created"
    assert len(sensors) > 20, f"Expected many sensors, but only got {len(sensors)}"
