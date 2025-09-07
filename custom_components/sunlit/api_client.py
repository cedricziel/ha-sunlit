"""Sunlit API Client for handling all API interactions."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout

from .const import (
    API_BASE_URL,
    API_FAMILY_LIST,
    API_DEVICE_DETAILS,
    API_DEVICE_STATISTICS,
    API_BATTERY_IO_POWER,
    API_DEVICE_LIST,
    API_SPACE_SOC,
    API_SPACE_CURRENT_STRATEGY,
    API_SPACE_STRATEGY_HISTORY,
)

_LOGGER = logging.getLogger(__name__)


class SunlitApiError(Exception):
    """Base exception for Sunlit API errors."""


class SunlitAuthError(SunlitApiError):
    """Exception for authentication errors."""


class SunlitConnectionError(SunlitApiError):
    """Exception for connection errors."""


class SunlitApiClient:
    """Client for interacting with the Sunlit Solar API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        timeout: int = 10,
        ha_version: str | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session (injected for testability)
            api_key: Bearer token for authentication
            timeout: Request timeout in seconds
            ha_version: HomeAssistant version for User-Agent
        """
        self._session = session
        self._api_key = api_key
        self._timeout = timeout
        self._base_url = API_BASE_URL
        self._ha_version = ha_version or "unknown"

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        from .const import INTEGRATION_NAME, VERSION, GITHUB_URL
        
        # Build User-Agent string
        user_agent = f"{INTEGRATION_NAME}/{VERSION} (+{GITHUB_URL})"
        if self._ha_version != "unknown":
            user_agent += f" HomeAssistant/{self._ha_version}"
        
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        }

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
            async with async_timeout.timeout(self._timeout):
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
                        message = data.get("message", "Unknown error")
                        raise SunlitApiError(f"API error: {message}")

                    return data

        except aiohttp.ClientError as err:
            raise SunlitConnectionError(f"Connection error: {err}") from err
        except TimeoutError as err:
            raise SunlitConnectionError(
                f"Request timeout after {self._timeout}s"
            ) from err

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
        """Fetch statistics for a specific device.

        Args:
            device_id: The device ID to fetch statistics for

        Returns:
            Dictionary containing device statistics including:
            - batterySoc: Battery state of charge
            - status: Device online/offline status
            - deviceType: Type of device (e.g., ENERGY_STORAGE_BATTERY)
            - batteryMpptData: MPPT charge controller data
            - fault: Fault status

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        try:
            # This endpoint uses POST with JSON payload
            payload = {"deviceId": int(device_id)}
            response = await self._make_request(
                "POST", API_DEVICE_STATISTICS, json=payload
            )

            # Extract data from response
            if "content" in response:
                data = response["content"]
                _LOGGER.debug("Fetched statistics for device %s", device_id)
                return data

            # If no content wrapper, return raw response
            return response

        except SunlitApiError as err:
            _LOGGER.error(
                "Failed to fetch statistics for device %s: %s", device_id, err
            )
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
            _LOGGER.error("Failed to fetch statistics for device %s: %s", device_id, err)
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

            # Extract device list from nested response structure
            if "content" in response and isinstance(response["content"], dict):
                content = response["content"]
                if "content" in content and isinstance(content["content"], list):
                    devices = content["content"]
                    _LOGGER.debug(
                        "Fetched %d devices for family %s (type: %s)",
                        len(devices),
                        family_id,
                        device_type,
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
            _LOGGER.error(
                "Failed to fetch strategy for family %s: %s", family_id, err
            )
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
