"""Unknown device sensor entity for Sunlit integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .device_sensor_base import SunlitDeviceSensorBase


class SunlitUnknownDeviceSensor(SunlitDeviceSensorBase):
    """Representation of a Sunlit unknown/unsupported device sensor."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this unknown device."""
        base_info = self._get_base_device_info()
        
        # Use manufacturer from device data if available, otherwise "Unknown"
        manufacturer = self._device_info_data.get("manufacturer", "Unknown")
        
        # Use the raw device type as the model
        device_type = self._device_info_data.get("deviceType", "Unknown Device")
        
        return DeviceInfo(
            **base_info,
            manufacturer=manufacturer,
            model=device_type,
        )