"""Meter device sensor entity for Sunlit integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from ..const import DEVICE_TYPE_METER, DEVICE_TYPE_METER_PRO
from .device_sensor_base import SunlitDeviceSensorBase


class SunlitMeterSensor(SunlitDeviceSensorBase):
    """Representation of a Sunlit meter device sensor."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this meter device."""
        base_info = self._get_base_device_info()
        device_type = self._device_info_data.get("deviceType")

        # Use manufacturer from device data if available
        manufacturer = self._device_info_data.get("manufacturer", "Shelly")

        # Determine model based on device type
        if device_type == DEVICE_TYPE_METER_PRO:
            model = "Pro 3EM Smart Meter"
        elif device_type == DEVICE_TYPE_METER:
            model = "3EM Smart Meter"
        else:
            model = "Smart Meter"

        return DeviceInfo(
            **base_info,
            manufacturer=manufacturer,
            model=model,
        )
