"""Family-level sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .. import SunlitDataUpdateCoordinator
from ..const import DOMAIN


class SunlitFamilySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit family aggregate sensor."""

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
        self._attr_unique_id = f"sunlit_{family_id}_{description.key}"

        # Human-readable name
        self._attr_name = f"{family_name} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data and "family" in self.coordinator.data:
            value = self.coordinator.data["family"].get(self.entity_description.key)

            # Convert timestamp from milliseconds to datetime for timestamp sensors
            if self.entity_description.key == "last_strategy_change" and value:
                return datetime.fromtimestamp(value / 1000, tz=timezone.utc)

            return value
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