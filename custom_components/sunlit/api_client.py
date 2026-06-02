"""Sunlit API Client for handling all API interactions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_BATTERY_IO_POWER,
    API_BATTERY_LOCAL_MODE_CONFIG,
    API_CHARGING_BOX_CHECK_STRATEGY,
    API_DEVICE_DETAILS,
    API_DEVICE_LIST,
    API_DEVICE_STATISTICS,
    API_FAMILY_LIST,
    API_NOTIFICATION_LIST,
    API_RABOT_DAY_PRICE,
    API_SPACE_CURRENT_STRATEGY,
    API_SPACE_INDEX,
    API_SPACE_SOC,
    API_SPACE_STATISTICS_DYNAMIC_ENERGY,
    API_SPACE_STATISTICS_STATIC,
    API_SPACE_STRATEGY_HISTORY,
    API_STRATEGY_DEVICE_STATUS,
    API_STRATEGY_SETTING_DETAIL,
    API_TARIFF_INDEX,
    API_TARIFF_STRATEGY_ADD,
    API_USER_LOGIN,
)

_LOGGER = logging.getLogger(__name__)


class SunlitApiError(Exception):
    """Base exception for Sunlit API errors."""


class SunlitAuthError(SunlitApiError):
    """Exception for authentication errors."""


class SunlitConnectionError(SunlitApiError):
    """Exception for connection errors."""


def _format_api_message(message: Any) -> str:
    """Render an API error message into a readable string.

    The Sunlit API returns localized error messages as a dict keyed by
    language code, e.g. ``{"DE": "Fehler: ..."}``. Logging that raw makes
    error lines hard to read, so pick a single human-readable string,
    preferring English when available.
    """
    if isinstance(message, dict):
        for lang in ("EN", "en", "DE", "de"):
            if message.get(lang):
                return str(message[lang])
        # Unknown language keys: fall back to the first value, then the dict.
        return str(next(iter(message.values()), message))
    return str(message)


class SunlitApiClient:
    """Client for interacting with the Sunlit Solar API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str | None = None,
        timeout: int = 10,
        ha_version: str | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session (injected for testability)
            access_token: Bearer token for authentication (optional, can be set after login)
            timeout: Request timeout in seconds
            ha_version: HomeAssistant version for User-Agent
        """
        self._session = session
        self._access_token = access_token
        self._timeout = timeout
        self._base_url = API_BASE_URL
        self._ha_version = ha_version or "unknown"

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        from .const import GITHUB_URL, INTEGRATION_NAME, VERSION

        # Build User-Agent string
        user_agent = f"{INTEGRATION_NAME}/{VERSION} (+{GITHUB_URL})"
        if self._ha_version != "unknown":
            user_agent += f" HomeAssistant/{self._ha_version}"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        }

        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional request parameters

        Returns:
            Parsed JSON response

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: Other API errors
        """
        url = f"{self._base_url}{endpoint}"
        headers = self._build_headers()

        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                ) as response:
                    if response.status == 401:
                        raise SunlitAuthError("Invalid authentication token")

                    if response.status >= 400:
                        text = await response.text()
                        raise SunlitConnectionError(
                            f"API request failed with status {response.status}: {text}"
                        )

                    data = await response.json()

                    # Check for API-level errors
                    if isinstance(data, dict) and data.get("code") != 0:
                        message = _format_api_message(
                            data.get("message", "Unknown error")
                        )
                        raise SunlitApiError(f"API error: {message}")

                    # Log full response for debugging
                    _LOGGER.debug("API Response from %s: %s", url, data)
                    return data

        except aiohttp.ClientError as err:
            raise SunlitConnectionError(f"Connection error: {err}") from err
        except TimeoutError as err:
            raise SunlitConnectionError(
                f"Request timeout after {self._timeout}s"
            ) from err

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Login with email and password to get access token.

        Args:
            email: User email address
            password: User password

        Returns:
            Login response containing access_token

        Raises:
            SunlitAuthError: If login fails
        """
        payload = {
            "account": email,
            "password": password,
        }

        try:
            _LOGGER.debug("Attempting login for user: %s", email)
            response = await self._make_request(
                "POST",
                API_USER_LOGIN,
                json=payload,
            )

            # Extract token from response
            if response and "content" in response:
                content = response["content"]
                if "access_token" in content:
                    # Store the token for future requests
                    self._access_token = content["access_token"]
                    _LOGGER.info("Login successful for user: %s", email)
                    # Log response with masked token for debugging
                    debug_content = content.copy()
                    if "access_token" in debug_content:
                        debug_content["access_token"] = "***MASKED***"
                    _LOGGER.debug("Login response for %s: %s", email, debug_content)
                    return content

            _LOGGER.error("Invalid login response structure: %s", response)
            raise SunlitAuthError("Invalid login response structure")

        except SunlitApiError:
            raise
        except Exception as err:
            _LOGGER.error("Login failed: %s", err)
            raise SunlitAuthError(f"Login failed: {err}") from err

    async def fetch_families(self) -> list[dict[str, Any]]:
        """Fetch list of available families.

        Returns:
            List of family dictionaries with id, name, address, deviceCount

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            response = await self._make_request("GET", API_FAMILY_LIST)

            # Extract families from response
            # Log full response for debugging
            _LOGGER.debug("Family list response: %s", response)

            if "content" in response:
                families = response["content"]
                _LOGGER.debug("Fetched %d families", len(families))
                return families

            _LOGGER.warning("Unexpected response format: %s", response)
            return []

        except SunlitApiError as err:
            _LOGGER.error("Failed to fetch families: %s", err)
            raise

    async def fetch_device_statistics(self, device_id: str | int) -> dict[str, Any]:
        """Fetch detailed statistics for a specific device.

        Args:
            device_id: The device ID to fetch statistics for

        Returns:
            Dictionary containing detailed device statistics including:
            - Basic info: deviceId, sn, status, deviceType
            - Battery data: batterySoc, battery1Soc, battery2Soc, battery3Soc
            - Power data: inputPowerTotal, outputPowerTotal
            - MPPT data: batteryMppt1Data, batteryMppt2Data, battery1MpptData, etc.
            - Timing data: chargeRemaining, dischargeRemaining

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"deviceId": int(device_id)}

            response = await self._make_request(
                "POST", API_DEVICE_STATISTICS, json=payload
            )

            # Extract content from response
            # Log full response for debugging
            _LOGGER.debug("Device statistics response for %s: %s", device_id, response)

            if "content" in response:
                data = response["content"]
                _LOGGER.debug(
                    "Fetched statistics for device %s (type: %s, status: %s, SOC: %s%%)",
                    device_id,
                    data.get("deviceType", "Unknown"),
                    data.get("status", "Unknown"),
                    data.get("batterySoc", "N/A"),
                )
                return data

            return response

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch statistics for device %s: %s", device_id, err
            )
            raise

    async def fetch_battery_io_power(
        self,
        device_id: str | int,
        year: str | int,
        month: str | int,
        day: str | int,
    ) -> list[dict[str, Any]]:
        """Fetch battery input/output power statistics for a specific device and date.

        Args:
            device_id: The device ID to fetch statistics for
            year: Year (e.g., "2025" or 2025)
            month: Month (e.g., "09" or 9)
            day: Day (e.g., "06" or 6)

        Returns:
            List of power readings with:
            - key: Time in HH:MM format
            - batteryInputPower: Input power in watts
            - batteryOutputPower: Output power in watts

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            # Format date components with leading zeros
            payload = {
                "deviceId": int(device_id),
                "year": str(year),
                "month": f"{int(month):02d}",
                "day": f"{int(day):02d}",
            }

            response = await self._make_request(
                "POST", API_BATTERY_IO_POWER, json=payload
            )

            # Extract power list from response
            if "content" in response and "powerList" in response["content"]:
                power_list = response["content"]["powerList"]
                _LOGGER.debug(
                    "Fetched %d power readings for device %s on %s-%s-%s",
                    len(power_list),
                    device_id,
                    payload["year"],
                    payload["month"],
                    payload["day"],
                )
                return power_list

            # Return empty list if no power data
            return []

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch battery IO power for device %s: %s", device_id, err
            )
            raise

    async def fetch_battery_io_power_today(
        self, device_id: str | int
    ) -> list[dict[str, Any]]:
        """Fetch today's battery input/output power statistics.

        Args:
            device_id: The device ID to fetch statistics for

        Returns:
            List of today's power readings

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        from datetime import datetime

        now = datetime.now()
        return await self.fetch_battery_io_power(
            device_id, now.year, now.month, now.day
        )

    async def fetch_device_details(self, device_id: str | int) -> dict[str, Any]:
        """Fetch detailed information for a specific device.

        Args:
            device_id: The device ID to fetch details for

        Returns:
            Dictionary containing device details including:
            - deviceId: Device identifier
            - deviceSn: Device serial number
            - deviceType: Type of device (SHELLY_3EM_METER, ENERGY_STORAGE_BATTERY)
            - status: Online/Offline status
            - familyItem: Family the device belongs to
            - manufacturer: Device manufacturer
            - firmwareVersion: Current firmware version
            - and other device-specific fields

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        endpoint = API_DEVICE_DETAILS.replace("{device_id}", str(device_id))

        try:
            # This is a GET endpoint - no JSON payload
            response = await self._make_request("GET", endpoint)

            # Extract data from response
            if "content" in response:
                data = response["content"]
                _LOGGER.debug(
                    "Fetched details for device %s (type: %s, status: %s)",
                    device_id,
                    data.get("deviceType", "Unknown"),
                    data.get("status", "Unknown"),
                )
                return data

            # If no content wrapper, return raw response
            return response

        except SunlitApiError as err:
            _LOGGER.error("Failed to fetch details for device %s: %s", device_id, err)
            raise

    async def fetch_device_list(
        self, family_id: str | int, device_type: str = "ALL"
    ) -> list[dict[str, Any]]:
        """Fetch list of devices for a specific family.

        Args:
            family_id: The family ID to fetch devices for
            device_type: Type of devices to fetch (default: "ALL")
                        Examples: "ALL", "ENERGY_STORAGE_BATTERY", "SHELLY_3EM_METER"

        Returns:
            List of device dictionaries containing:
            - deviceId: Device identifier
            - deviceSn: Device serial number
            - deviceType: Type of device
            - status: Online/Offline status
            - fault: Fault status
            - off: Whether device is off
            - batteryLevel: Battery level percentage (for battery devices)
            - totalAcPower: Total AC power (for meters)
            - today: Today's statistics (for inverters)
            - and other device-specific fields

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"familyId": int(family_id), "deviceType": device_type}

            response = await self._make_request("POST", API_DEVICE_LIST, json=payload)

            # Extract device list from paginated response structure
            # Format: { content: { content: [...devices...], pageable: {...} } }
            if "content" in response and isinstance(response["content"], dict):
                paginated_data = response["content"]
                if "content" in paginated_data and isinstance(
                    paginated_data["content"], list
                ):
                    devices = paginated_data["content"]
                    # Log full response for debugging
                    _LOGGER.debug(
                        "Device list response for family %s: %s", family_id, response
                    )
                    _LOGGER.debug(
                        "Fetched %d devices for family %s (type: %s, page: %d/%d)",
                        len(devices),
                        family_id,
                        device_type,
                        paginated_data.get("number", 0) + 1,
                        paginated_data.get("totalPages", 1),
                    )
                    return devices

            # Return empty list if no devices found
            _LOGGER.debug("No devices found for family %s", family_id)
            return []

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch device list for family %s: %s", family_id, err
            )
            raise

    async def fetch_space_soc(self, space_id: str | int) -> dict[str, Any]:
        """Fetch battery SOC limits configuration for a space/family.

        Args:
            space_id: The space/family ID to fetch SOC configuration for

        Returns:
            Dictionary containing SOC configuration:
            - hwSupportOnePercentage: Hardware supports 1% granularity
            - hwSbmsLimitedDiscSocMin: Hardware discharge SOC minimum
            - hwSbmsLimitedChgSocMax: Hardware charge SOC maximum
            - batteryBmsDiscSocMin: Battery BMS discharge SOC minimum
            - batteryBmsChgSocMax: Battery BMS charge SOC maximum
            - strategySocMax: Strategy SOC maximum
            - strategySocMin: Strategy SOC minimum
            - haDodMinSoc: Home automation depth of discharge minimum SOC
            - evDodMinSoc: EV depth of discharge minimum SOC
            - chgDodMaxSoc: Charge depth of discharge maximum SOC

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"spaceId": int(space_id)}
            response = await self._make_request("POST", API_SPACE_SOC, json=payload)

            # Extract data from response
            # Log full response for debugging
            _LOGGER.debug("Space SOC response for %s: %s", space_id, response)

            if "content" in response:
                data = response["content"]
                _LOGGER.debug(
                    "Fetched SOC config for space %s: hw_min=%s, hw_max=%s",
                    space_id,
                    data.get("hwSbmsLimitedDiscSocMin"),
                    data.get("hwSbmsLimitedChgSocMax"),
                )
                return data

            return {}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch SOC configuration for space %s: %s", space_id, err
            )
            raise

    async def fetch_space_statistics_static(
        self, space_id: str | int
    ) -> dict[str, Any]:
        """Fetch lifetime yield and earnings totals for a space/family.

        Args:
            space_id: The space/family ID to fetch lifetime statistics for

        Returns:
            Dictionary containing cumulative totals:
            - totalYield: Lifetime energy yield in kWh
            - totalEarnings: {earnings, currency}

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"spaceId": int(space_id)}
            response = await self._make_request(
                "POST", API_SPACE_STATISTICS_STATIC, json=payload
            )

            _LOGGER.debug(
                "Space static statistics response for %s: %s", space_id, response
            )

            if "content" in response:
                return response["content"]

            return {}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch lifetime statistics for space %s: %s", space_id, err
            )
            raise

    async def fetch_notification_list(
        self, page: int = 0, size: int = 20
    ) -> dict[str, Any]:
        """Fetch the paginated notification feed for the account.

        Args:
            page: Page number (0-based)
            size: Page size

        Returns:
            Paginated content dict with a "content" list of notification items
            ({id, type, title, content, read, deviceSn, deviceType, space, ...}).

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"page": page, "size": size}
            response = await self._make_request(
                "POST", API_NOTIFICATION_LIST, json=payload
            )

            if "content" in response:
                return response["content"]

            return {}

        except SunlitApiError as err:
            _LOGGER.error("Failed to fetch notification list: %s", err)
            raise

    async def fetch_space_statistics_dynamic_energy(
        self,
        space_id: str | int,
        year: int | None = None,
        month: int | None = None,
    ) -> dict[str, Any]:
        """Fetch energy distribution & self-consumption for a space.

        Granularity follows the optional year/month (see openapi.yaml). With
        no year/month the response is all-time per-year buckets.

        Args:
            space_id: The space/family ID
            year: Optional year (selects per-month or, with month, per-day)
            month: Optional month 1-12 (requires year; yields per-day)

        Returns:
            Dictionary containing:
            - totalSelfUseRate, selfSufficiencyRate (0-1 ratios)
            - totalYield, totalConsumption, totalEnergyFromPv
            - energyDistributions: per-bucket list

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload: dict[str, Any] = {"spaceId": int(space_id)}
            if year is not None:
                payload["year"] = int(year)
            if month is not None:
                payload["month"] = int(month)
            response = await self._make_request(
                "POST", API_SPACE_STATISTICS_DYNAMIC_ENERGY, json=payload
            )

            _LOGGER.debug(
                "Space dynamic energy response for %s: %s", space_id, response
            )

            if "content" in response:
                return response["content"]

            return {}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch energy distribution for space %s: %s",
                space_id,
                err,
            )
            raise

    async def update_battery_local_mode(
        self, device_sn: str, enable: bool
    ) -> dict[str, Any]:
        """Enable or disable local mode for a battery (control endpoint).

        Local mode lets the battery run from on-device logic rather than cloud
        strategy. This mutates device state.

        Args:
            device_sn: Battery serial number
            enable: True to enable local mode, False to disable

        Returns:
            The raw API envelope (``content`` is null on success)

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        payload = {"enable": enable, "deviceSn": device_sn}
        _LOGGER.debug("Setting battery %s local mode to %s", device_sn, enable)
        return await self._make_request(
            "POST", API_BATTERY_LOCAL_MODE_CONFIG, json=payload
        )

    async def set_tariff_strategy(
        self,
        family_id: str | int,
        low_price_strategy: dict[str, Any],
        high_price_strategy: dict[str, Any],
        enable_switch_notice: bool = True,
    ) -> dict[str, Any]:
        """Add or update the tariff-based battery strategy for a family.

        POSTs to /v1.6/tariffStrategy/add. Configures the battery's behaviour
        for low- and high-price tariff windows in a single call. The endpoint
        is all-or-nothing: callers must always supply both low and high blocks.

        Args:
            family_id: The family/space ID
            low_price_strategy: Dict with keys ``strategy``, ``socMin``,
                ``socMax`` and optional ``defaultExpectInverterOutput``
            high_price_strategy: Dict with keys ``strategy``, ``socMin``,
                ``socMax`` and optional ``smartStrategyMode``,
                ``smartStrategyFullMode``
            enable_switch_notice: Send a push notification when the strategy
                switches between price bands

        Returns:
            The raw API envelope (``content`` is null on success)

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        payload = {
            "familyId": int(family_id),
            "lowPriceStrategy": low_price_strategy,
            "highPriceStrategy": high_price_strategy,
            "enableSwitchNotice": enable_switch_notice,
        }
        _LOGGER.debug(
            "Setting tariff strategy for family %s: low=%s high=%s",
            family_id,
            low_price_strategy,
            high_price_strategy,
        )
        return await self._make_request("POST", API_TARIFF_STRATEGY_ADD, json=payload)

    async def fetch_tariff_setup(self, family_id: str | int) -> dict[str, Any] | None:
        """Read the cloud's authoritative tariff-strategy setup for a family.

        POSTs to /v1.8/strategy/setting/detail with strategyType=TariffStrategy.
        The cloud returns the currently-active low- and high-price strategy
        blocks — the same shape we send to /v1.6/tariffStrategy/add.

        This is the read side that complements ``set_tariff_strategy`` and
        lets the coordinator reconcile its in-memory cache against
        out-of-band edits made via the SunEnergyXT app.

        Args:
            family_id: The family/space ID

        Returns:
            A ``{"low": {...}, "high": {...}, "enableSwitchNotice": bool}``
            dict ready to feed into the coordinator's
            ``update_tariff_setup_field`` machinery, or ``None`` if the cloud
            says no tariff strategy is currently configured (``enabled: false``
            or ``content: null``).

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        payload = {
            "spaceId": int(family_id),
            "primarySpaceId": int(family_id),
            "strategyType": "TariffStrategy",
        }
        _LOGGER.debug("Fetching tariff setup for family %s", family_id)
        envelope = await self._make_request(
            "POST", API_STRATEGY_SETTING_DETAIL, json=payload
        )
        content = (envelope or {}).get("content")
        if not content or not content.get("enabled"):
            return None
        tariff = content.get("tariffStrategy") or {}
        low = tariff.get("lowPriceStrategy")
        high = tariff.get("highPriceStrategy")
        if not low or not high:
            return None
        return {
            "low": low,
            "high": high,
            "enableSwitchNotice": bool(tariff.get("enableSwitchNotice", True)),
        }

    async def fetch_tariff_index(self, space_id: str | int) -> dict[str, Any]:
        """Fetch dynamic electricity tariff/pricing for a space.

        Args:
            space_id: The space/family ID

        Returns:
            Dictionary containing:
            - rabotHasContract: Whether a Rabot dynamic-tariff contract exists
            - rabotHourPriceDTO: Current hourly price block (may be null) with
              priceInCentPerKwh, avgPriceInCentPerKwh, highestPriceInCentPerKwh,
              lowestPriceInCentPerKwh, priceTag, hour, timestamp
            - countryCode

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"spaceId": int(space_id)}
            response = await self._make_request("POST", API_TARIFF_INDEX, json=payload)

            _LOGGER.debug("Tariff index response for %s: %s", space_id, response)

            if "content" in response:
                return response["content"]

            return {}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch tariff index for space %s: %s", space_id, err
            )
            raise

    async def fetch_rabot_day_price(
        self,
        space_id: str | int,
        day: str,
        *,
        show_tax: bool = True,
        show_strategy: bool = False,
    ) -> dict[str, Any]:
        """Fetch the 24 hourly Rabot Charge electricity prices for one day.

        The endpoint is **not** gated on a Rabot Charge contract; it returns the
        German day-ahead market prices for the configured space. Verified
        horizon: today + tomorrow (after ~13:00 CET when EPEX publishes) and
        back ~12 months. Unsupported days return ``code=0`` with an empty
        ``prices`` array.

        Args:
            space_id: The space/family ID.
            day: Local date in ``YYYY-MM-DD`` format.
            show_tax: Whether to include tax in the prices (default True).
            show_strategy: Whether to also return per-hour strategy mode
                (default False; required by the API contract regardless).

        Returns:
            Dictionary containing:
            - prices: list of 24 entries with ``hour`` (0-23),
              ``priceInCentPerKwh``, ``avgPriceInCentPerKwh``, ``priceTag``
              (``VERY_CHEAP``..``VERY_EXPENSIVE``), ``timestamp`` (local),
              ``utcFullTime`` (UTC), and ``mode`` (when ``show_strategy``).
              Empty list when the day is outside the available window.
            - utcOffset: e.g. ``"UTC+2"``.
            - rabotHasContractPrice: per-response flag (may be null).

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {
                "spaceId": int(space_id),
                "day": day,
                "showTax": show_tax,
                "showStrategy": show_strategy,
            }
            response = await self._make_request(
                "POST", API_RABOT_DAY_PRICE, json=payload
            )

            _LOGGER.debug(
                "Rabot day-price response for space %s on %s: %s",
                space_id,
                day,
                response,
            )

            if "content" in response:
                return response["content"]

            return {}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch Rabot day price for space %s on %s: %s",
                space_id,
                day,
                err,
            )
            raise

    async def fetch_strategy_device_status(self, space_id: str | int) -> dict[str, Any]:
        """Fetch local-mode / UPS status for the strategy-capable device.

        Args:
            space_id: The space/family ID

        Returns:
            Dictionary containing:
            - batteryLocalModeEnabled: Whether battery local mode is enabled
            - aioLocalModeEnabled: Whether AIO local mode is enabled
            - aioUpsEnabled: Whether AIO UPS mode is enabled
            - deviceModel: Device model identifier

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"spaceId": int(space_id)}
            response = await self._make_request(
                "POST", API_STRATEGY_DEVICE_STATUS, json=payload
            )

            _LOGGER.debug(
                "Strategy device status response for %s: %s", space_id, response
            )

            if "content" in response:
                return response["content"]

            return {}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch strategy device status for space %s: %s",
                space_id,
                err,
            )
            raise

    async def fetch_space_current_strategy(
        self, family_id: str | int
    ) -> dict[str, Any]:
        """Fetch current battery strategy and device status for a family.

        Args:
            family_id: The family ID to fetch strategy for

        Returns:
            Dictionary containing strategy and status information:
            - strategy: Current strategy name
            - smartStrategyMode: Smart strategy mode
            - batteryFull: Whether battery is full
            - latestModifiedStatus: Latest modification status
            - deviceStatus: Overall device status
            - ratedPower: Rated power in watts
            - maxOutPutPower: Maximum output power
            - batteryStatus: Battery status
            - batteryDeviceStatus: Battery device online/offline status
            - inverterDeviceStatus: Inverter device online/offline status
            - meterDeviceStatus: Meter device online/offline status
            - socMax: Current SOC maximum
            - socMin: Current SOC minimum
            - hwSocMax: Hardware SOC maximum
            - hwSocMin: Hardware SOC minimum
            - deviceTypes: List of available device types
            - failInverterSns: List of failed inverter serial numbers

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"familyId": int(family_id)}
            response = await self._make_request(
                "POST", API_SPACE_CURRENT_STRATEGY, json=payload
            )

            # Extract data from response
            # Log full response for debugging
            _LOGGER.debug(
                "Current strategy response for family %s: %s", family_id, response
            )

            if "content" in response:
                data = response["content"]
                _LOGGER.debug(
                    "Fetched strategy for family %s: %s, battery=%s, status=%s",
                    family_id,
                    data.get("strategy"),
                    data.get("batteryStatus"),
                    data.get("deviceStatus"),
                )
                return data

            return {}

        except SunlitApiError as err:
            _LOGGER.error("Failed to fetch strategy for family %s: %s", family_id, err)
            raise

    async def fetch_space_strategy_history(
        self, family_id: str | int, page: int = 0, size: int = 20
    ) -> dict[str, Any]:
        """Fetch strategy change history for a family.

        Args:
            family_id: The family ID to fetch strategy history for
            page: Page number for pagination (default: 0)
            size: Number of items per page (default: 20)

        Returns:
            Dictionary containing paginated strategy history:
            - content: List of strategy history entries, each containing:
                - modifyDate: Timestamp of strategy change
                - strategy: Strategy type (e.g., "EnergyStorageOnly", "SmartStrategy")
                - smartStrategyMode: Mode for smart strategy
                - status: Success/Failure status
                - batteryStatus: Battery status
                - socMax/socMin: SOC limits at time of change
                - executeTimeStart/executeTimeEnd: Execution time window
                - and other strategy parameters
            - totalElements: Total number of history entries
            - totalPages: Total number of pages

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"familyId": int(family_id)}
            response = await self._make_request(
                "POST", API_SPACE_STRATEGY_HISTORY, json=payload
            )

            # Extract data from response
            # Log full response for debugging
            _LOGGER.debug(
                "Strategy history response for family %s: %s", family_id, response
            )

            if "content" in response:
                data = response["content"]
                content_list = data.get("content", [])
                _LOGGER.debug(
                    "Fetched %d strategy history entries for family %s",
                    len(content_list),
                    family_id,
                )
                return data

            return {"content": [], "totalElements": 0}

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch strategy history for family %s: %s", family_id, err
            )
            raise

    async def fetch_space_index(self, space_id: str | int) -> dict[str, Any]:
        """Fetch comprehensive dashboard data for a space.

        Args:
            space_id: The space/family ID to fetch dashboard data for

        Returns:
            Dictionary containing comprehensive space data:
            - spaceId: Space identifier
            - today: Today's metrics (yield, earning, homePower)
            - eleMeter: Smart meter status and power
            - inverter: Inverter status and power
            - battery: Battery status, SOC, power, heater status
            - chargingBox: Charging box status
            - boostSetting: Boost mode configuration
            - spaceChargePileDTO: EV charger status

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"spaceId": int(space_id)}
            response = await self._make_request("POST", API_SPACE_INDEX, json=payload)

            # Extract data from response
            # Log full response for debugging
            _LOGGER.debug("Space index response for %s: %s", space_id, response)

            if "content" in response:
                data = response["content"]
                _LOGGER.debug(
                    "Fetched space index for space %s: battery=%s%%, power_in=%sW, power_out=%sW",
                    space_id,
                    data.get("battery", {}).get("batteryLevel"),
                    data.get("battery", {}).get("inputPower"),
                    data.get("battery", {}).get("outputPower"),
                )
                return data

            return {}

        except SunlitApiError as err:
            _LOGGER.error("Failed to fetch space index for space %s: %s", space_id, err)
            raise

    async def test_connection(self) -> bool:
        """Test the API connection and authentication.

        Returns:
            True if connection is successful

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
        """
        try:
            await self.fetch_families()
            return True
        except (SunlitAuthError, SunlitConnectionError):
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error testing connection: %s", err)
            return False

    async def get_charging_box_strategy(self, space_id: int) -> dict[str, Any]:
        """Check charging box strategy for a space.

        Args:
            space_id: The space/family ID

        Returns:
            Dictionary containing charging box strategy information:
            - ev3600AutoStrategyExist: Whether EV auto strategy exists
            - ev3600AutoStrategyRunning: Whether EV auto strategy is running
            - ev3600AutoStrategyMode: Auto strategy mode (null if not set)
            - boostOn: Whether boost mode is on
            - storageStrategy: Storage strategy (null if not set)
            - normalChargeBoxMode: Normal charge box mode (null if not set)
            - tariffStrategyExist: Whether tariff strategy exists
            - inverterSn: List of inverter serial numbers
            - enableLocalSmartStrategy: Whether local smart strategy is enabled
            - deyeLocalSnList: List of Deye local serial numbers
            - acCoupleEnabled: Whether AC coupling is enabled

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            payload = {"spaceId": int(space_id)}
            response = await self._make_request(
                "POST", API_CHARGING_BOX_CHECK_STRATEGY, json=payload
            )

            if "content" in response:
                _LOGGER.debug(
                    "Fetched charging box strategy for space %s: %s",
                    space_id,
                    response["content"],
                )
                return response["content"]

            _LOGGER.warning(
                "No charging box strategy data found for space %s", space_id
            )
            return {}

        except (SunlitAuthError, SunlitConnectionError):
            raise
        except Exception as err:
            _LOGGER.error(
                "Failed to fetch charging box strategy for space %s: %s", space_id, err
            )
            raise SunlitApiError(
                f"Failed to fetch charging box strategy: {err}"
            ) from err

    def process_sensor_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process raw API data into sensor-friendly format.

        Args:
            data: Raw data from API

        Returns:
            Processed data with flattened structure
        """
        processed = {}

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float, str, bool)):
                    processed[key] = value
                elif isinstance(value, dict):
                    # Flatten nested dictionaries
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, (int, float, str, bool)):
                            processed[f"{key}_{sub_key}"] = sub_value
        elif isinstance(data, list) and data:
            # Handle arrays by processing first 10 items
            for idx, item in enumerate(data[:10]):
                if isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, (int, float, str, bool)):
                            processed[f"item_{idx}_{key}"] = value

        return processed
