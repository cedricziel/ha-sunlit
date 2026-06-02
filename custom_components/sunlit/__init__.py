"""The Sunlit REST integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_client import SunlitApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BATTERIES,
    CONF_FAMILIES,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_ENABLE_SOC_EVENTS,
    OPT_MIN_EVENT_INTERVAL,
    OPT_SOC_CHANGE_THRESHOLD,
    OPT_SOC_THRESHOLD_CRITICAL_HIGH,
    OPT_SOC_THRESHOLD_CRITICAL_LOW,
    OPT_SOC_THRESHOLD_HIGH,
    OPT_SOC_THRESHOLD_LOW,
)
from .coordinators import (
    SunlitDeviceCoordinator,
    SunlitFamilyCoordinator,
    SunlitMpptEnergyCoordinator,
    SunlitStrategyHistoryCoordinator,
)
from .event_manager import SunlitEventManager
from .local.manager import LocalChannelManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating config entry from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version == 1 and config_entry.minor_version < 2:
        # Migrate to version 1.2: Add default options if not present
        new_options = {**DEFAULT_OPTIONS}
        # Preserve any existing options
        if config_entry.options:
            new_options.update(config_entry.options)

        hass.config_entries.async_update_entry(
            config_entry,
            options=new_options,
            minor_version=2,
        )

        _LOGGER.info("Migration to version 1.2 successful: Added default options")

    return True


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
    event_managers = {}

    # Prepare SOC event options if enabled
    # After migration, options will always contain defaults
    soc_events_enabled = entry.options[OPT_ENABLE_SOC_EVENTS]
    soc_event_options = None

    if soc_events_enabled:
        soc_event_options = {
            "soc_thresholds": {
                "critical_low": entry.options[OPT_SOC_THRESHOLD_CRITICAL_LOW],
                "low": entry.options[OPT_SOC_THRESHOLD_LOW],
                "high": entry.options[OPT_SOC_THRESHOLD_HIGH],
                "critical_high": entry.options[OPT_SOC_THRESHOLD_CRITICAL_HIGH],
            },
            "soc_change_threshold": entry.options[OPT_SOC_CHANGE_THRESHOLD],
            "min_event_interval_seconds": entry.options[OPT_MIN_EVENT_INTERVAL],
        }

    # Create coordinators for selected families
    for family_id, family_info in families.items():
        # Create event manager if SOC events are enabled
        event_manager = None
        if soc_events_enabled:
            event_manager = SunlitEventManager(
                hass,
                family_id=str(family_info["id"]),
                config_options=soc_event_options,
            )
            event_managers[family_id] = event_manager

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
            event_manager=event_manager,
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

    # Spin up the opt-in local-mode TCP channel. The manager watches each
    # family's device coordinator and, for batteries with local mode enabled
    # and a host known (from zeroconf), maintains a persistent TCP client
    # that pushes telemetry into the same coordinator the cloud poll feeds.
    device_coordinators = {
        family_id: coord_set["device"] for family_id, coord_set in coordinators.items()
    }
    local_manager = LocalChannelManager(
        hass,
        device_coordinators=device_coordinators,
        batteries=entry.data.get(CONF_BATTERIES, {}),
    )
    local_manager.start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinators": coordinators,
        "event_managers": event_managers,
        "api_client": api_client,
        "local_manager": local_manager,
    }

    # Add update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Reload the integration when options change
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        local_manager = entry_data.get("local_manager")
        if local_manager is not None:
            await local_manager.async_stop()

    return unload_ok
