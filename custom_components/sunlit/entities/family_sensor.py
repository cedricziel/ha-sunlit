"""Family-level sensor entity for Sunlit integration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ..const import (
    DOMAIN,
    SENSOR_GROUP_BATTERY,
    SENSOR_GROUP_INFO,
    SENSOR_GROUP_STATUS,
    SENSOR_GROUP_STRATEGY,
    SENSOR_GROUPS,
)


class SunlitFamilySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit family aggregate sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
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
        self._attr_unique_id = f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_{description.key}"

        # Short friendly name for UI (used with has_entity_name)
        self._attr_name = description.name

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category based on sensor group."""
        sensor_group = SENSOR_GROUPS.get(self.entity_description.key)

        if sensor_group in (SENSOR_GROUP_BATTERY, SENSOR_GROUP_STRATEGY):
            # Battery management and strategy control are configuration
            return EntityCategory.CONFIG
        elif sensor_group in (SENSOR_GROUP_INFO, SENSOR_GROUP_STATUS):
            # System information and status are diagnostic
            return EntityCategory.DIAGNOSTIC

        # Overview, energy, and financial sensors are primary (no category)
        return None

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = None

            # Check the appropriate section based on coordinator type
            # Device coordinator uses aggregates
            if "aggregates" in self.coordinator.data:
                value = self.coordinator.data["aggregates"].get(
                    self.entity_description.key
                )
            # Strategy coordinator uses strategy
            elif "strategy" in self.coordinator.data:
                value = self.coordinator.data["strategy"].get(
                    self.entity_description.key
                )
            # MPPT coordinator uses mppt_energy
            elif "mppt_energy" in self.coordinator.data:
                value = self.coordinator.data["mppt_energy"].get(
                    self.entity_description.key
                )
            # Family coordinator uses family
            elif "family" in self.coordinator.data:
                value = self.coordinator.data["family"].get(self.entity_description.key)

            # Convert timestamp from milliseconds to datetime for timestamp sensors
            if self.entity_description.key == "last_strategy_change" and value:
                return datetime.fromtimestamp(value / 1000, tz=UTC)

            return value
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return False

        # Check if the key exists in the appropriate data section
        # Match the order used in native_value for consistency
        if "aggregates" in self.coordinator.data:
            return self.entity_description.key in self.coordinator.data.get(
                "aggregates", {}
            )
        elif "strategy" in self.coordinator.data:
            return self.entity_description.key in self.coordinator.data.get(
                "strategy", {}
            )
        elif "mppt_energy" in self.coordinator.data:
            return self.entity_description.key in self.coordinator.data.get(
                "mppt_energy", {}
            )
        elif "family" in self.coordinator.data:
            return self.entity_description.key in self.coordinator.data.get(
                "family", {}
            )

        return False

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
        attrs = {
            "family_id": self._family_id,
            "family_name": self._family_name,
        }

        # Add strategy history if available
        if (
            self.entity_description.key == "last_strategy_change"
            and self.coordinator.data
            and "family" in self.coordinator.data
        ):
            history = self.coordinator.data["family"].get("strategy_history", [])
            if history:
                # Format history for display
                formatted_history = []
                for entry in history[:10]:  # Last 10 entries
                    if entry.get("modifyDate"):
                        timestamp = datetime.fromtimestamp(
                            entry["modifyDate"] / 1000
                        ).isoformat()
                    else:
                        timestamp = "Unknown"

                    formatted_history.append(
                        {
                            "timestamp": timestamp,
                            "strategy": entry.get("strategy", "Unknown"),
                            "status": entry.get("status", "Unknown"),
                            "mode": entry.get("smartStrategyMode"),
                            "soc_min": entry.get("socMin"),
                            "soc_max": entry.get("socMax"),
                        }
                    )
                attrs["history"] = formatted_history

        return attrs
