"""Base utilities for Sunlit entities."""

from ..const import (DEVICE_TYPE_BATTERY, DEVICE_TYPE_INVERTER,
                     DEVICE_TYPE_METER)


def normalize_device_type(device_type: str) -> str:
    """Normalize device type for use in unique_id.

    Maps device types to short, readable names:
    - ENERGY_STORAGE_BATTERY -> battery
    - YUNENG_MICRO_INVERTER -> inverter
    - SHELLY_3EM_METER -> meter
    """
    type_map = {
        DEVICE_TYPE_BATTERY: "battery",
        DEVICE_TYPE_INVERTER: "inverter",
        DEVICE_TYPE_METER: "meter",
    }
    return type_map.get(
        device_type, device_type.lower().replace("_", "").replace(" ", "")
    )
