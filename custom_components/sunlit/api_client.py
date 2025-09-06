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
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session (injected for testability)
            api_key: Bearer token for authentication
            timeout: Request timeout in seconds
        """
        self._session = session
        self._api_key = api_key
        self._timeout = timeout
        self._base_url = API_BASE_URL

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
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
            - deviceType: Type of device (e.g., SHELLY_3EM_METER, ENERGY_STORAGE_BATTERY)
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
                        Examples: "ALL", "ENERGY_STORAGE_BATTERY", "SHELLY_3EM_METER", etc.

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

    async def test_connection(self) -> bool:
        """Test the API connection and authentication.

        Returns:
            True if connection is successful

        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
        """
        try:
            families = await self.fetch_families()
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
