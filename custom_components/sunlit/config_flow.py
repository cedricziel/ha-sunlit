"""Config flow for Sunlit REST integration."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api_client import SunlitApiClient, SunlitAuthError, SunlitConnectionError
from .const import CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_FAMILIES, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sunlit REST."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.email: str | None = None
        self.access_token: str | None = None
        self.families: dict[str, Any] = {}
        self.available_families: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - email/password entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            try:
                # Login and fetch families
                session = async_get_clientsession(self.hass)
                client = SunlitApiClient(session)

                # Login to get access token
                login_response = await client.login(self.email, password)
                self.access_token = login_response.get("access_token")

                if not self.access_token:
                    errors["base"] = "invalid_auth"
                else:
                    # Fetch families with the authenticated client
                    self.available_families = await client.fetch_families()

                    if not self.available_families:
                        errors["base"] = "no_families"
                    else:
                        # Create unique ID based on email hash
                        await self.async_set_unique_id(
                            hashlib.md5(self.email.encode()).hexdigest()[:8]
                        )
                        self._abort_if_unique_id_configured()

                        # Move to family selection
                        return await self.async_step_select_families()

            except SunlitConnectionError:
                errors["base"] = "cannot_connect"
            except SunlitAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"api_url": "https://api.sunlitsolar.de"},
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
                        (
                            f
                            for f in self.available_families
                            if str(f["id"]) == family_id
                        ),
                        None,
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
                        CONF_EMAIL: self.email,
                        CONF_ACCESS_TOKEN: self.access_token,
                        CONF_FAMILIES: self.families,
                    },
                )

        # Create options for family selection
        family_options = {
            str(family["id"]): (
                f"{family['name']} - {family.get('address', 'Unknown')} "
                f"({family.get('deviceCount', 0)} devices)"
            )
            for family in self.available_families
        }

        schema = vol.Schema(
            {
                vol.Required("families"): cv.multi_select(family_options),
            }
        )

        return self.async_show_form(
            step_id="select_families", data_schema=schema, errors=errors
        )


""
