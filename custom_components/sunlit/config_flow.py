"""Config flow for Sunlit REST integration."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api_client import SunlitApiClient, SunlitAuthError, SunlitConnectionError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_FAMILIES,
    CONF_PASSWORD,
    DEFAULT_ENABLE_SOC_EVENTS,
    DEFAULT_MIN_EVENT_INTERVAL,
    DEFAULT_OPTIONS,
    DEFAULT_SOC_CHANGE_THRESHOLD,
    DEFAULT_SOC_THRESHOLD_CRITICAL_HIGH,
    DEFAULT_SOC_THRESHOLD_CRITICAL_LOW,
    DEFAULT_SOC_THRESHOLD_HIGH,
    DEFAULT_SOC_THRESHOLD_LOW,
    DOMAIN,
    OPT_ENABLE_SOC_EVENTS,
    OPT_MIN_EVENT_INTERVAL,
    OPT_SOC_CHANGE_THRESHOLD,
    OPT_SOC_THRESHOLD_CRITICAL_HIGH,
    OPT_SOC_THRESHOLD_CRITICAL_LOW,
    OPT_SOC_THRESHOLD_HIGH,
    OPT_SOC_THRESHOLD_LOW,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sunlit REST."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    def __init__(self):
        """Initialize the config flow."""
        self.email: str | None = None
        self.access_token: str | None = None
        self.families: dict[str, Any] = {}
        self.available_families: list[dict[str, Any]] = []
        self._discovered_serial: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle a battery discovered via mDNS/zeroconf.

        The BK215 (Highpower) advertises itself on the local network as
        ``hp-bk215*`` over ``_http._tcp.local.``. This integration is
        cloud-polling, so discovery only acts as an onboarding trigger:
        we surface the device and then funnel the user into the normal
        cloud credential flow. The discovered serial is recorded so a
        future opt-in local-polling mode can reuse it.
        """
        properties = discovery_info.properties
        self._discovered_serial = properties.get("id")

        # Dedupe concurrent discovery flows for the same battery.
        await self.async_set_unique_id(self._discovered_serial or DOMAIN)
        self._abort_if_unique_id_configured()

        # Single-entry integration: one cloud account covers every device,
        # so once anything is set up there is nothing more to discover.
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        self.context["title_placeholders"] = {
            "name": (
                f"Sunlit BK215 ({self._discovered_serial})"
                if self._discovered_serial
                else "Sunlit BK215"
            )
        }

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a discovered battery and continue to cloud login."""
        if user_input is not None:
            return await self.async_step_user()

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "serial_number": self._discovered_serial or "unknown"
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - email/password entry."""
        # Check if already configured
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

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
                    options=DEFAULT_OPTIONS,
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


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Sunlit integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options for the Sunlit integration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Build the options schema with current values as defaults
        options_schema = vol.Schema(
            {
                vol.Optional(
                    OPT_ENABLE_SOC_EVENTS,
                    default=self.config_entry.options.get(
                        OPT_ENABLE_SOC_EVENTS, DEFAULT_ENABLE_SOC_EVENTS
                    ),
                ): BooleanSelector(),
                vol.Optional(
                    OPT_SOC_THRESHOLD_CRITICAL_LOW,
                    default=self.config_entry.options.get(
                        OPT_SOC_THRESHOLD_CRITICAL_LOW,
                        DEFAULT_SOC_THRESHOLD_CRITICAL_LOW,
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=50,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    OPT_SOC_THRESHOLD_LOW,
                    default=self.config_entry.options.get(
                        OPT_SOC_THRESHOLD_LOW, DEFAULT_SOC_THRESHOLD_LOW
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=60,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    OPT_SOC_THRESHOLD_HIGH,
                    default=self.config_entry.options.get(
                        OPT_SOC_THRESHOLD_HIGH, DEFAULT_SOC_THRESHOLD_HIGH
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=60,
                        max=95,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    OPT_SOC_THRESHOLD_CRITICAL_HIGH,
                    default=self.config_entry.options.get(
                        OPT_SOC_THRESHOLD_CRITICAL_HIGH,
                        DEFAULT_SOC_THRESHOLD_CRITICAL_HIGH,
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=80,
                        max=100,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    OPT_SOC_CHANGE_THRESHOLD,
                    default=self.config_entry.options.get(
                        OPT_SOC_CHANGE_THRESHOLD, DEFAULT_SOC_CHANGE_THRESHOLD
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=50,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="%",
                    )
                ),
                vol.Optional(
                    OPT_MIN_EVENT_INTERVAL,
                    default=self.config_entry.options.get(
                        OPT_MIN_EVENT_INTERVAL, DEFAULT_MIN_EVENT_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=3600,
                        step=10,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "config_title": self.config_entry.title,
            },
        )
