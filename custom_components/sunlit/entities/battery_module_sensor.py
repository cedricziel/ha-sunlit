"""Battery module sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .. import SunlitDataUpdateCoordinator
from ..const import DOMAIN
from .base import normalize_device_type


class SunlitBatteryModuleSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit battery module sensor (virtual device)."""
    
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
        module_number: int,
    ) -> None:
        """Initialize the battery module sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data
        self._module_number = module_number

        # Include module number in unique_id
        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = (
            f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_{normalized_type}_{device_id}_module{module_number}_{description.key}"
        )

        # Short friendly name for UI (used with has_entity_name)
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Special handling for static battery module capacity
        if self.entity_description.key == "capacity":
            return 2.15  # kWh nominal capacity for B215 module
            
        if (
            self.coordinator.data
            and "devices" in self.coordinator.data
            and self._device_id in self.coordinator.data["devices"]
        ):
            value = self.coordinator.data["devices"][self._device_id].get(
                self.entity_description.key
            )
            # Debug logging for missing values
            if value is None and self.entity_description.key != "capacity":
                import logging
                _LOGGER = logging.getLogger(__name__)
                _LOGGER.debug(
                    "Battery module %d sensor '%s' looking for key '%s' - not found in device data. Available keys: %s",
                    self._module_number,
                    self._attr_name,
                    self.entity_description.key,
                    list(self.coordinator.data["devices"][self._device_id].keys())
                )
            return value
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is available as long as the device exists in the data
        return (
            self.coordinator.last_update_success
            and "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data.get("devices", {})
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this virtual battery module."""
        device_sn = self._device_info_data.get("deviceSn", self._device_id)
        
        # Create a virtual device for this battery module
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_sn}_module{self._module_number}")},
            name=f"Battery Module {self._module_number} ({self._family_name})",
            manufacturer="Highpower",
            model="B215 Extension Module",
            via_device=(DOMAIN, device_sn),  # Links to main battery unit
        )
        
        return device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "main_device_id": self._device_id,
            "module_number": self._module_number,
            "parent_device_sn": self._device_info_data.get("deviceSn"),
        }
        
        return attrs