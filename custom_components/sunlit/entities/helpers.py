"""Helper functions for Sunlit sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTime,
    PERCENTAGE,
)


def get_device_class_for_sensor(key: str) -> SensorDeviceClass | None:
    """Get the appropriate device class for a sensor."""
    # Check for status and strategy fields first (they're text, not numeric)
    if "status" in key.lower() or "strategy" in key.lower():
        return None
    # battery_full is a boolean, not a battery percentage
    elif key == "battery_full":
        return None
    # Battery capacity
    elif "capacity" in key.lower():
        return SensorDeviceClass.ENERGY
    # Time remaining sensors
    elif "remaining" in key.lower():
        return SensorDeviceClass.DURATION
    # MPPT voltage sensors
    elif "invol" in key.lower() or "voltage" in key.lower():
        return SensorDeviceClass.VOLTAGE
    # MPPT current sensors
    elif "incur" in key.lower() or "current" in key.lower():
        return SensorDeviceClass.CURRENT
    # total_power_generation is actually energy despite the name
    elif key == "total_power_generation":
        return SensorDeviceClass.ENERGY
    elif "power" in key.lower():
        return SensorDeviceClass.POWER
    elif "energy" in key.lower():
        return SensorDeviceClass.ENERGY
    elif "soc" in key.lower():
        return SensorDeviceClass.BATTERY
    elif "battery" in key.lower() or "level" in key.lower():
        return SensorDeviceClass.BATTERY
    elif key == "last_strategy_change":
        return SensorDeviceClass.TIMESTAMP
    elif key == "has_fault":
        return None  # Binary-like sensor but as regular sensor
    return None


def get_state_class_for_sensor(key: str) -> SensorStateClass | None:
    """Get the appropriate state class for a sensor."""
    # Static configuration values don't need state class
    if key in ["rated_power", "max_output_power"]:
        return None
    # Special case: total_power_generation is cumulative energy
    elif key == "total_power_generation":
        return SensorStateClass.TOTAL_INCREASING
    # Energy sensors need special handling
    elif "energy" in key.lower():
        if "total" in key.lower():
            # Total energy counters that never reset
            return SensorStateClass.TOTAL_INCREASING
        elif "daily" in key.lower():
            # Daily energy counters that reset each day
            return SensorStateClass.TOTAL
        else:
            # Other energy sensors
            return SensorStateClass.TOTAL_INCREASING
    elif "power" in key.lower():
        return SensorStateClass.MEASUREMENT
    elif key in [
        "device_count",
        "online_devices",
        "offline_devices",
        "strategy_changes_today",
    ]:
        return SensorStateClass.MEASUREMENT
    return None


def get_unit_for_sensor(key: str) -> str | None:
    """Get the appropriate unit for a sensor."""
    # Battery capacity
    if "capacity" in key.lower():
        return UnitOfEnergy.KILO_WATT_HOUR
    # Special case: total_power_generation is actually energy in kWh
    elif key == "total_power_generation":
        return UnitOfEnergy.KILO_WATT_HOUR
    # Time remaining sensors
    elif "remaining" in key.lower():
        return UnitOfTime.MINUTES
    # MPPT voltage sensors
    elif "invol" in key.lower() or "voltage" in key.lower():
        return UnitOfElectricPotential.VOLT
    # MPPT current sensors  
    elif "incur" in key.lower() or "current" in key.lower():
        return UnitOfElectricCurrent.AMPERE
    # Ensure rated_power and max_output_power get W units
    elif key in ["rated_power", "max_output_power"] or "power" in key.lower():
        return UnitOfPower.WATT
    elif "energy" in key.lower():
        return UnitOfEnergy.KILO_WATT_HOUR
    elif "soc" in key.lower():
        return PERCENTAGE
    elif "battery_level" in key or "average_battery_level" in key:
        return PERCENTAGE
    elif "earnings" in key:
        return "EUR"  # Could be made configurable
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
    # Solar/Inverter related
    elif device_type == "YUNENG_MICRO_INVERTER" or "generation" in key:
        return "mdi:solar-power"
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
    return None