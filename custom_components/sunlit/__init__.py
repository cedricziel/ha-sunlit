"""The Sunlit REST integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    API_BASE_URL,
    API_FAMILY_DATA,
    CONF_API_KEY,
    CONF_FAMILIES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunlit REST from a config entry."""
    
    api_key = entry.data[CONF_API_KEY]
    families = entry.data.get(CONF_FAMILIES, {})
    
    # Handle legacy config entries
    if not families and "api_url" in entry.data:
        # Legacy single endpoint configuration
        api_url = entry.data["api_url"]
        auth_type = entry.data.get("auth_type")
        
        session = async_get_clientsession(hass)
        headers = {}
        if auth_type == "bearer" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == "api_key" and api_key:
            headers["X-API-Key"] = api_key
            
        coordinator = SunlitDataUpdateCoordinator(
            hass,
            session=session,
            api_url=api_url,
            headers=headers,
            family_id="legacy",
            family_name="Legacy",
        )
        
        await coordinator.async_config_entry_first_refresh()
        
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {"legacy": coordinator}
    else:
        # New multi-family configuration
        session = async_get_clientsession(hass)
        headers = {"Authorization": f"Bearer {api_key}"}
        
        coordinators = {}
        for family_id, family_info in families.items():
            api_url = f"{API_BASE_URL}{API_FAMILY_DATA}".replace("{family_id}", str(family_info['id']))
            
            coordinator = SunlitDataUpdateCoordinator(
                hass,
                session=session,
                api_url=api_url,
                headers=headers,
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
        session: aiohttp.ClientSession,
        api_url: str,
        headers: dict[str, str],
        family_id: str = "default",
        family_name: str = "Default",
    ) -> None:
        """Initialize."""
        self.session = session
        self.api_url = api_url
        self.headers = headers
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
            async with async_timeout.timeout(10):
                async with self.session.get(
                    self.api_url,
                    headers=self.headers,
                ) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Error {response.status}")

                    data = await response.json()

                    _LOGGER.debug("Received data for family %s: %s", self.family_name, data)

                    return self._process_data(data)

        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout error fetching data") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    def _process_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process the raw data from the API."""
        processed = {}

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float, str, bool)):
                    processed[key] = value
                elif isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, (int, float, str, bool)):
                            processed[f"{key}_{sub_key}"] = sub_value
        elif isinstance(data, list) and data:
            for idx, item in enumerate(data[:10]):
                if isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, (int, float, str, bool)):
                            processed[f"item_{idx}_{key}"] = value

        return processed