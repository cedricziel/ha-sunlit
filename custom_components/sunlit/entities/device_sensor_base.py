"""Base class for device-level sensor entities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from homeassistant.components.sensor import (SensorEntity,
                                             SensorEntityDescription)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .. import SunlitDataUpdateCoordinator
from ..const import DOMAIN
from .base import normalize_device_type


class SunlitDeviceSensorBase(CoordinatorEntity, SensorEntity, ABC):
    """Base representation of a Sunlit device sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data

        # Include family_name, family_id and normalized device type in unique_id
        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_{normalized_type}_{device_id}_{description.key}"

        # Short friendly name for UI (used with has_entity_name)
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Allow subclasses to override for special handling
        value = self._get_native_value()
        if value is not None:
            return value

        # Default behavior: get from coordinator data
        if (
            self.coordinator.data
            and "devices" in self.coordinator.data
            and self._device_id in self.coordinator.data["devices"]
        ):
            return self.coordinator.data["devices"][self._device_id].get(
                self.entity_description.key
            )
        return None

    def _get_native_value(self) -> Any:
        """Override in subclass for special value handling."""
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is available as long as the device exists in the data
        # Even if the specific sensor value is not present (None/null)
        return (
            self.coordinator.last_update_success
            and "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data.get("devices", {})
        )

    @property
    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """Return device info for this device - must be implemented by subclass."""
        pass

    def _get_base_device_info(self) -> dict[str, Any]:
        """Get common device info fields."""
        device_sn = self._device_info_data.get("deviceSn", self._device_id)
        device_type = self._device_info_data.get("deviceType", "Unknown")

        # Map device types to friendly names
        friendly_names = {
            "ENERGY_STORAGE_BATTERY": "BK215",
            "YUNENG_MICRO_INVERTER": "Microinverter",
            "SHELLY_3EM_METER": "Smart Meter",
        }

        friendly_name = friendly_names.get(device_type, device_type)

        base_info = {
            "identifiers": {(DOMAIN, device_sn)},
            "name": f"{friendly_name} ({self._family_name}, {self._device_id})",
            "via_device": (DOMAIN, f"family_{self._family_id}"),
        }

        # Add optional fields if available
        if device_sn != self._device_id:
            base_info["serial_number"] = device_sn

        if "firmwareVersion" in self._device_info_data:
            base_info["sw_version"] = self._device_info_data["firmwareVersion"]

        if "hwVersion" in self._device_info_data:
            base_info["hw_version"] = self._device_info_data["hwVersion"]

        return base_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "device_id": self._device_id,
            "device_type": self._device_info_data.get("deviceType"),
            "device_sn": self._device_info_data.get("deviceSn"),
        }

        # Add device-specific attributes from coordinator data
        if (
            "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data["devices"]
        ):
            device_data = self.coordinator.data["devices"][self._device_id]
            if "fault" in device_data:
                attrs["fault"] = device_data["fault"]
            if "off" in device_data:
                attrs["off"] = device_data["off"]

        # Add additional device info if available
        if "systemMultiStatus" in self._device_info_data:
            attrs["system_status"] = self._device_info_data["systemMultiStatus"]
        if "supportReboot" in self._device_info_data:
            attrs["support_reboot"] = self._device_info_data["supportReboot"]
        if "ssid" in self._device_info_data:
            attrs["wifi_ssid"] = self._device_info_data["ssid"]

        return attrs
