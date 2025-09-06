"""Platform for sensor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunlitDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinators = hass.data[DOMAIN][config_entry.entry_id]
    
    sensors = []
    
    # Process multiple family coordinators
    for _, coordinator in coordinators.items():
        if coordinator.data:
            for key, _ in coordinator.data.items():
                sensor_description = SensorEntityDescription(
                    key=key,
                    name=f"{coordinator.family_name} {key.replace('_', ' ').title()}",
                )
                sensors.append(
                    SunlitSensor(
                        coordinator=coordinator,
                        description=sensor_description,
                        entry_id=config_entry.entry_id,
                        family_id=coordinator.family_id,
                        family_name=coordinator.family_name,
                    )
                )
    
    async_add_entities(sensors, True)


class SunlitSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit REST sensor."""
    
    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        
        # Include family_id in unique_id to ensure uniqueness across families
        self._attr_unique_id = f"{entry_id}_{family_id}_{description.key}"
        
        # Human-readable name includes family name
        self._attr_name = f"Sunlit {family_name} {description.key.replace('_', ' ').title()}"
    
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(self.entity_description.key)
        return None
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and (
            self.entity_description.key in (self.coordinator.data or {})
        )
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "family_id": self._family_id,
            "family_name": self._family_name,
            "last_update": self.coordinator.last_update_success_time,
        }