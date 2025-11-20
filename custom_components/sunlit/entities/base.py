"""Base utilities for Sunlit entities."""

from ..const import (
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_INVERTER_SOLAR,
    DEVICE_TYPE_METER,
    DEVICE_TYPE_METER_PRO,
)


def normalize_device_type(device_type: str) -> str:
    """Normalize device type for use in unique_id.

    Maps device types to short, readable names:
    - ENERGY_STORAGE_BATTERY -> battery
    - YUNENG_MICRO_INVERTER -> inverter
    - SOLAR_MICRO_INVERTER -> inverter (generic solar inverter, includes DEYE)
    - SHELLY_3EM_METER -> meter
    - SHELLY_PRO3EM_METER -> meter (Shelly Pro 3EM variant)
    """
    type_map = {
        DEVICE_TYPE_BATTERY: "battery",
        DEVICE_TYPE_INVERTER: "inverter",
        DEVICE_TYPE_INVERTER_SOLAR: "inverter",  # Generic solar inverter
        DEVICE_TYPE_METER: "meter",
        DEVICE_TYPE_METER_PRO: "meter",  # Shelly Pro variant
    }
    return type_map.get(
        device_type, device_type.lower().replace("_", "").replace(" ", "")
    )
