"""Config flow for Sunlit REST integration."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    API_BASE_URL,
    API_FAMILY_LIST,
    CONF_API_KEY,
    CONF_FAMILIES,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sunlit REST."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.api_key: str | None = None
        self.families: dict[str, Any] = {}
        self.available_families: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API key entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.api_key = user_input[CONF_API_KEY]
            
            try:
                # Test connection and fetch families
                self.available_families = await self._fetch_families(
                    self.hass,
                    self.api_key
                )
                
                if not self.available_families:
                    errors["base"] = "no_families"
                else:
                    # Create unique ID based on API key hash
                    await self.async_set_unique_id(
                        hashlib.md5(self.api_key.encode()).hexdigest()[:8]
                    )
                    self._abort_if_unique_id_configured()
                    
                    # Move to family selection
                    return await self.async_step_select_families()
                    
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors,
            description_placeholders={"api_url": API_BASE_URL}
        )

    async def async_step_select_families(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle family selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_family_ids = user_input["families"]
            
            if not selected_family_ids:
                errors["base"] = "no_selection"
            else:
                # Build families dictionary with selected families
                self.families = {}
                for family_id in selected_family_ids:
                    # Find family details from available families
                    family_data = next(
                        (f for f in self.available_families if str(f["id"]) == family_id),
                        None
                    )
                    if family_data:
                        self.families[family_id] = {
                            "id": family_data["id"],
                            "name": family_data["name"],
                            "address": family_data.get("address", ""),
                            "device_count": family_data.get("deviceCount", 0),
                        }
                
                # Create config entry with selected families
                family_names = [f["name"] for f in self.families.values()]
                title = f"Sunlit ({', '.join(family_names)})"
                
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_API_KEY: self.api_key,
                        CONF_FAMILIES: self.families,
                    },
                )

        # Create options for family selection
        family_options = {
            str(family["id"]): f"{family['name']} - {family.get('address', 'Unknown')} ({family.get('deviceCount', 0)} devices)"
            for family in self.available_families
        }

        schema = vol.Schema(
            {
                vol.Required("families"): cv.multi_select(family_options),
            }
        )

        return self.async_show_form(
            step_id="select_families",
            data_schema=schema,
            errors=errors
        )

    async def _fetch_families(
        self,
        hass: HomeAssistant,
        api_key: str,
    ) -> list[dict[str, Any]]:
        """Fetch available families from the API."""
        session = async_get_clientsession(hass)
        headers = {"Authorization": f"Bearer {api_key}"}
        
        try:
            async with session.get(
                f"{API_BASE_URL}{API_FAMILY_LIST}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 401:
                    raise InvalidAuth
                if response.status >= 400:
                    raise CannotConnect
                    
                data = await response.json()
                
                # Extract families from response
                if data.get("code") == 0 and "content" in data:
                    return data["content"]
                else:
                    _LOGGER.error("Unexpected API response: %s", data)
                    return []
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching families: %s", err)
            raise CannotConnect from err


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
