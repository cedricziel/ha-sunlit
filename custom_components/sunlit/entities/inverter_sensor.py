"""Inverter device sensor entity for Sunlit integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .device_sensor_base import SunlitDeviceSensorBase


class SunlitInverterSensor(SunlitDeviceSensorBase):
    """Representation of a Sunlit inverter device sensor."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this inverter device."""
        base_info = self._get_base_device_info()
        
        # Use manufacturer from device data if available
        manufacturer = self._device_info_data.get("manufacturer", "Yuneng")
        
        return DeviceInfo(
            **base_info,
            manufacturer=manufacturer,
            model="Micro Inverter",
        )