"""Platform for switch integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entities.device_switch import SunlitBatteryLocalModeSwitch

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]

    # Handle both old and new data structures
    if isinstance(integration_data, dict) and "coordinators" in integration_data:
        coordinators = integration_data["coordinators"]
    else:
        coordinators = integration_data

    switches = []

    for family_id, coordinator_set in coordinators.items():
        if not isinstance(coordinator_set, dict):
            _LOGGER.warning(
                "Old coordinator structure detected, skipping family %s", family_id
            )
            continue

        device_coordinator = coordinator_set.get("device")
        if not device_coordinator or not device_coordinator.data:
            continue

        devices = device_coordinator.data.get("devices", {})
        for device_id, device_data in devices.items():
            # Only batteries that advertise local-mode support get a switch.
            if not device_data.get("support_local_mode"):
                continue
            if not (
                device_coordinator.devices and device_id in device_coordinator.devices
            ):
                continue

            device_info = device_coordinator.devices[device_id]
            switches.append(
                SunlitBatteryLocalModeSwitch(
                    coordinator=device_coordinator,
                    entry_id=config_entry.entry_id,
                    family_id=device_coordinator.family_id,
                    family_name=device_coordinator.family_name,
                    device_id=device_id,
                    device_info_data=device_info,
                )
            )

    async_add_entities(switches, True)
