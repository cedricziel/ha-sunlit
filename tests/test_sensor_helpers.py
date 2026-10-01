"""Tests for sensor helper functions."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
import pytest

from custom_components.sunlit.entities.helpers import (
    get_device_class_for_sensor,
    get_entity_category,
    get_icon_for_sensor,
    get_options_for_sensor,
    get_state_class_for_sensor,
    get_suggested_display_precision,
    get_unit_for_sensor,
)


class TestDeviceClassForSensor:
    """Test get_device_class_for_sensor function."""

    def test_timestamp_sensor(self):
        """Test that last_strategy_change returns timestamp device class."""
        assert (
            get_device_class_for_sensor("last_strategy_change")
            == SensorDeviceClass.TIMESTAMP
        )

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
            "batteryMppt1Energy",
        ]
        for sensor in energy_sensors:
            assert (
                get_device_class_for_sensor(sensor) == SensorDeviceClass.ENERGY
            ), f"Failed for {sensor}"

    def test_capacity_is_not_energy(self):
        """Nominal capacity is a static spec, not metered energy (no device class)."""
        assert get_device_class_for_sensor("battery_capacity") is None
        assert get_device_class_for_sensor("battery1capacity") is None

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
            assert (
                get_device_class_for_sensor(sensor) == SensorDeviceClass.POWER
            ), f"Failed for {sensor}"

    def test_battery_sensors(self):
        """Only metered, fluctuating SOC is BATTERY (issue: validate sensors)."""
        battery_sensors = [
            "battery_level",
            "average_battery_level",
            "batterySoc",
            "battery1Soc",
            "battery2Soc",
            # Head unit real SOC from the local channel (t592)
            "head_battery_soc",
        ]
        for sensor in battery_sensors:
            assert (
                get_device_class_for_sensor(sensor) == SensorDeviceClass.BATTERY
            ), f"Failed for {sensor}"

    def test_soc_limits_are_not_battery(self):
        """SOC limit thresholds are config values, not metered battery levels."""
        soc_limits = [
            "hw_soc_min",
            "hw_soc_max",
            "battery_soc_min",
            "battery_soc_max",
            "current_soc_min",
            "current_soc_max",
            "strategy_soc_min",
            "strategy_soc_max",
        ]
        for sensor in soc_limits:
            assert get_device_class_for_sensor(sensor) is None, f"Failed for {sensor}"

    def test_duration_sensors(self):
        """Test duration sensor classification."""
        duration_sensors = [
            "chargeRemaining",
            "dischargeRemaining",
            "battery_charging_remaining",
            "battery_discharging_remaining",
        ]
        for sensor in duration_sensors:
            assert (
                get_device_class_for_sensor(sensor) == SensorDeviceClass.DURATION
            ), f"Failed for {sensor}"

    def test_voltage_sensors(self):
        """Test voltage sensor classification."""
        voltage_sensors = [
            "batteryMppt1InVol",
            "batteryMppt2InVol",
            "battery1Mppt1InVol",
        ]
        for sensor in voltage_sensors:
            assert (
                get_device_class_for_sensor(sensor) == SensorDeviceClass.VOLTAGE
            ), f"Failed for {sensor}"

    def test_current_sensors(self):
        """Test current sensor classification."""
        current_sensors = [
            "batteryMppt1InCur",
            "batteryMppt2InCur",
            "battery1Mppt1InCur",
        ]
        for sensor in current_sensors:
            assert (
                get_device_class_for_sensor(sensor) == SensorDeviceClass.CURRENT
            ), f"Failed for {sensor}"

    def test_monetary_sensor(self):
        """Test monetary sensor classification."""
        assert (
            get_device_class_for_sensor("daily_earnings") == SensorDeviceClass.MONETARY
        )

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
        assert (
            get_device_class_for_sensor("last_strategy_change")
            == SensorDeviceClass.TIMESTAMP
        )


class TestStateClassForSensor:
    """Test get_state_class_for_sensor function."""

    def test_total_increasing_sensors(self):
        """Energy counters use TOTAL_INCREASING — incl. daily ones.

        Daily energy counters reset at midnight; TOTAL_INCREASING auto-detects
        the reset (value drops to ~0), so no last_reset attribute is needed and
        the long-term statistics stay correct across the reset.
        """
        total_increasing = [
            "total_buy_energy",
            "total_ret_energy",
            "total_solar_energy",
            "total_grid_export_energy",
            # daily energy counters (previously TOTAL without last_reset)
            "daily_buy_energy",
            "daily_ret_energy",
            "daily_grid_export_energy",
            "daily_yield",
            "total_power_generation",  # daily generation despite the name
        ]
        for sensor in total_increasing:
            assert (
                get_state_class_for_sensor(sensor) == SensorStateClass.TOTAL_INCREASING
            ), f"Failed for {sensor}"

    def test_total_sensors(self):
        """Only daily_earnings uses TOTAL (MONETARY forbids TOTAL_INCREASING).

        lifetime_earnings is integration-managed long-term statistics (no
        state_class) — covered by TestLifetimeStatsSensors.
        """
        total_sensors = [
            "daily_earnings",  # resets daily -> carries a last_reset (see entity)
        ]
        for sensor in total_sensors:
            assert (
                get_state_class_for_sensor(sensor) == SensorStateClass.TOTAL
            ), f"Failed for {sensor}"

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
            assert (
                get_state_class_for_sensor(sensor) == SensorStateClass.MEASUREMENT
            ), f"Failed for {sensor}"

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
        ]
        for sensor in no_state_class:
            assert get_state_class_for_sensor(sensor) is None, f"Failed for {sensor}"

    def test_rated_and_max_power_have_measurement(self):
        """rated_power / max_output_power are POWER sensors -> MEASUREMENT."""
        assert get_state_class_for_sensor("rated_power") == SensorStateClass.MEASUREMENT
        assert (
            get_state_class_for_sensor("max_output_power")
            == SensorStateClass.MEASUREMENT
        )


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
            assert (
                get_unit_for_sensor(sensor) == UnitOfEnergy.KILO_WATT_HOUR
            ), f"Failed for {sensor}"

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
            assert (
                get_unit_for_sensor(sensor) == UnitOfPower.WATT
            ), f"Failed for {sensor}"

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
            assert (
                get_unit_for_sensor(sensor) == UnitOfTime.MINUTES
            ), f"Failed for {sensor}"

    def test_voltage_units(self):
        """Test voltage sensors return V."""
        voltage_sensors = [
            "batteryMppt1InVol",
            "batteryMppt2InVol",
        ]
        for sensor in voltage_sensors:
            assert (
                get_unit_for_sensor(sensor) == UnitOfElectricPotential.VOLT
            ), f"Failed for {sensor}"

    def test_current_units(self):
        """Test current sensors return A."""
        current_sensors = [
            "batteryMppt1InCur",
            "batteryMppt2InCur",
        ]
        for sensor in current_sensors:
            assert (
                get_unit_for_sensor(sensor) == UnitOfElectricCurrent.AMPERE
            ), f"Failed for {sensor}"

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
        assert (
            get_icon_for_sensor("total_solar_energy")
            == "mdi:solar-power-variant-outline"
        )
        assert get_icon_for_sensor("total_solar_power") == "mdi:solar-power-variant"
        assert get_icon_for_sensor("daily_yield") == "mdi:solar-power-variant"

    def test_grid_icons(self):
        """Test grid/meter icons."""
        assert (
            get_icon_for_sensor("total_grid_export_energy")
            == "mdi:transmission-tower-export"
        )
        assert (
            get_icon_for_sensor("daily_grid_export_energy")
            == "mdi:transmission-tower-export"
        )

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
        assert (
            get_icon_for_sensor("dischargeRemaining") == "mdi:timer-sand"
        )  # Current behavior
        # This should ideally be "mdi:timer-sand-empty" but needs fix in helpers.py

    def test_mppt_icons(self):
        """Test MPPT-related icons."""
        assert get_icon_for_sensor("batteryMppt1InVol") == "mdi:sine-wave"
        assert get_icon_for_sensor("batteryMppt1InCur") == "mdi:current-dc"
        assert get_icon_for_sensor("batteryMppt1InPower") == "mdi:solar-power-variant"


class TestLifetimeStatsSensors:
    """Test classification of lifetime yield & earnings sensors (issue #155)."""

    def test_lifetime_yield(self):
        """lifetime_yield is energy in kWh with integration-managed statistics.

        It has no state_class: the integration owns its long-term statistics
        (historical backfill + ongoing hourly import) so the recorder must not
        also auto-compile them. See statistics.py.
        """
        assert get_device_class_for_sensor("lifetime_yield") == SensorDeviceClass.ENERGY
        assert get_state_class_for_sensor("lifetime_yield") is None
        assert get_unit_for_sensor("lifetime_yield") == UnitOfEnergy.KILO_WATT_HOUR
        assert get_icon_for_sensor("lifetime_yield") == "mdi:solar-power-variant"

    def test_lifetime_earnings(self):
        """lifetime_earnings is monetary with integration-managed statistics."""
        assert (
            get_device_class_for_sensor("lifetime_earnings")
            == SensorDeviceClass.MONETARY
        )
        assert get_state_class_for_sensor("lifetime_earnings") is None
        assert get_unit_for_sensor("lifetime_earnings") == "EUR"
        assert get_icon_for_sensor("lifetime_earnings") == "mdi:cash"


class TestSensorMetadataExtras:
    """Validate entity_category, ENUM options, and display precision."""

    @pytest.mark.parametrize("key", ["battery_capacity", "battery1capacity"])
    def test_capacity_is_diagnostic(self, key):
        """Nominal capacity is a static spec -> diagnostic, no device class."""
        assert get_entity_category(key) == EntityCategory.DIAGNOSTIC
        assert get_device_class_for_sensor(key) is None

    def test_metered_sensors_are_not_diagnostic(self):
        """Live telemetry stays in the default category."""
        assert get_entity_category("batterySoc") is None
        assert get_entity_category("stored_energy") is None

    @pytest.mark.parametrize(
        "key",
        ["battery_device_status", "inverter_device_status", "meter_device_status"],
    )
    def test_device_status_is_enum(self, key):
        """Device status is a bounded ENUM (no unit/state_class)."""
        assert get_device_class_for_sensor(key) == SensorDeviceClass.ENUM
        assert get_options_for_sensor(key) == ["Online", "Offline", "NotExist"]
        assert get_unit_for_sensor(key) is None
        assert get_state_class_for_sensor(key) is None

    def test_is_daily_reset_total(self):
        """Only the daily MONETARY counter needs a last_reset (TOTAL + resets)."""
        from custom_components.sunlit.entities.helpers import is_daily_reset_total

        assert is_daily_reset_total("daily_earnings") is True
        assert is_daily_reset_total("lifetime_earnings") is False  # never resets
        # Daily ENERGY counters are TOTAL_INCREASING, not TOTAL -> no last_reset.
        assert is_daily_reset_total("daily_yield") is False
        assert is_daily_reset_total("daily_grid_export_energy") is False

    @pytest.mark.parametrize(
        ("key", "precision"),
        [
            ("stored_energy", 2),
            ("lifetime_yield", 2),
            ("daily_earnings", 2),
            ("batteryMppt1InPower", 1),
            ("batteryMppt1InVol", 1),
            ("batteryMppt1InCur", 2),
            ("batterySoc", 1),
            ("battery_capacity", 2),  # kWh, no device class
            ("chargeRemaining", 0),
            ("device_count", None),
            ("battery_strategy", None),
        ],
    )
    def test_suggested_display_precision(self, key, precision):
        assert get_suggested_display_precision(key) == precision


class TestLocalOnlySensors:
    """Validate metadata for the local-channel-only battery sensors."""

    def test_head_battery_soc_is_metered_battery(self):
        """t592 -> head_battery_soc behaves like the per-module SOC keys."""
        assert (
            get_device_class_for_sensor("head_battery_soc") == SensorDeviceClass.BATTERY
        )
        assert (
            get_state_class_for_sensor("head_battery_soc")
            == SensorStateClass.MEASUREMENT
        )
        assert get_unit_for_sensor("head_battery_soc") == PERCENTAGE
        # Primary telemetry, not diagnostic.
        assert get_entity_category("head_battery_soc") is None

    def test_daily_energy_keys_are_total_increasing(self):
        """Local daily energy counters behave like the cloud daily_yield."""
        for key in ("daily_pv_energy", "daily_output_energy"):
            assert get_device_class_for_sensor(key) == SensorDeviceClass.ENERGY, key
            assert (
                get_state_class_for_sensor(key) == SensorStateClass.TOTAL_INCREASING
            ), key
            assert get_unit_for_sensor(key) == UnitOfEnergy.KILO_WATT_HOUR, key

    def test_wifi_rssi_is_diagnostic_signal_strength(self):
        """t475 -> wifi_rssi: SIGNAL_STRENGTH device class, dB unit, diagnostic."""
        assert (
            get_device_class_for_sensor("wifi_rssi")
            == SensorDeviceClass.SIGNAL_STRENGTH
        )
        assert get_state_class_for_sensor("wifi_rssi") == SensorStateClass.MEASUREMENT
        assert get_unit_for_sensor("wifi_rssi") == SIGNAL_STRENGTH_DECIBELS
        assert get_entity_category("wifi_rssi") == EntityCategory.DIAGNOSTIC


class TestStoredEnergySensors:
    """Test classification of battery stored-energy sensors (issue #190)."""

    @pytest.mark.parametrize(
        "key",
        ["stored_energy", "total_stored_energy", "battery1StoredEnergy"],
    )
    def test_stored_energy_classification(self, key):
        """Stored energy is ENERGY_STORAGE / MEASUREMENT / kWh."""
        assert (
            get_device_class_for_sensor(key) == SensorDeviceClass.ENERGY_STORAGE
        ), f"Failed device_class for {key}"
        assert (
            get_state_class_for_sensor(key) == SensorStateClass.MEASUREMENT
        ), f"Failed state_class for {key}"
        assert (
            get_unit_for_sensor(key) == UnitOfEnergy.KILO_WATT_HOUR
        ), f"Failed unit for {key}"

    def test_stored_energy_not_total_increasing(self):
        """Regression: stored energy must not be classified as a meter."""
        assert get_state_class_for_sensor("stored_energy") != (
            SensorStateClass.TOTAL_INCREASING
        )


class TestElectricityPriceSensors:
    """Test classification of dynamic tariff price sensors (issue #154)."""

    @pytest.mark.parametrize(
        "key",
        [
            "electricity_price",
            "electricity_price_avg",
            "electricity_price_high",
            "electricity_price_low",
        ],
    )
    def test_numeric_price(self, key):
        """Numeric price sensors are ct/kWh measurements with no device class."""
        assert get_device_class_for_sensor(key) is None
        assert get_state_class_for_sensor(key) == SensorStateClass.MEASUREMENT
        assert get_unit_for_sensor(key) == "ct/kWh"
        assert get_icon_for_sensor(key) == "mdi:cash-multiple"

    def test_price_tag(self):
        """The price tag is a bounded ENUM sensor (no unit/state_class)."""
        from custom_components.sunlit.entities.helpers import get_options_for_sensor

        assert (
            get_device_class_for_sensor("electricity_price_tag")
            == SensorDeviceClass.ENUM
        )
        assert get_state_class_for_sensor("electricity_price_tag") is None
        assert get_unit_for_sensor("electricity_price_tag") is None
        assert get_options_for_sensor("electricity_price_tag") == [
            "VERY_CHEAP",
            "CHEAP",
            "NORMAL",
            "EXPENSIVE",
            "VERY_EXPENSIVE",
        ]
        assert get_icon_for_sensor("electricity_price_tag") == "mdi:tag-outline"


class TestSelfConsumptionSensors:
    """Test classification of energy self-consumption sensors (issue #168)."""

    @pytest.mark.parametrize("key", ["self_use_rate", "self_sufficiency_rate"])
    def test_rates(self, key):
        """Self-use / self-sufficiency are % measurements, no device class."""
        assert get_device_class_for_sensor(key) is None
        assert get_state_class_for_sensor(key) == SensorStateClass.MEASUREMENT
        assert get_unit_for_sensor(key) == PERCENTAGE
        assert get_icon_for_sensor(key) is not None


class TestDeviceDiagnosticSensors:
    """Test classification of device-detail diagnostic sensors (issue #159)."""

    def test_text_diagnostics_have_no_device_class(self):
        """ssid / system status are plain text sensors."""
        for key in ("wifi_ssid", "system_status"):
            assert get_device_class_for_sensor(key) is None
            assert get_state_class_for_sensor(key) is None
            assert get_unit_for_sensor(key) is None

    def test_diagnostic_icons_resolve_for_battery_device(self):
        """Icons must resolve before the battery device_type branch."""
        assert get_icon_for_sensor("wifi_ssid", "ENERGY_STORAGE_BATTERY") == "mdi:wifi"
        assert (
            get_icon_for_sensor("system_status", "ENERGY_STORAGE_BATTERY")
            == "mdi:information-outline"
        )
