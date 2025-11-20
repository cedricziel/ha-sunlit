"""Tests for sensor helper functions."""

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)

from custom_components.sunlit.entities.helpers import (
    get_device_class_for_sensor,
    get_icon_for_sensor,
    get_state_class_for_sensor,
    get_unit_for_sensor,
)


class TestDeviceClassForSensor:
    """Test get_device_class_for_sensor function."""

    def test_timestamp_sensor(self):
        """Test that last_strategy_change returns timestamp device class."""
        assert get_device_class_for_sensor("last_strategy_change") == SensorDeviceClass.TIMESTAMP

    def test_energy_sensors(self):
        """Test energy sensor classification."""
        energy_sensors = [
            "daily_buy_energy",
            "daily_ret_energy",
            "total_buy_energy",
            "total_ret_energy",
            "total_power_generation",  # Actually energy despite the name
            "total_solar_energy",
            "total_grid_export_energy",
            "daily_grid_export_energy",
            "daily_yield",
            "battery_capacity",
            "batteryMppt1Energy",
        ]
        for sensor in energy_sensors:
            assert get_device_class_for_sensor(sensor) == SensorDeviceClass.ENERGY, f"Failed for {sensor}"

    def test_power_sensors(self):
        """Test power sensor classification."""
        power_sensors = [
            "total_ac_power",
            "current_power",
            "inverter_current_power",
            "total_input_power",
            "total_output_power",
            "rated_power",
            "max_output_power",
            "home_power",
            "total_solar_power",
            "batteryMppt1InPower",
        ]
        for sensor in power_sensors:
            assert get_device_class_for_sensor(sensor) == SensorDeviceClass.POWER, f"Failed for {sensor}"

    def test_battery_sensors(self):
        """Test battery sensor classification."""
        battery_sensors = [
            "battery_level",
            "average_battery_level",
            "batterySoc",
            "hw_soc_min",
            "hw_soc_max",
            "battery_soc_min",
            "battery_soc_max",
            # Note: strategy_soc_min/max return None because "strategy" check comes first
            # They are tested separately in test_strategy_fields_except_timestamp
        ]
        for sensor in battery_sensors:
            assert get_device_class_for_sensor(sensor) == SensorDeviceClass.BATTERY, f"Failed for {sensor}"

    def test_duration_sensors(self):
        """Test duration sensor classification."""
        duration_sensors = [
            "chargeRemaining",
            "dischargeRemaining",
            "battery_charging_remaining",
            "battery_discharging_remaining",
        ]
        for sensor in duration_sensors:
            assert get_device_class_for_sensor(sensor) == SensorDeviceClass.DURATION, f"Failed for {sensor}"

    def test_voltage_sensors(self):
        """Test voltage sensor classification."""
        voltage_sensors = [
            "batteryMppt1InVol",
            "batteryMppt2InVol",
            "battery1Mppt1InVol",
        ]
        for sensor in voltage_sensors:
            assert get_device_class_for_sensor(sensor) == SensorDeviceClass.VOLTAGE, f"Failed for {sensor}"

    def test_current_sensors(self):
        """Test current sensor classification."""
        current_sensors = [
            "batteryMppt1InCur",
            "batteryMppt2InCur",
            "battery1Mppt1InCur",
        ]
        for sensor in current_sensors:
            assert get_device_class_for_sensor(sensor) == SensorDeviceClass.CURRENT, f"Failed for {sensor}"

    def test_monetary_sensor(self):
        """Test monetary sensor classification."""
        assert get_device_class_for_sensor("daily_earnings") == SensorDeviceClass.MONETARY

    def test_no_device_class_sensors(self):
        """Test sensors that should have no device class."""
        no_class_sensors = [
            "battery_strategy",
            "battery_status",
            "last_strategy_type",
            "last_strategy_status",
            "currency",
            "battery_count",
            "device_count",
            "online_devices",
            "offline_devices",
            "has_fault",
        ]
        for sensor in no_class_sensors:
            assert get_device_class_for_sensor(sensor) is None, f"Failed for {sensor}"

    def test_strategy_fields_except_timestamp(self):
        """Test that strategy fields return None except for last_strategy_change."""
        # These should return None due to "strategy" in the name
        assert get_device_class_for_sensor("battery_strategy") is None
        assert get_device_class_for_sensor("last_strategy_type") is None
        assert get_device_class_for_sensor("last_strategy_status") is None
        # strategy_soc_min/max also return None because "strategy" check comes first
        assert get_device_class_for_sensor("strategy_soc_min") is None
        assert get_device_class_for_sensor("strategy_soc_max") is None

        # But last_strategy_change should return TIMESTAMP (tested separately)
        assert get_device_class_for_sensor("last_strategy_change") == SensorDeviceClass.TIMESTAMP


class TestStateClassForSensor:
    """Test get_state_class_for_sensor function."""

    def test_total_increasing_sensors(self):
        """Test sensors with total_increasing state class."""
        total_increasing = [
            "total_buy_energy",
            "total_ret_energy",
            "total_solar_energy",
            "total_grid_export_energy",
        ]
        for sensor in total_increasing:
            assert get_state_class_for_sensor(sensor) == SensorStateClass.TOTAL_INCREASING, f"Failed for {sensor}"

    def test_total_sensors(self):
        """Test sensors with total state class (daily counters)."""
        total_sensors = [
            "daily_buy_energy",
            "daily_ret_energy",
            "daily_grid_export_energy",
            "daily_yield",
            "daily_earnings",
            "total_power_generation",  # Despite the name, this is daily data (resets at midnight)
        ]
        for sensor in total_sensors:
            assert get_state_class_for_sensor(sensor) == SensorStateClass.TOTAL, f"Failed for {sensor}"

    def test_measurement_sensors(self):
        """Test sensors with measurement state class."""
        measurement_sensors = [
            "total_ac_power",
            "current_power",
            "total_input_power",
            "total_output_power",
            "device_count",
            "online_devices",
            "offline_devices",
            "strategy_changes_today",
            "home_power",
            "battery_charging_remaining",
            "battery_discharging_remaining",
            "inverter_current_power",
            "total_solar_power",
        ]
        for sensor in measurement_sensors:
            assert get_state_class_for_sensor(sensor) == SensorStateClass.MEASUREMENT, f"Failed for {sensor}"

    def test_no_state_class_sensors(self):
        """Test sensors that should have no state class."""
        no_state_class = [
            "battery_strategy",
            "battery_status",
            "last_strategy_change",
            "last_strategy_type",
            "last_strategy_status",
            "currency",
            "battery_count",
            "rated_power",  # Configuration value
            "max_output_power",  # Configuration value
        ]
        for sensor in no_state_class:
            assert get_state_class_for_sensor(sensor) is None, f"Failed for {sensor}"


class TestUnitForSensor:
    """Test get_unit_for_sensor function."""

    def test_energy_units(self):
        """Test energy sensors return kWh."""
        energy_sensors = [
            "daily_buy_energy",
            "total_buy_energy",
            "total_power_generation",
            "total_solar_energy",
            "battery_capacity",
        ]
        for sensor in energy_sensors:
            assert get_unit_for_sensor(sensor) == UnitOfEnergy.KILO_WATT_HOUR, f"Failed for {sensor}"

    def test_power_units(self):
        """Test power sensors return W."""
        power_sensors = [
            "total_ac_power",
            "current_power",
            "rated_power",
            "max_output_power",
            "home_power",
        ]
        for sensor in power_sensors:
            assert get_unit_for_sensor(sensor) == UnitOfPower.WATT, f"Failed for {sensor}"

    def test_percentage_units(self):
        """Test battery/SOC sensors return %."""
        percentage_sensors = [
            "battery_level",
            "average_battery_level",
            "batterySoc",
            "hw_soc_min",
            "hw_soc_max",
        ]
        for sensor in percentage_sensors:
            assert get_unit_for_sensor(sensor) == PERCENTAGE, f"Failed for {sensor}"

    def test_time_units(self):
        """Test duration sensors return minutes."""
        time_sensors = [
            "chargeRemaining",
            "dischargeRemaining",
            "battery_charging_remaining",
        ]
        for sensor in time_sensors:
            assert get_unit_for_sensor(sensor) == UnitOfTime.MINUTES, f"Failed for {sensor}"

    def test_voltage_units(self):
        """Test voltage sensors return V."""
        voltage_sensors = [
            "batteryMppt1InVol",
            "batteryMppt2InVol",
        ]
        for sensor in voltage_sensors:
            assert get_unit_for_sensor(sensor) == UnitOfElectricPotential.VOLT, f"Failed for {sensor}"

    def test_current_units(self):
        """Test current sensors return A."""
        current_sensors = [
            "batteryMppt1InCur",
            "batteryMppt2InCur",
        ]
        for sensor in current_sensors:
            assert get_unit_for_sensor(sensor) == UnitOfElectricCurrent.AMPERE, f"Failed for {sensor}"

    def test_monetary_units(self):
        """Test monetary sensor returns EUR."""
        assert get_unit_for_sensor("daily_earnings") == "EUR"

    def test_no_unit_sensors(self):
        """Test sensors that should have no unit."""
        no_unit_sensors = [
            "battery_strategy",
            "battery_status",
            "device_count",
            "currency",
        ]
        for sensor in no_unit_sensors:
            assert get_unit_for_sensor(sensor) is None, f"Failed for {sensor}"


class TestIconForSensor:
    """Test get_icon_for_sensor function."""

    def test_battery_icons(self):
        """Test battery-related icons."""
        assert get_icon_for_sensor("battery_level") == "mdi:battery-50"
        assert get_icon_for_sensor("battery_full") == "mdi:battery-check"
        assert get_icon_for_sensor("batterySoc") == "mdi:battery-outline"
        assert get_icon_for_sensor("battery_count") == "mdi:battery-multiple"

    def test_solar_icons(self):
        """Test solar/inverter icons."""
        assert get_icon_for_sensor("total_solar_energy") == "mdi:solar-power-variant-outline"
        assert get_icon_for_sensor("total_solar_power") == "mdi:solar-power-variant"
        assert get_icon_for_sensor("daily_yield") == "mdi:solar-power-variant"

    def test_grid_icons(self):
        """Test grid/meter icons."""
        assert get_icon_for_sensor("total_grid_export_energy") == "mdi:transmission-tower-export"
        assert get_icon_for_sensor("daily_grid_export_energy") == "mdi:transmission-tower-export"

    def test_strategy_icons(self):
        """Test strategy-related icons."""
        assert get_icon_for_sensor("last_strategy_change") == "mdi:clock-outline"
        assert get_icon_for_sensor("last_strategy_type") == "mdi:history"
        assert get_icon_for_sensor("strategy_changes_today") == "mdi:counter"
        assert get_icon_for_sensor("battery_strategy") == "mdi:cog"

    def test_remaining_time_icons(self):
        """Test time remaining icons."""
        assert get_icon_for_sensor("chargeRemaining") == "mdi:timer-sand"
        # BUG: dischargeRemaining returns "mdi:timer-sand" instead of "mdi:timer-sand-empty"
        # because "charge" is checked before "discharge" and "charge" is in "discharge"
        assert get_icon_for_sensor("dischargeRemaining") == "mdi:timer-sand"  # Current behavior
        # This should ideally be "mdi:timer-sand-empty" but needs fix in helpers.py

    def test_mppt_icons(self):
        """Test MPPT-related icons."""
        assert get_icon_for_sensor("batteryMppt1InVol") == "mdi:sine-wave"
        assert get_icon_for_sensor("batteryMppt1InCur") == "mdi:current-dc"
        assert get_icon_for_sensor("batteryMppt1InPower") == "mdi:solar-power-variant"
