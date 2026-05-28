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
    API_BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_BATTERIES,
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
from .local.protocol import DEFAULT_PORT as LOCAL_TCP_PORT

_LOGGER = logging.getLogger(__name__)


def _parse_battery_discovery(
    discovery_info: ZeroconfServiceInfo,
) -> dict[str, Any] | None:
    """Extract battery LAN info from a ``hp-bk215`` zeroconf advertisement.

    Returns a dict with serial/host/port and optional firmware/hardware
    versions, or ``None`` if the advertisement lacks the required fields.

    The TXT ``port`` property carries the TCP control port (observed 8000);
    the mDNS service port (``discovery_info.port``) advertises the device's
    ``_http`` port and is not what the local-mode channel uses.
    """
    properties = discovery_info.properties or {}
    serial = properties.get("id")
    if not serial:
        return None
    host = discovery_info.host
    if not host:
        return None
    port_raw = properties.get("port")
    try:
        port = int(port_raw) if port_raw is not None else LOCAL_TCP_PORT
    except (TypeError, ValueError):
        port = LOCAL_TCP_PORT
    return {
        "serial": serial,
        "host": host,
        "port": port,
        "sw_version": properties.get("fw_ver"),
        "hw_version": properties.get("model"),
    }


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
        self._discovered_battery: dict[str, Any] | None = None

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle a battery discovered via mDNS/zeroconf.

        The BK215 (Highpower) advertises itself as ``hp-bk215*`` over
        ``_http._tcp.local.``. Two roles for this step:

        - **Onboarding** — when no cloud entry exists yet, surface the device
          and funnel the user into the normal credential flow; the captured
          LAN info is stamped onto the entry as it's created.
        - **Address refresh** — when an entry already exists, merge the
          (possibly changed) host/port into ``entry.data[CONF_BATTERIES]``
          so the opt-in local-mode channel can use it. DHCP can rotate the
          IP, so we accept rediscoveries instead of ignoring them.
        """
        battery = _parse_battery_discovery(discovery_info)
        if battery is None:
            return self.async_abort(reason="invalid_discovery")
        self._discovered_battery = battery

        # Dedupe concurrent discovery flows for the same battery.
        await self.async_set_unique_id(battery["serial"])
        self._abort_if_unique_id_configured()

        # If a cloud entry is already set up, this advertisement is just a
        # LAN refresh: merge the LAN info and reload only on real changes.
        existing = self._existing_entry()
        if existing is not None:
            if self._merge_battery_into_entry(existing, battery):
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(existing.entry_id)
                )
            return self.async_abort(reason="already_configured")

        self.context["title_placeholders"] = {
            "name": f"Sunlit BK215 ({battery['serial']})"
        }

        return await self.async_step_zeroconf_confirm()

    def _existing_entry(self) -> config_entries.ConfigEntry | None:
        """Return the integration's single cloud entry, or None."""
        entries = self._async_current_entries()
        return entries[0] if entries else None

    def _merge_battery_into_entry(
        self,
        entry: config_entries.ConfigEntry,
        battery: dict[str, Any],
    ) -> bool:
        """Merge a discovered battery into ``entry.data``; return True if changed."""
        current = entry.data.get(CONF_BATTERIES, {}) or {}
        if current.get(battery["serial"]) == battery:
            return False
        updated = {**current, battery["serial"]: battery}
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_BATTERIES: updated}
        )
        return True

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a discovered battery and continue to cloud login."""
        if user_input is not None:
            return await self.async_step_user()

        serial = (
            self._discovered_battery["serial"]
            if self._discovered_battery is not None
            else "unknown"
        )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"serial_number": serial},
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
            description_placeholders={"api_url": API_BASE_URL},
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

                # Stamp any zeroconf-discovered battery onto the new entry so
                # the local channel can pick up the LAN address without
                # waiting for another mDNS round.
                batteries: dict[str, dict[str, Any]] = {}
                if self._discovered_battery is not None:
                    batteries[self._discovered_battery["serial"]] = (
                        self._discovered_battery
                    )

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_EMAIL: self.email,
                        CONF_ACCESS_TOKEN: self.access_token,
                        CONF_FAMILIES: self.families,
                        CONF_BATTERIES: batteries,
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
