"""Config flow for Sunlit REST integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_API_URL,
    CONF_API_KEY,
    CONF_AUTH_TYPE,
    AUTH_TYPE_NONE,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_API_KEY,
    AUTH_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sunlit REST."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                await self._test_connection(
                    self.hass,
                    user_input[CONF_API_URL],
                    user_input.get(CONF_AUTH_TYPE, AUTH_TYPE_NONE),
                    user_input.get(CONF_API_KEY),
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_API_URL])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"Sunlit REST ({user_input[CONF_API_URL]})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_URL): str,
                vol.Required(CONF_AUTH_TYPE, default=AUTH_TYPE_NONE): vol.In(
                    AUTH_TYPES
                ),
                vol.Optional(CONF_API_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def _test_connection(
        self,
        hass: HomeAssistant,
        api_url: str,
        auth_type: str,
        api_key: str | None,
    ) -> None:
        """Test if we can connect to the REST API."""
        session = async_get_clientsession(hass)
        
        headers = {}
        if auth_type == AUTH_TYPE_BEARER and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == AUTH_TYPE_API_KEY and api_key:
            headers["X-API-Key"] = api_key
        
        try:
            async with session.get(
                api_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 401:
                    raise InvalidAuth
                if response.status >= 400:
                    raise CannotConnect
        except aiohttp.ClientError as err:
            raise CannotConnect from err


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""