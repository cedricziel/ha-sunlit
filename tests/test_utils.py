"""Test utilities for the Sunlit integration tests."""

from typing import Any, Callable, Optional, Union, Set
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower


class SensorAssertionBuilder:
    """Builder-style API for asserting sensor properties in tests."""

    def __init__(self, sensors: list):
        """Initialize with a list of sensors to test."""
        self.all_sensors = sensors
        self.filtered_sensors = sensors
        self.context = "sensors"

    def for_device(self, device_id: str) -> "SensorAssertionBuilder":
        """Filter sensors for a specific device ID."""
        self.filtered_sensors = [
            s for s in self.all_sensors
            if hasattr(s, "_device_id") and s._device_id == device_id
        ]
        self.context = f"device '{device_id}'"
        return self

    def for_family(self, family_id: str) -> "SensorAssertionBuilder":
        """Filter sensors for a specific family ID."""
        self.filtered_sensors = [
            s for s in self.all_sensors
            if hasattr(s, "_family_id") and s._family_id == family_id
        ]
        self.context = f"family '{family_id}'"
        return self

    def excluding_modules(self) -> "SensorAssertionBuilder":
        """Exclude battery module sensors (those with _module_number attribute)."""
        self.filtered_sensors = [
            s for s in self.filtered_sensors
            if not hasattr(s, "_module_number")
        ]
        self.context += " (excluding modules)"
        return self

    def only_modules(self) -> "SensorAssertionBuilder":
        """Include only battery module sensors (those with _module_number attribute)."""
        self.filtered_sensors = [
            s for s in self.filtered_sensors
            if hasattr(s, "_module_number")
        ]
        self.context += " (modules only)"
        return self

    def with_descriptions(self) -> "SensorAssertionBuilder":
        """Filter to only sensors that have entity_description."""
        self.filtered_sensors = [
            s for s in self.filtered_sensors
            if hasattr(s, "entity_description") and s.entity_description
        ]
        self.context += " (with descriptions)"
        return self

    def with_count(self, expected_count: int) -> "SensorAssertionBuilder":
        """Assert the filtered sensors have the expected count."""
        actual_count = len(self.filtered_sensors)
        assert actual_count == expected_count, (
            f"Expected {expected_count} sensors for {self.context}, "
            f"but found {actual_count}"
        )
        return self

    def having_keys(self, expected_keys: Set[str]) -> "SensorAssertionBuilder":
        """Assert the filtered sensors have exactly the expected keys."""
        actual_keys = {
            s.entity_description.key for s in self.filtered_sensors
            if hasattr(s, "entity_description") and s.entity_description
        }
        assert actual_keys == expected_keys, (
            f"Expected keys {expected_keys} for {self.context}, "
            f"but found {actual_keys}"
        )
        return self

    def with_sensor_class(self, expected_class: type) -> "SensorAssertionBuilder":
        """Assert all filtered sensors are instances of the expected class."""
        typed_sensors = [
            s for s in self.filtered_sensors
            if hasattr(s, "entity_description") and s.entity_description
        ]
        class_matching_sensors = [
            s for s in typed_sensors if isinstance(s, expected_class)
        ]

        assert len(class_matching_sensors) == len(typed_sensors), (
            f"Expected all sensors for {self.context} to use {expected_class.__name__}, "
            f"but {len(typed_sensors) - len(class_matching_sensors)} don't match"
        )
        return self

    def where_key(self, key: str) -> "SensorKeyAssertions":
        """Start assertions for sensors with a specific key."""
        matching_sensors = [
            s for s in self.filtered_sensors
            if (hasattr(s, "entity_description") and
                s.entity_description and
                s.entity_description.key == key)
        ]
        return SensorKeyAssertions(matching_sensors, key, self.context)

    def where_key_contains(self, substring: str) -> "SensorKeyAssertions":
        """Start assertions for sensors whose keys contain the substring."""
        matching_sensors = [
            s for s in self.filtered_sensors
            if (hasattr(s, "entity_description") and
                s.entity_description and
                substring in s.entity_description.key)
        ]
        return SensorKeyAssertions(matching_sensors, f"containing '{substring}'", self.context)

    def where_key_matches(self, condition: Callable[[str], bool]) -> "SensorKeyAssertions":
        """Start assertions for sensors whose keys match a condition."""
        matching_sensors = [
            s for s in self.filtered_sensors
            if (hasattr(s, "entity_description") and
                s.entity_description and
                condition(s.entity_description.key))
        ]
        return SensorKeyAssertions(matching_sensors, "matching condition", self.context)

    def assert_modules(self, expected_modules: list[int], sensors_per_module: int) -> "SensorAssertionBuilder":
        """Assert that each expected module has the correct number of sensors."""
        for module_num in expected_modules:
            module_sensors = [
                s for s in self.filtered_sensors
                if hasattr(s, "_module_number") and s._module_number == module_num
            ]
            assert len(module_sensors) == sensors_per_module, (
                f"Expected module {module_num} to have {sensors_per_module} sensors, "
                f"but found {len(module_sensors)}"
            )
        return self

    def assert_module_keys(self, module_num: int, expected_suffixes: Set[str]) -> "SensorAssertionBuilder":
        """Assert that a specific module has sensors with expected key patterns."""
        module_sensors = [
            s for s in self.filtered_sensors
            if hasattr(s, "_module_number") and s._module_number == module_num
        ]

        actual_keys = {
            s.entity_description.key for s in module_sensors
            if hasattr(s, "entity_description") and s.entity_description
        }

        expected_keys = {f"battery{module_num}{suffix}" for suffix in expected_suffixes}

        assert actual_keys == expected_keys, (
            f"Expected module {module_num} to have keys {expected_keys}, "
            f"but found {actual_keys}"
        )
        return self

    def validate_all_attributes(self, attribute_validator: Callable) -> "SensorAssertionBuilder":
        """Apply a custom validation function to all filtered sensors."""
        for sensor in self.filtered_sensors:
            if hasattr(sensor, "entity_description") and sensor.entity_description:
                attribute_validator(sensor)
        return self


class SensorKeyAssertions:
    """Assertion builder for sensors filtered by key patterns."""

    def __init__(self, sensors: list, key_description: str, context: str):
        self.sensors = sensors
        self.key_description = key_description
        self.context = context

    def has_device_class(self, device_class: SensorDeviceClass) -> "SensorKeyAssertions":
        """Assert sensors have the expected device class."""
        for sensor in self.sensors:
            assert sensor.entity_description.device_class == device_class, (
                f"Expected device class {device_class} for sensor key {self.key_description} "
                f"in {self.context}, but found {sensor.entity_description.device_class}"
            )
        return self

    def has_state_class(self, state_class: Optional[SensorStateClass]) -> "SensorKeyAssertions":
        """Assert sensors have the expected state class."""
        for sensor in self.sensors:
            assert sensor.entity_description.state_class == state_class, (
                f"Expected state class {state_class} for sensor key {self.key_description} "
                f"in {self.context}, but found {sensor.entity_description.state_class}"
            )
        return self

    def has_unit(self, unit: Optional[str]) -> "SensorKeyAssertions":
        """Assert sensors have the expected unit of measurement."""
        for sensor in self.sensors:
            assert sensor.entity_description.native_unit_of_measurement == unit, (
                f"Expected unit {unit} for sensor key {self.key_description} "
                f"in {self.context}, but found {sensor.entity_description.native_unit_of_measurement}"
            )
        return self

    def has_no_device_class(self) -> "SensorKeyAssertions":
        """Assert sensors have no device class (None)."""
        return self.has_device_class(None)

    def has_no_unit(self) -> "SensorKeyAssertions":
        """Assert sensors have no unit of measurement (None)."""
        return self.has_unit(None)

    def matches_pattern(
        self,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
        unit: Optional[str] = None
    ) -> "SensorKeyAssertions":
        """Assert sensors match a complete pattern of attributes."""
        if device_class is not None:
            self.has_device_class(device_class)
        if state_class is not None:
            self.has_state_class(state_class)
        if unit is not None:
            self.has_unit(unit)
        return self


def assert_sensors(sensors: list) -> SensorAssertionBuilder:
    """Entry point for fluent sensor assertions."""
    return SensorAssertionBuilder(sensors)
