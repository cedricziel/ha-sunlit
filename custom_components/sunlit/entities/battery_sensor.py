"""Battery device sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo

from .device_sensor_base import SunlitDeviceSensorBase


class SunlitBatterySensor(SunlitDeviceSensorBase):
    """Representation of a Sunlit battery device sensor."""

    def _get_native_value(self) -> Any:
        """Handle special battery-specific values."""
        # Special handling for static battery capacity
        if self.entity_description.key == "battery_capacity":
            return 2.15  # kWh nominal capacity for BK215
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this battery device."""
        base_info = self._get_base_device_info()
        
        # Use manufacturer from device data if available
        manufacturer = self._device_info_data.get("manufacturer", "Highpower")
        
        return DeviceInfo(
            **base_info,
            manufacturer=manufacturer,
            model="BK215",
        )