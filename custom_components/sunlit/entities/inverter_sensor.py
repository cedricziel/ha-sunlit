"""Inverter device sensor entity for Sunlit integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from ..const import DEVICE_TYPE_INVERTER, DEVICE_TYPE_INVERTER_SOLAR
from .device_sensor_base import SunlitDeviceSensorBase


class SunlitInverterSensor(SunlitDeviceSensorBase):
    """Representation of a Sunlit inverter device sensor."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this inverter device."""
        base_info = self._get_base_device_info()
        device_type = self._device_info_data.get("deviceType")

        # Use manufacturer from device data if available, otherwise map by type
        manufacturer = self._device_info_data.get("manufacturer")
        model = "Micro Inverter"

        if not manufacturer:
            if device_type == DEVICE_TYPE_INVERTER:
                manufacturer = "Yuneng"
            elif device_type == DEVICE_TYPE_INVERTER_SOLAR:
                # Generic solar inverter - could be DEYE, Hoymiles, etc.
                # Try to get from device data, fallback to "Solar"
                manufacturer = "Solar"
            else:
                manufacturer = "Unknown"

        return DeviceInfo(
            **base_info,
            manufacturer=manufacturer,
            model=model,
        )
