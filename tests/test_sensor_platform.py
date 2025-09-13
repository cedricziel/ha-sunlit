"""Tests for the Sunlit sensor platform."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from custom_components.sunlit.coordinators.family import SunlitFamilyCoordinator
from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator
from custom_components.sunlit.coordinators.strategy import (
    SunlitStrategyHistoryCoordinator,
)
from custom_components.sunlit.coordinators.mppt import SunlitMpptEnergyCoordinator
from custom_components.sunlit.const import DOMAIN
from custom_components.sunlit.sensor import async_setup_entry
from tests.test_utils import assert_sensors


@pytest.fixture
def mock_coordinators():
    """Create mock coordinators with test data."""
    # Create family coordinator
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.devices = {}

    # Create timestamps for strategy history
    now = datetime.now()
    two_hours_ago = now - timedelta(hours=2)

    family_coordinator.data = {
        "family": {
            "device_count": 3,
            "online_devices": 2,
            "offline_devices": 1,
            "total_ac_power": 1500,
            "average_battery_level": 85,
            "battery_strategy": "SELF_CONSUMPTION",
            "hw_soc_min": 10,
            "hw_soc_max": 95,
            "total_solar_energy": 1234.5,
            "total_solar_power": 3500,
            "daily_grid_export_energy": 15.8,
            "total_grid_export_energy": 1802.3,
        },
    }

    # Create device coordinator
    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
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

    device_coordinator.devices = {
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

    # Create strategy coordinator
    strategy_coordinator = MagicMock(spec=SunlitStrategyHistoryCoordinator)
    strategy_coordinator.family_id = "test_family_123"
    strategy_coordinator.family_name = "Test Family"
    strategy_coordinator.data = {
        "strategy": {
            "last_strategy_change": int(two_hours_ago.timestamp() * 1000),
            "last_strategy_type": "SELF_CONSUMPTION",
            "last_strategy_status": "ACTIVE",
            "strategy_changes_today": 2,
        }
    }

    # Create MPPT coordinator (can be None for tests)
    mppt_coordinator = None

    return {
        "family": family_coordinator,
        "device": device_coordinator,
        "strategy": strategy_coordinator,
        "mppt": mppt_coordinator,
    }


async def test_family_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinators,
):
    """Test that family sensors are created with correct attributes."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinators
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {"test_family_123": mock_coordinators}
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find the last_strategy_change sensor
    timestamp_sensor = None
    for sensor in sensors:
        if (
            hasattr(sensor, "entity_description")
            and sensor.entity_description.key == "last_strategy_change"
        ):
            timestamp_sensor = sensor
            break

    assert timestamp_sensor is not None, "last_strategy_change sensor not found"
    assert (
        timestamp_sensor.entity_description.device_class == SensorDeviceClass.TIMESTAMP
    )
    assert timestamp_sensor.entity_description.state_class is None

    # Check other important sensors
    sensor_map = {
        s.entity_description.key: s for s in sensors if hasattr(s, "entity_description")
    }

    # Check power sensor
    if "total_ac_power" in sensor_map:
        power_sensor = sensor_map["total_ac_power"]
        assert power_sensor.entity_description.device_class == SensorDeviceClass.POWER
        assert (
            power_sensor.entity_description.state_class == SensorStateClass.MEASUREMENT
        )
        assert (
            power_sensor.entity_description.native_unit_of_measurement
            == UnitOfPower.WATT
        )

    # Check energy sensor
    if "total_solar_energy" in sensor_map:
        energy_sensor = sensor_map["total_solar_energy"]
        assert energy_sensor.entity_description.device_class == SensorDeviceClass.ENERGY
        assert (
            energy_sensor.entity_description.state_class
            == SensorStateClass.TOTAL_INCREASING
        )
        assert (
            energy_sensor.entity_description.native_unit_of_measurement
            == UnitOfEnergy.KILO_WATT_HOUR
        )

    # Check battery sensor
    if "average_battery_level" in sensor_map:
        battery_sensor = sensor_map["average_battery_level"]
        assert (
            battery_sensor.entity_description.device_class == SensorDeviceClass.BATTERY
        )
        assert battery_sensor.entity_description.state_class is None
        assert battery_sensor.entity_description.native_unit_of_measurement == "%"


async def test_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinators,
):
    """Test that device sensors are created with correct types."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinators
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {"test_family_123": mock_coordinators}
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find meter sensors
    meter_sensors = [
        s for s in sensors if hasattr(s, "_device_id") and s._device_id == "meter_001"
    ]
    assert len(meter_sensors) > 0, "No meter sensors found"

    # Check meter sensor types
    for sensor in meter_sensors:
        if hasattr(sensor, "entity_description"):
            key = sensor.entity_description.key
            if "energy" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.ENERGY
                )
                if "daily" in key:
                    assert (
                        sensor.entity_description.state_class == SensorStateClass.TOTAL
                    )
                elif "total" in key:
                    assert (
                        sensor.entity_description.state_class
                        == SensorStateClass.TOTAL_INCREASING
                    )
            elif "power" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.POWER
                assert (
                    sensor.entity_description.state_class
                    == SensorStateClass.MEASUREMENT
                )

    # Find battery sensors
    battery_sensors = [
        s for s in sensors if hasattr(s, "_device_id") and s._device_id == "battery_001"
    ]
    assert len(battery_sensors) > 0, "No battery sensors found"

    # Check battery sensor types
    for sensor in battery_sensors:
        if hasattr(sensor, "entity_description"):
            key = sensor.entity_description.key
            if key == "chargeRemaining" or key == "dischargeRemaining":
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.DURATION
                )
            elif "Soc" in key or "battery_level" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.BATTERY
                )
            elif "InVol" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.VOLTAGE
                )
            elif "InCur" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.CURRENT
                )
            elif "InPower" in key or "power" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.POWER


async def test_timestamp_sensor_value(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinators,
):
    """Test that last_strategy_change sensor returns proper datetime value."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinators
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {"test_family_123": mock_coordinators}
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find the last_strategy_change sensor
    timestamp_sensor = None
    for sensor in sensors:
        if (
            hasattr(sensor, "entity_description")
            and sensor.entity_description.key == "last_strategy_change"
        ):
            timestamp_sensor = sensor
            break

    assert timestamp_sensor is not None

    # Check that native_value returns a datetime
    value = timestamp_sensor.native_value
    assert isinstance(value, datetime), f"Expected datetime, got {type(value)}"

    # Verify it's approximately 2 hours ago (within 1 minute tolerance)
    now = datetime.now()
    time_diff = now.timestamp() - value.timestamp()
    assert (
        7100 < time_diff < 7300
    ), f"Timestamp should be ~2 hours ago, but diff is {time_diff} seconds"


async def test_sensor_count(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
    mock_coordinators,
):
    """Test that the correct number of sensors are created."""
    mock_config_entry.add_to_hass(hass)

    # Set up the coordinators
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {"test_family_123": mock_coordinators}
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    # Check that sensors were created
    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Count family sensors (should match keys in family data minus binary sensors)
    family_sensor_count = len([s for s in sensors if hasattr(s, "_family_id")])

    # Count device sensors
    device_sensor_count = len([s for s in sensors if hasattr(s, "_device_id")])

    # Should have multiple sensors created
    assert family_sensor_count > 0, "No family sensors created"
    assert device_sensor_count > 0, "No device sensors created"
    assert len(sensors) > 20, f"Expected many sensors, but only got {len(sensors)}"


async def test_meter_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that meter devices create the correct sensors."""
    from custom_components.sunlit.entities.meter_sensor import SunlitMeterSensor
    from custom_components.sunlit.const import (
        DEVICE_TYPE_METER,
        DEVICE_TYPE_METER_PRO,
        METER_SENSORS,
    )
    from .test_utils import assert_sensors

    # Create specialized coordinators for meter test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "meter_001": {
                "total_ac_power": 1500,
                "daily_buy_energy": 5.2,
                "daily_ret_energy": 8.7,
                "total_buy_energy": 1234.5,
                "total_ret_energy": 987.6,
            }
        }
    }

    # Test both meter device types
    for device_type in [DEVICE_TYPE_METER, DEVICE_TYPE_METER_PRO]:
        device_coordinator.devices = {
            "meter_001": {
                "deviceId": "meter_001",
                "deviceType": device_type,
                "deviceName": "Smart Meter",
            }
        }

        mock_config_entry.add_to_hass(hass)
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                "test_family_123": {
                    "family": family_coordinator,
                    "device": device_coordinator,
                    "strategy": None,
                    "mppt": None,
                }
            }
        }

        # Create sensors
        async_add_entities = Mock()
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        assert async_add_entities.called
        sensors = async_add_entities.call_args[0][0]

        # Use builder pattern for assertions
        expected_keys = set(METER_SENSORS.keys()) | {"status"}
        expected_count = len(METER_SENSORS) + 1  # +1 for status

        (assert_sensors(sensors)
         .for_device("meter_001")
         .with_count(expected_count)
         .having_keys(expected_keys)
         .with_sensor_class(SunlitMeterSensor))

        # Test specific sensor attributes with fluent API
        (assert_sensors(sensors)
         .for_device("meter_001")
         .where_key("total_ac_power")
         .matches_pattern(
             device_class=SensorDeviceClass.POWER,
             state_class=SensorStateClass.MEASUREMENT,
             unit=UnitOfPower.WATT
         ))

        (assert_sensors(sensors)
         .for_device("meter_001")
         .where_key_contains("energy")
         .has_device_class(SensorDeviceClass.ENERGY)
         .has_unit(UnitOfEnergy.KILO_WATT_HOUR))

        (assert_sensors(sensors)
         .for_device("meter_001")
         .where_key_matches(lambda k: "daily" in k and "energy" in k)
         .has_state_class(SensorStateClass.TOTAL))

        (assert_sensors(sensors)
         .for_device("meter_001")
         .where_key_matches(lambda k: "total" in k and "energy" in k)
         .has_state_class(SensorStateClass.TOTAL_INCREASING))

        (assert_sensors(sensors)
         .for_device("meter_001")
         .where_key("status")
         .has_no_device_class()
         .has_no_unit())

        # Clean up for next iteration
        hass.data[DOMAIN] = {}
        async_add_entities.reset_mock()


async def test_battery_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that battery devices create the correct sensors."""
    from custom_components.sunlit.entities.battery_sensor import SunlitBatterySensor
    from custom_components.sunlit.const import DEVICE_TYPE_BATTERY, BATTERY_SENSORS

    # Create specialized coordinators for battery test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "battery_001": {
                "battery_level": 85,
                "batterySoc": 85,
                "chargeRemaining": 120,
                "dischargeRemaining": 480,
                "input_power_total": 1000,
                "output_power_total": 0,
                "battery_capacity": 2.15,
                "batteryMppt1InVol": 400.5,
                "batteryMppt1InCur": 2.5,
                "batteryMppt1InPower": 1000,
                "batteryMppt1Energy": 1234.5,
                "batteryMppt2InVol": 0,
                "batteryMppt2InCur": 0,
                "batteryMppt2InPower": 0,
                "batteryMppt2Energy": 0,
            }
        }
    }

    device_coordinator.devices = {
        "battery_001": {
            "deviceId": "battery_001",
            "deviceType": DEVICE_TYPE_BATTERY,
            "deviceName": "Battery Storage",
        }
    }

    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Test battery device sensors using builder pattern
    expected_battery_keys = set(BATTERY_SENSORS.keys()) | {"status"}

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()  # Exclude battery module sensors
     .with_count(len(BATTERY_SENSORS) + 1)  # +1 for status sensor
     .having_keys(expected_battery_keys)
     .with_sensor_class(SunlitBatterySensor))

    # Test specific sensor patterns
    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key_contains("Remaining")
     .matches_pattern(
         device_class=SensorDeviceClass.DURATION,
         unit="min"
     ))

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key_matches(lambda k: k in ["battery_level", "batterySoc"])
     .matches_pattern(
         device_class=SensorDeviceClass.BATTERY,
         unit="%"
     ))

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key_contains("InVol")
     .matches_pattern(
         device_class=SensorDeviceClass.VOLTAGE,
         unit="V"
     ))

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key_contains("InCur")
     .matches_pattern(
         device_class=SensorDeviceClass.CURRENT,
         unit="A"
     ))

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key_matches(lambda k: "power" in k.lower())
     .matches_pattern(
         device_class=SensorDeviceClass.POWER,
         unit=UnitOfPower.WATT
     ))

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key_matches(lambda k: "energy" in k.lower() or k == "battery_capacity")
     .matches_pattern(
         device_class=SensorDeviceClass.ENERGY,
         unit=UnitOfEnergy.KILO_WATT_HOUR
     ))

    (assert_sensors(sensors)
     .for_device("battery_001")
     .excluding_modules()
     .where_key("status")
     .has_no_device_class()
     .has_no_unit())


async def test_battery_module_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that battery devices create virtual battery module sensors."""
    from custom_components.sunlit.entities.battery_module_sensor import (
        SunlitBatteryModuleSensor,
    )
    from custom_components.sunlit.const import (
        DEVICE_TYPE_BATTERY,
        BATTERY_MODULE_SENSORS,
    )

    # Create specialized coordinators for battery module test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "battery_001": {
                # Module 1 data
                "battery1Soc": 85,
                "battery1Mppt1InVol": 400.5,
                "battery1Mppt1InCur": 2.5,
                "battery1Mppt1InPower": 1000,
                "battery1Mppt1Energy": 1234.5,
                "battery1capacity": 2.15,
                # Module 2 data
                "battery2Soc": 83,
                "battery2Mppt1InVol": 398.2,
                "battery2Mppt1InCur": 2.3,
                "battery2Mppt1InPower": 915,
                "battery2Mppt1Energy": 987.3,
                "battery2capacity": 2.15,
                # Module 3 data
                "battery3Soc": 87,
                "battery3Mppt1InVol": 402.1,
                "battery3Mppt1InCur": 2.7,
                "battery3Mppt1InPower": 1085,
                "battery3Mppt1Energy": 1500.2,
                "battery3capacity": 2.15,
            }
        }
    }

    device_coordinator.devices = {
        "battery_001": {
            "deviceId": "battery_001",
            "deviceType": DEVICE_TYPE_BATTERY,
            "deviceName": "Battery Storage",
        }
    }

    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find battery module sensors (should have _module_number attribute)
    battery_module_sensors = [
        s
        for s in sensors
        if hasattr(s, "_device_id")
        and s._device_id == "battery_001"
        and hasattr(s, "_module_number")  # Only battery module sensors
    ]

    # Should have 3 modules × 6 sensors per module = 18 battery module sensors
    expected_module_count = 3 * len(BATTERY_MODULE_SENSORS)
    assert (
        len(battery_module_sensors) == expected_module_count
    ), f"Expected {expected_module_count} battery module sensors, got {len(battery_module_sensors)}"

    # Verify sensor classes
    module_class_sensors = [
        s for s in battery_module_sensors if isinstance(s, SunlitBatteryModuleSensor)
    ]
    assert len(module_class_sensors) == len(
        battery_module_sensors
    ), f"All battery module sensors should use SunlitBatteryModuleSensor class"

    # Verify each module has the correct sensors
    for module_num in [1, 2, 3]:
        module_sensors = [
            s
            for s in battery_module_sensors
            if hasattr(s, "_module_number") and s._module_number == module_num
        ]
        assert len(module_sensors) == len(
            BATTERY_MODULE_SENSORS
        ), f"Module {module_num} should have {len(BATTERY_MODULE_SENSORS)} sensors"

        # Verify sensor keys for this module
        module_sensor_keys = {
            s.entity_description.key
            for s in module_sensors
            if hasattr(s, "entity_description")
        }
        expected_module_keys = {
            f"battery{module_num}{suffix}" for suffix in BATTERY_MODULE_SENSORS.keys()
        }
        assert (
            module_sensor_keys == expected_module_keys
        ), f"Module {module_num} expected keys {expected_module_keys}, got {module_sensor_keys}"

    # Verify specific sensor attributes for battery modules
    for sensor in battery_module_sensors:
        if hasattr(sensor, "entity_description"):
            key = sensor.entity_description.key
            if "Soc" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.BATTERY
                )
                assert sensor.entity_description.native_unit_of_measurement == "%"
            elif "InVol" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.VOLTAGE
                )
                assert sensor.entity_description.native_unit_of_measurement == "V"
            elif "InCur" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.CURRENT
                )
                assert sensor.entity_description.native_unit_of_measurement == "A"
            elif "InPower" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.POWER
                assert (
                    sensor.entity_description.native_unit_of_measurement
                    == UnitOfPower.WATT
                )
            elif "Energy" in key or "capacity" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.ENERGY
                )
                assert (
                    sensor.entity_description.native_unit_of_measurement
                    == UnitOfEnergy.KILO_WATT_HOUR
                )


async def test_unknown_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that unknown devices create sensors with the fallback sensor class."""
    from custom_components.sunlit.entities.unknown_device_sensor import (
        SunlitUnknownDeviceSensor,
    )

    # Create specialized coordinators for unknown device test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "unknown_001": {
                "some_data": 42,
                "other_data": "test",
            }
        }
    }

    device_coordinator.devices = {
        "unknown_001": {
            "deviceId": "unknown_001",
            "deviceType": "UNKNOWN_DEVICE_TYPE",  # This type is not in our mapping
            "deviceName": "Unknown Device",
        }
    }

    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find unknown device sensors (excluding family sensors)
    unknown_sensors = [
        s for s in sensors if hasattr(s, "_device_id") and s._device_id == "unknown_001"
    ]

    # Should have only status sensor (no device-specific sensors for unknown devices)
    assert (
        len(unknown_sensors) == 1
    ), f"Expected 1 unknown device sensor (status only), got {len(unknown_sensors)}"

    # Verify sensor class
    unknown_class_sensors = [
        s for s in unknown_sensors if isinstance(s, SunlitUnknownDeviceSensor)
    ]
    assert len(unknown_class_sensors) == len(
        unknown_sensors
    ), f"All unknown device sensors should use SunlitUnknownDeviceSensor class"

    # Verify it's the status sensor
    status_sensor = unknown_sensors[0]
    assert hasattr(status_sensor, "entity_description")
    assert status_sensor.entity_description.key == "status"
    assert status_sensor.entity_description.name == "Status"


async def test_device_type_sensor_mapping(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test the create_device_sensor factory function with different device types."""
    from custom_components.sunlit.sensor import create_device_sensor
    from custom_components.sunlit.entities.meter_sensor import SunlitMeterSensor
    from custom_components.sunlit.entities.inverter_sensor import SunlitInverterSensor
    from custom_components.sunlit.entities.battery_sensor import SunlitBatterySensor
    from custom_components.sunlit.entities.unknown_device_sensor import (
        SunlitUnknownDeviceSensor,
    )
    from custom_components.sunlit.const import (
        DEVICE_TYPE_METER,
        DEVICE_TYPE_METER_PRO,
        DEVICE_TYPE_INVERTER,
        DEVICE_TYPE_INVERTER_SOLAR,
        DEVICE_TYPE_BATTERY,
    )

    # Test data for sensor creation
    test_kwargs = {
        "coordinator": MagicMock(),
        "description": MagicMock(),
        "entry_id": "test_entry",
        "family_id": "test_family",
        "family_name": "Test Family",
        "device_id": "test_device",
        "device_info_data": {"deviceName": "Test Device"},
    }

    # Test meter device types
    meter_sensor = create_device_sensor(DEVICE_TYPE_METER, **test_kwargs)
    assert isinstance(
        meter_sensor, SunlitMeterSensor
    ), f"Expected SunlitMeterSensor, got {type(meter_sensor)}"

    meter_pro_sensor = create_device_sensor(DEVICE_TYPE_METER_PRO, **test_kwargs)
    assert isinstance(
        meter_pro_sensor, SunlitMeterSensor
    ), f"Expected SunlitMeterSensor, got {type(meter_pro_sensor)}"

    # Test inverter device types
    inverter_sensor = create_device_sensor(DEVICE_TYPE_INVERTER, **test_kwargs)
    assert isinstance(
        inverter_sensor, SunlitInverterSensor
    ), f"Expected SunlitInverterSensor, got {type(inverter_sensor)}"

    inverter_solar_sensor = create_device_sensor(
        DEVICE_TYPE_INVERTER_SOLAR, **test_kwargs
    )
    assert isinstance(
        inverter_solar_sensor, SunlitInverterSensor
    ), f"Expected SunlitInverterSensor, got {type(inverter_solar_sensor)}"

    # Test battery device type
    battery_sensor = create_device_sensor(DEVICE_TYPE_BATTERY, **test_kwargs)
    assert isinstance(
        battery_sensor, SunlitBatterySensor
    ), f"Expected SunlitBatterySensor, got {type(battery_sensor)}"

    # Test unknown device type (fallback)
    unknown_sensor = create_device_sensor("UNKNOWN_TYPE", **test_kwargs)
    assert isinstance(
        unknown_sensor, SunlitUnknownDeviceSensor
    ), f"Expected SunlitUnknownDeviceSensor, got {type(unknown_sensor)}"


async def test_inverter_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that inverter devices create the correct sensors."""
    from custom_components.sunlit.entities.inverter_sensor import SunlitInverterSensor
    from custom_components.sunlit.const import (
        DEVICE_TYPE_INVERTER,
        DEVICE_TYPE_INVERTER_SOLAR,
        INVERTER_SENSORS,
    )
    from .test_utils import assert_sensors

    # Create specialized coordinators for inverter test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "inverter_001": {
                "current_power": 2500,
                "total_power_generation": 5678.9,
                "total_yield": 6000.0,
                "daily_earnings": 12.34,
            }
        }
    }

    # Test both inverter device types
    for device_type in [DEVICE_TYPE_INVERTER, DEVICE_TYPE_INVERTER_SOLAR]:
        device_coordinator.devices = {
            "inverter_001": {
                "deviceId": "inverter_001",
                "deviceType": device_type,
                "deviceName": "Solar Inverter",
            }
        }

        mock_config_entry.add_to_hass(hass)
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                "test_family_123": {
                    "family": family_coordinator,
                    "device": device_coordinator,
                    "strategy": None,
                    "mppt": None,
                }
            }
        }

        # Create sensors
        async_add_entities = Mock()
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        assert async_add_entities.called
        sensors = async_add_entities.call_args[0][0]

        # Use builder pattern for assertions
        expected_keys = set(INVERTER_SENSORS.keys()) | {"status"}
        expected_count = len(INVERTER_SENSORS) + 1  # +1 for status

        (assert_sensors(sensors)
         .for_device("inverter_001")
         .with_count(expected_count)
         .having_keys(expected_keys)
         .with_sensor_class(SunlitInverterSensor))

        # Test specific sensor attributes with fluent API
        (assert_sensors(sensors)
         .for_device("inverter_001")
         .where_key("current_power")
         .matches_pattern(
             device_class=SensorDeviceClass.POWER,
             state_class=SensorStateClass.MEASUREMENT,
             unit=UnitOfPower.WATT
         ))

        (assert_sensors(sensors)
         .for_device("inverter_001")
         .where_key_matches(lambda k: k in ["total_power_generation", "total_yield"])
         .matches_pattern(
             device_class=SensorDeviceClass.ENERGY,
             state_class=SensorStateClass.TOTAL_INCREASING,
             unit=UnitOfEnergy.KILO_WATT_HOUR
         ))

        (assert_sensors(sensors)
         .for_device("inverter_001")
         .where_key("daily_earnings")
         .matches_pattern(
             device_class=SensorDeviceClass.MONETARY,
             unit="EUR"
         ))

        (assert_sensors(sensors)
         .for_device("inverter_001")
         .where_key("status")
         .has_no_device_class()
         .has_no_unit())

        # Clean up for next iteration
        hass.data[DOMAIN] = {}
        async_add_entities.reset_mock()


async def test_battery_module_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that battery devices create virtual battery module sensors."""
    from custom_components.sunlit.entities.battery_module_sensor import (
        SunlitBatteryModuleSensor,
    )
    from custom_components.sunlit.const import (
        DEVICE_TYPE_BATTERY,
        BATTERY_MODULE_SENSORS,
    )

    # Create specialized coordinators for battery module test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "battery_001": {
                # Module 1 data
                "battery1Soc": 85,
                "battery1Mppt1InVol": 400.5,
                "battery1Mppt1InCur": 2.5,
                "battery1Mppt1InPower": 1000,
                "battery1Mppt1Energy": 1234.5,
                "battery1capacity": 2.15,
                # Module 2 data
                "battery2Soc": 83,
                "battery2Mppt1InVol": 398.2,
                "battery2Mppt1InCur": 2.3,
                "battery2Mppt1InPower": 915,
                "battery2Mppt1Energy": 987.3,
                "battery2capacity": 2.15,
                # Module 3 data
                "battery3Soc": 87,
                "battery3Mppt1InVol": 402.1,
                "battery3Mppt1InCur": 2.7,
                "battery3Mppt1InPower": 1085,
                "battery3Mppt1Energy": 1500.2,
                "battery3capacity": 2.15,
            }
        }
    }

    device_coordinator.devices = {
        "battery_001": {
            "deviceId": "battery_001",
            "deviceType": DEVICE_TYPE_BATTERY,
            "deviceName": "Battery Storage",
        }
    }

    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find battery module sensors (should have _module_number attribute)
    battery_module_sensors = [
        s
        for s in sensors
        if hasattr(s, "_device_id")
        and s._device_id == "battery_001"
        and hasattr(s, "_module_number")  # Only battery module sensors
    ]

    # Should have 3 modules × 6 sensors per module = 18 battery module sensors
    expected_module_count = 3 * len(BATTERY_MODULE_SENSORS)
    assert (
        len(battery_module_sensors) == expected_module_count
    ), f"Expected {expected_module_count} battery module sensors, got {len(battery_module_sensors)}"

    # Verify sensor classes
    module_class_sensors = [
        s for s in battery_module_sensors if isinstance(s, SunlitBatteryModuleSensor)
    ]
    assert len(module_class_sensors) == len(
        battery_module_sensors
    ), f"All battery module sensors should use SunlitBatteryModuleSensor class"

    # Verify each module has the correct sensors
    for module_num in [1, 2, 3]:
        module_sensors = [
            s
            for s in battery_module_sensors
            if hasattr(s, "_module_number") and s._module_number == module_num
        ]
        assert len(module_sensors) == len(
            BATTERY_MODULE_SENSORS
        ), f"Module {module_num} should have {len(BATTERY_MODULE_SENSORS)} sensors"

        # Verify sensor keys for this module
        module_sensor_keys = {
            s.entity_description.key
            for s in module_sensors
            if hasattr(s, "entity_description")
        }
        expected_module_keys = {
            f"battery{module_num}{suffix}" for suffix in BATTERY_MODULE_SENSORS.keys()
        }
        assert (
            module_sensor_keys == expected_module_keys
        ), f"Module {module_num} expected keys {expected_module_keys}, got {module_sensor_keys}"

    # Verify specific sensor attributes for battery modules
    for sensor in battery_module_sensors:
        if hasattr(sensor, "entity_description"):
            key = sensor.entity_description.key
            if "Soc" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.BATTERY
                )
                assert sensor.entity_description.native_unit_of_measurement == "%"
            elif "InVol" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.VOLTAGE
                )
                assert sensor.entity_description.native_unit_of_measurement == "V"
            elif "InCur" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.CURRENT
                )
                assert sensor.entity_description.native_unit_of_measurement == "A"
            elif "InPower" in key:
                assert sensor.entity_description.device_class == SensorDeviceClass.POWER
                assert (
                    sensor.entity_description.native_unit_of_measurement
                    == UnitOfPower.WATT
                )
            elif "Energy" in key or "capacity" in key:
                assert (
                    sensor.entity_description.device_class == SensorDeviceClass.ENERGY
                )
                assert (
                    sensor.entity_description.native_unit_of_measurement
                    == UnitOfEnergy.KILO_WATT_HOUR
                )


async def test_unknown_device_sensor_creation(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test that unknown devices create sensors with the fallback sensor class."""
    from custom_components.sunlit.entities.unknown_device_sensor import (
        SunlitUnknownDeviceSensor,
    )

    # Create specialized coordinators for unknown device test
    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "test_family_123"
    family_coordinator.family_name = "Test Family"
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "test_family_123"
    device_coordinator.family_name = "Test Family"
    device_coordinator.data = {
        "devices": {
            "unknown_001": {
                "some_data": 42,
                "other_data": "test",
            }
        }
    }

    device_coordinator.devices = {
        "unknown_001": {
            "deviceId": "unknown_001",
            "deviceType": "UNKNOWN_DEVICE_TYPE",  # This type is not in our mapping
            "deviceName": "Unknown Device",
        }
    }

    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "test_family_123": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }

    # Create sensors
    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.called
    sensors = async_add_entities.call_args[0][0]

    # Find unknown device sensors (excluding family sensors)
    unknown_sensors = [
        s for s in sensors if hasattr(s, "_device_id") and s._device_id == "unknown_001"
    ]

    # Should have only status sensor (no device-specific sensors for unknown devices)
    assert (
        len(unknown_sensors) == 1
    ), f"Expected 1 unknown device sensor (status only), got {len(unknown_sensors)}"

    # Verify sensor class
    unknown_class_sensors = [
        s for s in unknown_sensors if isinstance(s, SunlitUnknownDeviceSensor)
    ]
    assert len(unknown_class_sensors) == len(
        unknown_sensors
    ), f"All unknown device sensors should use SunlitUnknownDeviceSensor class"

    # Verify it's the status sensor
    status_sensor = unknown_sensors[0]
    assert hasattr(status_sensor, "entity_description")
    assert status_sensor.entity_description.key == "status"
    assert status_sensor.entity_description.name == "Status"


async def test_device_type_sensor_mapping(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test the create_device_sensor factory function with different device types."""
    from custom_components.sunlit.sensor import create_device_sensor
    from custom_components.sunlit.entities.meter_sensor import SunlitMeterSensor
    from custom_components.sunlit.entities.inverter_sensor import SunlitInverterSensor
    from custom_components.sunlit.entities.battery_sensor import SunlitBatterySensor
    from custom_components.sunlit.entities.unknown_device_sensor import (
        SunlitUnknownDeviceSensor,
    )
    from custom_components.sunlit.const import (
        DEVICE_TYPE_METER,
        DEVICE_TYPE_METER_PRO,
        DEVICE_TYPE_INVERTER,
        DEVICE_TYPE_INVERTER_SOLAR,
        DEVICE_TYPE_BATTERY,
    )

    # Test data for sensor creation
    test_kwargs = {
        "coordinator": MagicMock(),
        "description": MagicMock(),
        "entry_id": "test_entry",
        "family_id": "test_family",
        "family_name": "Test Family",
        "device_id": "test_device",
        "device_info_data": {"deviceName": "Test Device"},
    }

    # Test meter device types
    meter_sensor = create_device_sensor(DEVICE_TYPE_METER, **test_kwargs)
    assert isinstance(
        meter_sensor, SunlitMeterSensor
    ), f"Expected SunlitMeterSensor, got {type(meter_sensor)}"

    meter_pro_sensor = create_device_sensor(DEVICE_TYPE_METER_PRO, **test_kwargs)
    assert isinstance(
        meter_pro_sensor, SunlitMeterSensor
    ), f"Expected SunlitMeterSensor, got {type(meter_pro_sensor)}"

    # Test inverter device types
    inverter_sensor = create_device_sensor(DEVICE_TYPE_INVERTER, **test_kwargs)
    assert isinstance(
        inverter_sensor, SunlitInverterSensor
    ), f"Expected SunlitInverterSensor, got {type(inverter_sensor)}"

    inverter_solar_sensor = create_device_sensor(
        DEVICE_TYPE_INVERTER_SOLAR, **test_kwargs
    )
    assert isinstance(
        inverter_solar_sensor, SunlitInverterSensor
    ), f"Expected SunlitInverterSensor, got {type(inverter_solar_sensor)}"

    # Test battery device type
    battery_sensor = create_device_sensor(DEVICE_TYPE_BATTERY, **test_kwargs)
    assert isinstance(
        battery_sensor, SunlitBatterySensor
    ), f"Expected SunlitBatterySensor, got {type(battery_sensor)}"

    # Test unknown device type (fallback)
    unknown_sensor = create_device_sensor("UNKNOWN_TYPE", **test_kwargs)
    assert isinstance(
        unknown_sensor, SunlitUnknownDeviceSensor
    ), f"Expected SunlitUnknownDeviceSensor, got {type(unknown_sensor)}"
