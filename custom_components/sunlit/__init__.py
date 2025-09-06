"""The Sunlit REST integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_client import SunlitApiClient
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_API_KEY,
    CONF_FAMILIES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunlit REST from a config entry."""
    
    api_key = entry.data[CONF_API_KEY]
    families = entry.data[CONF_FAMILIES]
    
    session = async_get_clientsession(hass)
    api_client = SunlitApiClient(session, api_key)
    
    coordinators = {}
    for family_id, family_info in families.items():
        coordinator = SunlitDataUpdateCoordinator(
            hass,
            api_client=api_client,
            family_id=str(family_info['id']),
            family_name=family_info['name'],
        )
        
        await coordinator.async_config_entry_first_refresh()
        coordinators[family_id] = coordinator
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class SunlitDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the REST API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SunlitApiClient,
        family_id: str,
        family_name: str,
    ) -> None:
        """Initialize."""
        self.api_client = api_client
        self.family_id = family_id
        self.family_name = family_name

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{family_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from REST API."""
        try:
            # Fetch raw data from API
            raw_data = await self.api_client.fetch_family_data(self.family_id)
            
            _LOGGER.debug("Received data for family %s: %s", self.family_name, raw_data)
            
            # Process data into sensor-friendly format
            return self.api_client.process_sensor_data(raw_data)
            
        except Exception as err:
            raise UpdateFailed(f"Error fetching data for family {self.family_name}: {err}") from err