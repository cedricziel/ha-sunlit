"""The Sunlit REST integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import SunlitApiClient
from .const import CONF_ACCESS_TOKEN, CONF_FAMILIES, DOMAIN
from .coordinators import (
    SunlitDeviceCoordinator,
    SunlitFamilyCoordinator,
    SunlitMpptEnergyCoordinator,
    SunlitStrategyHistoryCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunlit REST from a config entry."""

    access_token = entry.data[CONF_ACCESS_TOKEN]
    families = entry.data[CONF_FAMILIES]

    # Get HomeAssistant version for User-Agent
    try:
        from homeassistant.const import __version__ as ha_version
    except ImportError:
        # Fallback if __version__ is not available
        ha_version = getattr(hass, "version", "unknown")

    session = async_get_clientsession(hass)
    api_client = SunlitApiClient(session, access_token, ha_version=str(ha_version))

    coordinators = {}

    # Create coordinators for selected families
    for family_id, family_info in families.items():
        # Create specialized coordinators
        family_coordinator = SunlitFamilyCoordinator(
            hass,
            api_client=api_client,
            family_id=str(family_info["id"]),
            family_name=family_info["name"],
        )
        await family_coordinator.async_config_entry_first_refresh()

        device_coordinator = SunlitDeviceCoordinator(
            hass,
            api_client=api_client,
            family_id=str(family_info["id"]),
            family_name=family_info["name"],
        )
        await device_coordinator.async_config_entry_first_refresh()

        strategy_coordinator = SunlitStrategyHistoryCoordinator(
            hass,
            api_client=api_client,
            family_id=str(family_info["id"]),
            family_name=family_info["name"],
        )
        await strategy_coordinator.async_config_entry_first_refresh()

        mppt_coordinator = SunlitMpptEnergyCoordinator(
            hass,
            device_coordinator=device_coordinator,
            family_id=str(family_info["id"]),
            family_name=family_info["name"],
        )
        await mppt_coordinator.async_config_entry_first_refresh()

        # Store all coordinators
        coordinators[family_id] = {
            "family": family_coordinator,
            "device": device_coordinator,
            "strategy": strategy_coordinator,
            "mppt": mppt_coordinator,
        }

    # Check for devices without a spaceId (global/unassigned devices)
    try:
        all_devices = await api_client.get_device_list()
        unassigned_devices = [d for d in all_devices if d.get("spaceId") is None]

        if unassigned_devices:
            _LOGGER.info(
                "Found %d unassigned devices (no spaceId), creating global coordinator",
                len(unassigned_devices),
            )
            # Create specialized coordinators for global devices
            global_family_coordinator = SunlitFamilyCoordinator(
                hass,
                api_client=api_client,
                family_id="global",
                family_name="Unassigned Devices",
                is_global=True,
            )
            await global_family_coordinator.async_config_entry_first_refresh()

            global_device_coordinator = SunlitDeviceCoordinator(
                hass,
                api_client=api_client,
                family_id="global",
                family_name="Unassigned Devices",
                is_global=True,
            )
            await global_device_coordinator.async_config_entry_first_refresh()

            # Note: No strategy or MPPT coordinators for global devices
            coordinators["global"] = {
                "family": global_family_coordinator,
                "device": global_device_coordinator,
                "strategy": None,  # Not applicable for global devices
                "mppt": None,  # Not applicable for global devices
            }
    except Exception as err:
        _LOGGER.warning("Failed to check for unassigned devices: %s", err)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
