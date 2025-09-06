"""Sunlit API Client for handling all API interactions."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout

from .const import (
    API_BASE_URL,
    API_FAMILY_LIST,
    API_FAMILY_DATA,
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
            raise SunlitConnectionError(f"Request timeout after {self._timeout}s") from err

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

    async def fetch_family_data(self, family_id: str | int) -> dict[str, Any]:
        """Fetch data for a specific family.
        
        Args:
            family_id: The family ID to fetch data for
            
        Returns:
            Dictionary containing family data
            
        Raises:
            SunlitAuthError: Authentication failed
            SunlitConnectionError: Connection failed
            SunlitApiError: API returned an error
        """
        endpoint = API_FAMILY_DATA.replace("{family_id}", str(family_id))
        
        try:
            response = await self._make_request("GET", endpoint)
            
            # Extract data from response
            if "content" in response:
                data = response["content"]
                _LOGGER.debug("Fetched data for family %s", family_id)
                return data
            
            # If no content wrapper, return raw response
            return response
            
        except SunlitApiError as err:
            _LOGGER.error("Failed to fetch data for family %s: %s", family_id, err)
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