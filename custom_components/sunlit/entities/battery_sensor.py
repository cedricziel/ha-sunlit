"""Battery device sensor entity for Sunlit integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .device_sensor_base import SunlitDeviceSensorBase


class SunlitBatterySensor(SunlitDeviceSensorBase):
    """Representation of a Sunlit battery device sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
        mppt_coordinator: DataUpdateCoordinator | None = None,
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(
            coordinator,
            description,
            entry_id,
            family_id,
            family_name,
            device_id,
            device_info_data,
        )
        self._mppt_coordinator = mppt_coordinator

    async def async_added_to_hass(self) -> None:
        """Subscribe to the MPPT coordinator in addition to the device coordinator.

        The MPPT energy values come from a separate MPPT coordinator, which
        HomeAssistant only schedules for periodic refresh while it has at least
        one listener. Without this subscription the MPPT coordinator would
        refresh once at startup (all energy = 0) and never again, freezing
        MPPT Total Energy at 0 (issue #72).
        """
        await super().async_added_to_hass()
        if self._mppt_coordinator is not None:
            self.async_on_remove(
                self._mppt_coordinator.async_add_listener(
                    self._handle_coordinator_update
                )
            )

    def _get_native_value(self) -> Any:
        """Handle special battery-specific values."""
        # Special handling for static battery capacity
        if self.entity_description.key == "battery_capacity":
            return 2.15  # kWh nominal capacity for BK215

        # Handle MPPT energy values from MPPT coordinator
        if (
            self._mppt_coordinator
            and self.entity_description.key
            in ["batteryMppt1Energy", "batteryMppt2Energy"]
            and self._mppt_coordinator.data
            and "mppt_energy" in self._mppt_coordinator.data
            and self._device_id in self._mppt_coordinator.data["mppt_energy"]
        ):
            return self._mppt_coordinator.data["mppt_energy"][self._device_id].get(
                self.entity_description.key
            )

        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this battery device."""
        base_info = self._get_base_device_info()

        # Use manufacturer from device data if available
        manufacturer = self._device_info_data.get("manufacturer", "Highpower")

        return DeviceInfo(
            **base_info,
            manufacturer=manufacturer,
            model="BK215",
        )
