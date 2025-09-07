"""Family-level binary sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity, BinarySensorEntityDescription)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .. import SunlitDataUpdateCoordinator
from ..const import DOMAIN


class SunlitFamilyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Sunlit family binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._attr_icon = icon

        # Include family_id in unique_id to ensure uniqueness across families
        self._attr_unique_id = f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_{description.key}"

        # Short friendly name for UI (used with has_entity_name)
        self._attr_name = description.name

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data and "family" in self.coordinator.data:
            value = self.coordinator.data["family"].get(self.entity_description.key)
            if value is not None:
                return bool(value)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and (
            "family" in (self.coordinator.data or {})
            and self.entity_description.key in (self.coordinator.data.get("family", {}))
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the family hub."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"family_{self._family_id}")},
            name=f"{self._family_name} Solar System",
            manufacturer="Sunlit Solar",
            model="Solar Management Hub",
            configuration_url="https://sunlitsolar.de",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "family_id": self._family_id,
            "family_name": self._family_name,
        }
