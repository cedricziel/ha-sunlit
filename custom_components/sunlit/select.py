"""Platform for select integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunlitDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Define select entities with their options
FAMILY_SELECT_ENTITIES = {
    "battery_strategy": {
        "name": "Battery Strategy",
        "options": ["EnergyStorageOnly", "SmartStrategy", "None"],
        "icon": "mdi:cog",
    },
    "battery_status": {
        "name": "Battery Status",
        "options": ["Success", "Failure", "Unknown"],
        "icon": "mdi:battery-heart",
    },
    "battery_device_status": {
        "name": "Battery Device Status",
        "options": ["Online", "Offline", "Unknown"],
        "icon": "mdi:battery-sync",
    },
    "inverter_device_status": {
        "name": "Inverter Device Status",
        "options": ["Online", "Offline", "Unknown"],
        "icon": "mdi:solar-panel",
    },
    "meter_device_status": {
        "name": "Meter Device Status",
        "options": ["Online", "Offline", "Unknown"],
        "icon": "mdi:meter-electric",
    },
    "last_strategy_type": {
        "name": "Last Strategy Type",
        "options": ["EnergyStorageOnly", "SmartStrategy", "None"],
        "icon": "mdi:history",
    },
    "last_strategy_status": {
        "name": "Last Strategy Status",
        "options": ["Success", "Failure", "Unknown"],
        "icon": "mdi:check-circle",
    },
}

DEVICE_SELECT_ENTITIES = {
    "status": {
        "name": "Status",
        "options": ["Online", "Offline", "Unknown"],
        "icon": "mdi:information-outline",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinators = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    # Process multiple family coordinators
    for _, coordinator in coordinators.items():
        if coordinator.data:
            # Create family select entities
            if "family" in coordinator.data:
                for key, config in FAMILY_SELECT_ENTITIES.items():
                    if key in coordinator.data["family"]:
                        entity_description = SelectEntityDescription(
                            key=key,
                            name=config["name"],
                        )
                        entity = SunlitFamilySelect(
                            coordinator=coordinator,
                            description=entity_description,
                            entry_id=config_entry.entry_id,
                            family_id=coordinator.family_id,
                            family_name=coordinator.family_name,
                            options=config["options"],
                            icon=config.get("icon"),
                        )
                        entities.append(entity)

            # Create device select entities
            if "devices" in coordinator.data:
                for device_id, device_data in coordinator.data["devices"].items():
                    if device_id in coordinator.devices:
                        device_info = coordinator.devices[device_id]
                        
                        for key, config in DEVICE_SELECT_ENTITIES.items():
                            if key in device_data:
                                entity_description = SelectEntityDescription(
                                    key=key,
                                    name=config["name"],
                                )
                                entity = SunlitDeviceSelect(
                                    coordinator=coordinator,
                                    description=entity_description,
                                    entry_id=config_entry.entry_id,
                                    family_id=coordinator.family_id,
                                    family_name=coordinator.family_name,
                                    device_id=device_id,
                                    device_info_data=device_info,
                                    options=config["options"],
                                    icon=config.get("icon"),
                                )
                                entities.append(entity)

    async_add_entities(entities, True)


class SunlitFamilySelect(CoordinatorEntity, SelectEntity):
    """Representation of a Sunlit family select entity."""

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SelectEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        options: list[str],
        icon: str | None = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._attr_options = options
        self._attr_icon = icon

        # Include family_id in unique_id to ensure uniqueness across families
        self._attr_unique_id = f"{entry_id}_{family_id}_family_{description.key}"

        # Human-readable name includes family name
        self._attr_name = f"{family_name} {description.name}"

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        if self.coordinator.data and "family" in self.coordinator.data:
            value = self.coordinator.data["family"].get(self.entity_description.key)
            if value is not None:
                # Convert value to string and check if it's in options
                str_value = str(value)
                if str_value in self._attr_options:
                    return str_value
                # If not in options, return it anyway (will show as custom value)
                return str_value
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # This would need API support to actually change the value
        _LOGGER.info(
            "Select option %s for %s (read-only - API write not implemented)",
            option,
            self.entity_description.key,
        )

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
            model="Family Hub",
        )


class SunlitDeviceSelect(CoordinatorEntity, SelectEntity):
    """Representation of a Sunlit device select entity."""

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SelectEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
        options: list[str],
        icon: str | None = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data
        self._attr_options = options
        self._attr_icon = icon

        # Include device_id in unique_id to ensure uniqueness
        self._attr_unique_id = f"{entry_id}_{device_id}_{description.key}"

        # Human-readable name
        device_type = device_info_data.get("deviceType", "Device")
        self._attr_name = f"{device_type} {device_id} {description.name}"

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        if (
            self.coordinator.data
            and "devices" in self.coordinator.data
            and self._device_id in self.coordinator.data["devices"]
        ):
            value = self.coordinator.data["devices"][self._device_id].get(
                self.entity_description.key
            )
            if value is not None:
                # Convert value to string and check if it's in options
                str_value = str(value)
                if str_value in self._attr_options:
                    return str_value
                # If not in options, return it anyway (will show as custom value)
                return str_value
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # This would need API support to actually change the value
        _LOGGER.info(
            "Select option %s for device %s/%s (read-only - API write not implemented)",
            option,
            self._device_id,
            self.entity_description.key,
        )

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

        # Use manufacturer from device data if available, otherwise map by type
        manufacturer = self._device_info_data.get("manufacturer")
        if not manufacturer:
            # Fallback mapping if manufacturer not provided
            if device_type == "SHELLY_3EM_METER":
                manufacturer = "Shelly"
            elif device_type == "YUNENG_MICRO_INVERTER":
                manufacturer = "Yuneng"
            elif device_type == "ENERGY_STORAGE_BATTERY":
                manufacturer = "Highpower"
            else:
                manufacturer = "Unknown"

        device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"{device_type} ({self._device_id})",
            manufacturer=manufacturer,
            model=device_type,
            via_device=(DOMAIN, f"family_{self._family_id}"),
        )
        
        # Add firmware version if available
        if "firmwareVersion" in self._device_info_data:
            device_info["sw_version"] = self._device_info_data["firmwareVersion"]
        
        # Add hardware version if available  
        if "hwVersion" in self._device_info_data:
            device_info["hw_version"] = self._device_info_data["hwVersion"]
            
        return device_info