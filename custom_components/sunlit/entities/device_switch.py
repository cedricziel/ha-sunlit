"""Battery local-mode control switch for the Sunlit integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ..const import DOMAIN
from .base import normalize_device_type

_LOGGER = logging.getLogger(__name__)


class SunlitBatteryLocalModeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to toggle a battery's local mode.

    Local mode lets the battery operate from on-device logic rather than the
    cloud strategy. Writes go to /v1.7/battery/updateLocalModeConfig; current
    state is read from the device coordinator (sourced from device details).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
    ) -> None:
        """Initialize the local-mode switch."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data
        self._device_sn = device_info_data.get("deviceSn")

        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = (
            f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_"
            f"{normalized_type}_{device_id}_local_mode"
        )
        self._attr_name = "Local Mode"

    def _device_data(self) -> dict[str, Any] | None:
        """Return this device's entry from the coordinator data."""
        data = self.coordinator.data or {}
        return data.get("devices", {}).get(self._device_id)

    @property
    def is_on(self) -> bool | None:
        """Return whether local mode is currently enabled."""
        device = self._device_data()
        if device is not None and device.get("local_mode_enabled") is not None:
            return bool(device["local_mode_enabled"])
        return None

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        device = self._device_data()
        return (
            self.coordinator.last_update_success
            and device is not None
            and device.get("local_mode_enabled") is not None
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the battery device created by the other platforms."""
        device_sn = self._device_info_data.get("deviceSn", self._device_id)
        return DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            via_device=(DOMAIN, f"family_{self._family_id}"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "device_id": self._device_id,
            "device_sn": self._device_sn,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable local mode."""
        await self._set_local_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable local mode."""
        await self._set_local_mode(False)

    async def _set_local_mode(self, enable: bool) -> None:
        """Call the control endpoint, then optimistically update and refresh."""
        if not self._device_sn:
            raise HomeAssistantError(
                "Battery serial number unknown; cannot set local mode"
            )
        try:
            await self.coordinator.api_client.update_battery_local_mode(
                self._device_sn, enable
            )
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set battery local mode: {err}"
            ) from err

        # Reflect the change immediately, then refresh to confirm against the API.
        device = self._device_data()
        if device is not None:
            device["local_mode_enabled"] = enable
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
