"""Test for issue #33 fix: total_solar_power should use inverter power, not battery output."""

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorEntityDescription

from custom_components.sunlit.entities.family_sensor import SunlitFamilySensor


def test_family_sensor_prioritizes_aggregates_over_family_data():
    """Test that family sensor prioritizes aggregates data over family data.

    This ensures total_solar_power uses device coordinator's aggregates
    (actual solar power) instead of family coordinator's data (which might
    contain battery output power).
    """

    # Create a coordinator that has both family and aggregates data
    # This simulates device coordinator which might have both sections
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "family": {
            "total_output_power": 3000,  # Battery output (wrong value if used for solar)
            "some_other_field": "value",
        },
        "aggregates": {
            "total_solar_power": 1500,  # Solar power from inverters (correct value)
            "total_solar_energy": 1234.5,
        }
    }

    # Create sensor description for total_solar_power
    description = SensorEntityDescription(
        key="total_solar_power",
        name="Total Solar Power",
    )

    # Create the sensor
    sensor = SunlitFamilySensor(
        coordinator=coordinator,
        description=description,
        entry_id="test_entry",
        family_id="test_family",
        family_name="Test Family",
    )

    # Test that it returns the value from aggregates, not family
    assert sensor.native_value == 1500, \
        f"Should return 1500 from aggregates, got {sensor.native_value}"

    # Test availability checks aggregates first
    assert sensor.available is True, \
        "Sensor should be available when key exists in aggregates"


def test_family_sensor_with_only_family_data():
    """Test sensor behavior when only family data exists (no aggregates)."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "family": {
            "total_output_power": 3000,  # Battery output power
            "average_battery_level": 75,
        }
    }

    # Try to create a total_solar_power sensor
    description = SensorEntityDescription(
        key="total_solar_power",
        name="Total Solar Power",
    )

    sensor = SunlitFamilySensor(
        coordinator=coordinator,
        description=description,
        entry_id="test_entry",
        family_id="test_family",
        family_name="Test Family",
    )

    # Since total_solar_power doesn't exist in family data, should return None
    assert sensor.native_value is None, \
        f"Should return None when key doesn't exist in family data, got {sensor.native_value}"

    # And sensor should not be available
    assert sensor.available is False, \
        "Sensor should not be available when key doesn't exist in any data section"


def test_family_sensor_correct_data_section_priority():
    """Test that sensor checks data sections in correct priority order."""

    coordinator = MagicMock()
    coordinator.last_update_success = True

    # Test with all sections present - aggregates should win
    coordinator.data = {
        "aggregates": {"test_key": "aggregates_value"},
        "strategy": {"test_key": "strategy_value"},
        "mppt_energy": {"test_key": "mppt_value"},
        "family": {"test_key": "family_value"},
    }

    description = SensorEntityDescription(key="test_key", name="Test")
    sensor = SunlitFamilySensor(
        coordinator=coordinator,
        description=description,
        entry_id="test",
        family_id="test",
        family_name="Test",
    )

    assert sensor.native_value == "aggregates_value", \
        "Aggregates should have highest priority"

    # Remove aggregates, strategy should win
    coordinator.data = {
        "strategy": {"test_key": "strategy_value"},
        "mppt_energy": {"test_key": "mppt_value"},
        "family": {"test_key": "family_value"},
    }

    assert sensor.native_value == "strategy_value", \
        "Strategy should have second priority"

    # Remove strategy, mppt_energy should win
    coordinator.data = {
        "mppt_energy": {"test_key": "mppt_value"},
        "family": {"test_key": "family_value"},
    }

    assert sensor.native_value == "mppt_value", \
        "MPPT energy should have third priority"

    # Only family left
    coordinator.data = {
        "family": {"test_key": "family_value"},
    }

    assert sensor.native_value == "family_value", \
        "Family should be last priority"


def test_total_output_vs_solar_power_separation():
    """Test that total_output_power and total_solar_power are correctly separated."""

    # Simulate family coordinator with battery output power
    family_coordinator = MagicMock()
    family_coordinator.last_update_success = True
    family_coordinator.data = {
        "family": {
            "total_output_power": 2500,  # Battery output to system
        }
    }

    # Simulate device coordinator with solar power
    device_coordinator = MagicMock()
    device_coordinator.last_update_success = True
    device_coordinator.data = {
        "aggregates": {
            "total_solar_power": 1800,  # Solar generation from inverters
        }
    }

    # Create sensor for total_output_power (battery) using family coordinator
    output_description = SensorEntityDescription(
        key="total_output_power",
        name="Total Output Power",
    )
    output_sensor = SunlitFamilySensor(
        coordinator=family_coordinator,  # Uses family coordinator
        description=output_description,
        entry_id="test",
        family_id="test",
        family_name="Test",
    )

    # Create sensor for total_solar_power (solar) using device coordinator
    solar_description = SensorEntityDescription(
        key="total_solar_power",
        name="Total Solar Power",
    )
    solar_sensor = SunlitFamilySensor(
        coordinator=device_coordinator,  # Uses device coordinator
        description=solar_description,
        entry_id="test",
        family_id="test",
        family_name="Test",
    )

    # Verify they return different values from different sources
    assert output_sensor.native_value == 2500, \
        f"total_output_power should be 2500 from family data, got {output_sensor.native_value}"

    assert solar_sensor.native_value == 1800, \
        f"total_solar_power should be 1800 from aggregates, got {solar_sensor.native_value}"

    # Verify both are available
    assert output_sensor.available is True
    assert solar_sensor.available is True
