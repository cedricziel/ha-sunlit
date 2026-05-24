"""Helper functions for Sunlit sensors."""

import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)

# Text sensors with a known, bounded value set -> ENUM device class + options.
# Only fields whose values are documented enums in the API are listed; strategy
# and battery-status fields are intentionally excluded (their value sets are not
# reliably bounded, so ENUM would emit "state not in options" warnings).
ENUM_SENSOR_OPTIONS: dict[str, list[str]] = {
    "electricity_price_tag": [
        "VERY_CHEAP",
        "CHEAP",
        "NORMAL",
        "EXPENSIVE",
        "VERY_EXPENSIVE",
    ],
    "battery_device_status": ["Online", "Offline", "NotExist"],
    "inverter_device_status": ["Online", "Offline", "NotExist"],
    "meter_device_status": ["Online", "Offline", "NotExist"],
}

# Battery SOC that is actually metered and fluctuates -> SensorDeviceClass.BATTERY.
# SOC *limits* (hw/bms/strategy/current min/max) are configuration thresholds,
# not metered battery levels, so they are deliberately excluded.
_METERED_SOC_KEYS = {"battery_level", "batterySoc", "average_battery_level"}
_MODULE_SOC_RE = re.compile(r"^battery\d+Soc$")


def _is_metered_battery_soc(key: str) -> bool:
    """Return True for fluctuating, metered battery SOC sensors only."""
    return key in _METERED_SOC_KEYS or _MODULE_SOC_RE.match(key) is not None


def get_device_class_for_sensor(key: str) -> SensorDeviceClass | None:
    """Get the appropriate device class for a sensor."""
    # Check specific keys first before general pattern matching
    if key == "last_strategy_change":
        return SensorDeviceClass.TIMESTAMP
    # Bounded text states -> ENUM (before the status guard, which would null them)
    elif key in ENUM_SENSOR_OPTIONS:
        return SensorDeviceClass.ENUM
    # Check for status and strategy fields (they're text, not numeric)
    elif (
        "status" in key.lower()
        or "strategy" in key.lower()
        or key in ["currency", "battery_count"]
        or key == "battery_full"
    ):
        return None
    # Stored energy: current energy in the battery (kWh). Must precede the
    # generic "energy"/"battery" checks so it is not mis-classified as ENERGY.
    elif "storedenergy" in key.lower().replace("_", ""):
        return SensorDeviceClass.ENERGY_STORAGE
    # Cumulative/flow energy. Nominal capacity is intentionally NOT here: it is a
    # static spec value, not metered energy (see get_entity_category -> diagnostic).
    elif (
        "mpptenergy" in key.lower().replace("_", "").replace(" ", "")
        or key == "total_solar_energy"
        or key in ["total_grid_export_energy", "daily_grid_export_energy"]
        or key in ["daily_yield", "lifetime_yield"]
    ):
        return SensorDeviceClass.ENERGY
    # Earnings are monetary
    elif key in ["daily_earnings", "lifetime_earnings"]:
        return SensorDeviceClass.MONETARY
    # Home power
    elif key == "home_power":
        return SensorDeviceClass.POWER
    # Time remaining sensors
    elif "remaining" in key.lower():
        return SensorDeviceClass.DURATION
    # MPPT voltage sensors
    elif "invol" in key.lower() or "voltage" in key.lower():
        return SensorDeviceClass.VOLTAGE
    # total_power_generation and total_yield are actually energy despite the name
    elif key in ["total_power_generation", "total_yield"]:
        return SensorDeviceClass.ENERGY
    # Check power BEFORE current to catch "current_power" correctly
    elif "power" in key.lower():
        return SensorDeviceClass.POWER
    # MPPT current sensors - more specific check to avoid catching "current_power"
    elif "incur" in key.lower() or (
        key.lower().endswith("_current") or key.lower() == "current"
    ):
        return SensorDeviceClass.CURRENT
    elif "energy" in key.lower():
        return SensorDeviceClass.ENERGY
    # BATTERY only for metered, fluctuating SOC — not for SOC limit thresholds.
    elif _is_metered_battery_soc(key):
        return SensorDeviceClass.BATTERY
    elif key == "has_fault":
        return None  # Binary-like sensor but as regular sensor
    return None


def get_state_class_for_sensor(key: str) -> SensorStateClass | None:
    """Get the appropriate state class for a sensor."""
    # Stored energy fluctuates (rises and falls) -> MEASUREMENT, never TOTAL*.
    if "storedenergy" in key.lower().replace("_", ""):
        return SensorStateClass.MEASUREMENT
    # Monetary totals must use TOTAL — MONETARY forbids TOTAL_INCREASING. The
    # daily-resetting one (daily_earnings) carries a last_reset (see the entity's
    # last_reset property) so the midnight reset is handled correctly.
    if key in ("lifetime_earnings", "daily_earnings"):
        return SensorStateClass.TOTAL
    # Energy: lifetime totals AND daily counters are modelled as TOTAL_INCREASING.
    # For the daily counters, TOTAL_INCREASING auto-detects the midnight reset
    # (the value drops to ~0), so no last_reset attribute is needed and the
    # long-term statistics stay correct across the reset.
    if "energy" in key.lower() or key in (
        "total_yield",
        "lifetime_yield",
        "daily_yield",
        "total_power_generation",
    ):
        return SensorStateClass.TOTAL_INCREASING
    # Measurement-type device classes opt into long-term statistics. This covers
    # power (incl. rated_power / max_output_power), voltage, current, metered
    # battery SOC, time-remaining (duration) and stored energy.
    if get_device_class_for_sensor(key) in (
        SensorDeviceClass.POWER,
        SensorDeviceClass.VOLTAGE,
        SensorDeviceClass.CURRENT,
        SensorDeviceClass.BATTERY,
        SensorDeviceClass.DURATION,
        SensorDeviceClass.ENERGY_STORAGE,
    ):
        return SensorStateClass.MEASUREMENT
    # Numeric measurements that carry no device class (counts, prices, rates).
    if key in [
        "device_count",
        "online_devices",
        "offline_devices",
        "strategy_changes_today",
        "electricity_price",
        "electricity_price_avg",
        "electricity_price_high",
        "electricity_price_low",
        "self_use_rate",
        "self_sufficiency_rate",
    ]:
        return SensorStateClass.MEASUREMENT
    return None


def get_unit_for_sensor(key: str) -> str | None:
    """Get the appropriate unit for a sensor."""
    # Stored energy (kWh)
    if "storedenergy" in key.lower().replace("_", ""):
        return UnitOfEnergy.KILO_WATT_HOUR
    # Battery capacity
    if (
        "capacity" in key.lower()
        or "mpptenergy" in key.lower().replace("_", "").replace(" ", "")
        or key == "total_solar_energy"
        or key in ["total_grid_export_energy", "daily_grid_export_energy"]
        or key in ["daily_yield", "lifetime_yield"]
        or key in ["total_power_generation", "total_yield"]
    ):
        return UnitOfEnergy.KILO_WATT_HOUR
    # Time remaining sensors
    elif "remaining" in key.lower():
        return UnitOfTime.MINUTES
    # MPPT voltage sensors
    elif "invol" in key.lower() or "voltage" in key.lower():
        return UnitOfElectricPotential.VOLT
    # Ensure rated_power and max_output_power get W units
    # Check power BEFORE current to catch "current_power" correctly
    elif (
        key
        in [
            "rated_power",
            "max_output_power",
            "home_power",
            "inverter_current_power",
            "current_power",
        ]
        or "power" in key.lower()
    ):
        return UnitOfPower.WATT
    # MPPT current sensors - more specific check to avoid catching "current_power"
    elif "incur" in key.lower() or (
        key.lower().endswith("_current") or key.lower() == "current"
    ):
        return UnitOfElectricCurrent.AMPERE
    elif "energy" in key.lower():
        return UnitOfEnergy.KILO_WATT_HOUR
    elif (
        "soc" in key.lower() or "battery_level" in key or "average_battery_level" in key
    ) or key in ("self_use_rate", "self_sufficiency_rate"):
        return PERCENTAGE
    elif key in (
        "electricity_price",
        "electricity_price_avg",
        "electricity_price_high",
        "electricity_price_low",
    ):
        return "ct/kWh"
    elif "earnings" in key:
        return "EUR"  # Could be made configurable, will use currency field
    return None


def get_icon_for_sensor(key: str, device_type: str = None) -> str | None:
    """Get the appropriate icon for a sensor."""
    # MPPT (Maximum Power Point Tracking) related
    if "mppt" in key.lower():
        if "vol" in key.lower():
            return "mdi:sine-wave"
        elif "cur" in key.lower():
            return "mdi:current-dc"
        elif "power" in key.lower():
            return "mdi:solar-power-variant"
        else:
            return "mdi:solar-panel-large"
    # Time remaining
    elif "remaining" in key.lower():
        if "charge" in key.lower():
            return "mdi:timer-sand"
        elif "discharge" in key.lower():
            return "mdi:timer-sand-empty"
    # Device diagnostics (#159) — before device_type branches so battery
    # devices don't fall through to the generic battery icon.
    elif key == "wifi_ssid":
        return "mdi:wifi"
    elif key == "system_status":
        return "mdi:information-outline"
    # Solar/Inverter related
    elif device_type == "YUNENG_MICRO_INVERTER" or "generation" in key:
        return "mdi:solar-power"
    # Total solar tracking
    elif key == "total_solar_energy":
        return "mdi:solar-power-variant-outline"
    elif key == "total_solar_power":
        return "mdi:solar-power-variant"
    # Grid export tracking
    elif key == "total_grid_export_energy" or key == "daily_grid_export_energy":
        return "mdi:transmission-tower-export"
    # Stored energy (before generic battery icons)
    elif "storedenergy" in key.lower().replace("_", ""):
        return "mdi:home-battery"
    # Battery related
    elif "battery_full" in key:
        return "mdi:battery-check"
    elif "battery_level" in key or "average_battery_level" in key:
        return "mdi:battery-50"
    elif "batterysoc" in key.lower() or "soc" in key.lower():
        return "mdi:battery-outline"
    elif device_type == "ENERGY_STORAGE_BATTERY":
        if "input" in key:
            return "mdi:battery-charging"
        elif "output" in key:
            return "mdi:battery-arrow-down"
        else:
            return "mdi:battery"
    # Grid/Meter related
    elif device_type == "SHELLY_3EM_METER" or "buy" in key or "ret" in key:
        if "buy" in key:
            return "mdi:transmission-tower-import"
        elif "ret" in key or "return" in key:
            return "mdi:transmission-tower-export"
        else:
            return "mdi:transmission-tower"
    # Power related
    elif "power" in key:
        if "rated" in key:
            return "mdi:gauge"
        elif "max" in key:
            return "mdi:gauge-full"
        else:
            return "mdi:flash"
    # Energy related
    elif "energy" in key:
        return "mdi:lightning-bolt"
    # Status related
    elif "battery_device_status" in key:
        return "mdi:battery-sync"
    elif "inverter_device_status" in key:
        return "mdi:solar-panel"
    elif "meter_device_status" in key:
        return "mdi:meter-electric"
    elif "battery_status" in key:
        return "mdi:battery-heart"
    elif "last_strategy_status" in key:
        return "mdi:check-circle"
    elif "status" in key:
        return "mdi:information-outline"
    elif "online" in key:
        return "mdi:check-network"
    elif "offline" in key:
        return "mdi:close-network"
    elif "fault" in key:
        return "mdi:alert-circle"
    # Strategy related
    elif "last_strategy_change" in key:
        return "mdi:clock-outline"
    elif "last_strategy_type" in key:
        return "mdi:history"
    elif "strategy_changes" in key:
        return "mdi:counter"
    elif "strategy" in key:
        return "mdi:cog"
    # Device count
    elif "device_count" in key or "devices" in key:
        return "mdi:counter"
    # Earnings
    elif "earnings" in key:
        return "mdi:cash"
    # Self-consumption rates
    elif key == "self_use_rate":
        return "mdi:solar-power-variant"
    elif key == "self_sufficiency_rate":
        return "mdi:home-percent"
    # Latest notification
    elif key == "latest_notification":
        return "mdi:bell"
    # Electricity price (dynamic tariff)
    elif key == "electricity_price_tag":
        return "mdi:tag-outline"
    elif key.startswith("electricity_price"):
        return "mdi:cash-multiple"
    # Yield (daily / lifetime)
    elif key in ("daily_yield", "lifetime_yield"):
        return "mdi:solar-power-variant"
    # Home power
    elif key == "home_power":
        return "mdi:home-lightning-bolt"
    # Battery count
    elif key == "battery_count":
        return "mdi:battery-multiple"
    # Currency
    elif key == "currency":
        return "mdi:currency-eur"
    return None


def is_daily_reset_total(key: str) -> bool:
    """True for TOTAL sensors that reset at local midnight (need last_reset).

    Energy day-counters use TOTAL_INCREASING (auto reset detection); this is for
    the monetary day-counter (daily_earnings), where MONETARY forbids
    TOTAL_INCREASING so a last_reset must be supplied instead.
    """
    return (
        "daily" in key.lower()
        and get_state_class_for_sensor(key) == SensorStateClass.TOTAL
    )


def get_options_for_sensor(key: str) -> list[str] | None:
    """Return the ENUM options for a bounded text sensor, else None."""
    return ENUM_SENSOR_OPTIONS.get(key)


def get_entity_category(key: str) -> EntityCategory | None:
    """Return the entity category for a sensor.

    Nominal capacity is a static hardware spec, not live telemetry -> diagnostic.
    """
    if key == "battery_capacity" or key.endswith("capacity"):
        return EntityCategory.DIAGNOSTIC
    return None


def get_suggested_display_precision(key: str) -> int | None:
    """Suggested number of decimals for a numeric sensor's displayed state."""
    device_class = get_device_class_for_sensor(key)
    unit = get_unit_for_sensor(key)
    if device_class in (
        SensorDeviceClass.ENERGY,
        SensorDeviceClass.ENERGY_STORAGE,
        SensorDeviceClass.MONETARY,
    ):
        return 2
    if device_class == SensorDeviceClass.CURRENT:
        return 2
    if device_class in (SensorDeviceClass.POWER, SensorDeviceClass.VOLTAGE):
        return 1
    if device_class == SensorDeviceClass.BATTERY:
        return 1
    if device_class == SensorDeviceClass.DURATION:
        return 0
    if unit == UnitOfEnergy.KILO_WATT_HOUR:  # nominal capacity (no device class)
        return 2
    if unit == "ct/kWh":
        return 2
    if unit == PERCENTAGE:
        return 1
    return None


def build_sensor_description(key: str, name: str) -> SensorEntityDescription:
    """Build a SensorEntityDescription with all derived metadata for a key."""
    return SensorEntityDescription(
        key=key,
        name=name,
        device_class=get_device_class_for_sensor(key),
        state_class=get_state_class_for_sensor(key),
        native_unit_of_measurement=get_unit_for_sensor(key),
        options=get_options_for_sensor(key),
        suggested_display_precision=get_suggested_display_precision(key),
        entity_category=get_entity_category(key),
    )
