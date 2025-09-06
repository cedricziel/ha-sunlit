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
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    sensors = []
    
    if coordinator.data:
        for key, value in coordinator.data.items():
            sensor_description = SensorEntityDescription(
                key=key,
                name=key.replace("_", " ").title(),
            )
            sensors.append(
                SunlitSensor(
                    coordinator=coordinator,
                    description=sensor_description,
                    entry_id=config_entry.entry_id,
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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_name = f"Sunlit {description.name}"
    
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
            "api_url": self.coordinator.api_url,
            "last_update": self.coordinator.last_update_success_time,
        }