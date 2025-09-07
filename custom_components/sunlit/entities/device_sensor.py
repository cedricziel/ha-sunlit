"""Device-level sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .. import SunlitDataUpdateCoordinator
from ..const import DOMAIN, DEVICE_TYPE_BATTERY, DEVICE_TYPE_INVERTER, DEVICE_TYPE_METER
from .base import normalize_device_type


class SunlitDeviceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit device sensor."""

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

        # Include family_id and normalized device type in unique_id
        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = (
            f"sunlit_{family_id}_{normalized_type}_{device_id}_{description.key}"
        )

        # Human-readable name
        self._attr_name = f"{device_type} {device_id} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Special handling for static battery capacity
        if self.entity_description.key == "battery_capacity":
            device_type = self._device_info_data.get("deviceType")
            if device_type == DEVICE_TYPE_BATTERY:
                return 2.15  # kWh nominal capacity for BK215
            return None
            
        if (
            self.coordinator.data
            and "devices" in self.coordinator.data
            and self._device_id in self.coordinator.data["devices"]
        ):
            return self.coordinator.data["devices"][self._device_id].get(
                self.entity_description.key
            )
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
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        device_type = self._device_info_data.get("deviceType", "Unknown")
        device_sn = self._device_info_data.get("deviceSn", self._device_id)

        # Use manufacturer from device data if available, otherwise map by type
        manufacturer = self._device_info_data.get("manufacturer")
        model_name = device_type
        
        if not manufacturer:
            # Fallback mapping if manufacturer not provided
            if device_type == DEVICE_TYPE_METER:
                manufacturer = "Shelly"
                model_name = "3EM Smart Meter"
            elif device_type == DEVICE_TYPE_INVERTER:
                manufacturer = "Yuneng"
                model_name = "Micro Inverter"
            elif device_type == DEVICE_TYPE_BATTERY:
                manufacturer = "Highpower"
                model_name = "BK215 Energy Storage System"
            else:
                manufacturer = "Unknown"

        device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"{device_type} ({self._device_id})",
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