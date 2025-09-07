"""Device-level binary sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .. import SunlitDataUpdateCoordinator
from ..const import DOMAIN, DEVICE_TYPE_BATTERY, DEVICE_TYPE_INVERTER, DEVICE_TYPE_METER
from .base import normalize_device_type


class SunlitDeviceBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Sunlit device binary sensor."""

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
        icon: str | None = None,
        inverted: bool = False,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data
        self._attr_icon = icon
        self._inverted = inverted

        # Include family_id and normalized device type in unique_id
        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = (
            f"sunlit_{family_id}_{normalized_type}_{device_id}_{description.key}"
        )

        # Map device types to friendly names for sensor names
        friendly_names = {
            DEVICE_TYPE_BATTERY: "BK215",
            DEVICE_TYPE_INVERTER: "Microinverter",
            DEVICE_TYPE_METER: "Smart Meter",
        }
        
        friendly_name = friendly_names.get(device_type, device_type)

        # Human-readable name
        self._attr_name = f"{friendly_name} {device_id} {description.name}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if (
            self.coordinator.data
            and "devices" in self.coordinator.data
            and self._device_id in self.coordinator.data["devices"]
        ):
            value = self.coordinator.data["devices"][self._device_id].get(
                self.entity_description.key
            )
            if value is not None:
                # Apply inversion if needed (e.g., for "off" field)
                return not bool(value) if self._inverted else bool(value)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data.get("devices", {})
            and self.entity_description.key
            in self.coordinator.data["devices"][self._device_id]
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        device_type = self._device_info_data.get("deviceType", "Unknown")
        device_sn = self._device_info_data.get("deviceSn", self._device_id)

        # Map device types to friendly names
        friendly_names = {
            DEVICE_TYPE_BATTERY: "BK215",
            DEVICE_TYPE_INVERTER: "Microinverter",
            DEVICE_TYPE_METER: "Smart Meter",
        }
        
        friendly_name = friendly_names.get(device_type, device_type)
        
        # Use manufacturer from device data if available, otherwise map by type
        manufacturer = self._device_info_data.get("manufacturer")
        
        if not manufacturer:
            # Fallback mapping if manufacturer not provided
            if device_type == DEVICE_TYPE_METER:
                manufacturer = "Shelly"
            elif device_type == DEVICE_TYPE_INVERTER:
                manufacturer = "Yuneng"
            elif device_type == DEVICE_TYPE_BATTERY:
                manufacturer = "Highpower"
            else:
                manufacturer = "Unknown"

        # Map to model names
        model_map = {
            DEVICE_TYPE_BATTERY: "BK215",
            DEVICE_TYPE_INVERTER: "Microinverter",
            DEVICE_TYPE_METER: "Smart Meter",
        }
        
        model_name = model_map.get(device_type, device_type)

        device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"{friendly_name} ({self._family_name}, {self._device_id})",
            manufacturer=manufacturer,
            model=model_name,
            serial_number=device_sn if device_sn != self._device_id else None,
            via_device=(DOMAIN, f"family_{self._family_id}"),
        )

        # Add firmware version if available
        if "firmwareVersion" in self._device_info_data:
            device_info["sw_version"] = self._device_info_data["firmwareVersion"]

        # Add hardware version if available
        if "hwVersion" in self._device_info_data:
            device_info["hw_version"] = self._device_info_data["hwVersion"]

        return device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "device_id": self._device_id,
            "device_type": self._device_info_data.get("deviceType"),
            "device_sn": self._device_info_data.get("deviceSn"),
        }

        return attrs