"""Simple API client tests without HomeAssistant framework."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.sunlit.api_client import SunlitApiClient


@pytest.mark.asyncio
async def test_get_families():
    """Test fetching families list."""
    with aioresponses() as m:
        # Mock the API response
        m.get(
            "https://api.sunlitsolar.de/rest/family/list",
            payload={
                "code": 0,
                "content": [
                    {"id": 1, "name": "Family 1"},
                    {"id": 2, "name": "Family 2"},
                ],
            },
        )

        # Create client with real aiohttp session
        async with aiohttp.ClientSession() as session:
            client = SunlitApiClient(session, "test_token")

            # Make the call
            families = await client.fetch_families()

            assert len(families) == 2
            assert families[0]["name"] == "Family 1"


@pytest.mark.asyncio
async def test_fetch_space_index():
    """Test fetching space index data."""
    with aioresponses() as m:
        # Mock the API response
        m.post(
            "https://api.sunlitsolar.de/rest/v1.5/space/index",
            payload={
                "code": 0,
                "content": {
                    "deviceList": [
                        {"deviceId": "dev1", "deviceType": "SHELLY_3EM_METER"}
                    ],
                    "dailyYield": 25.5,
                },
            },
        )

        async with aiohttp.ClientSession() as session:
            client = SunlitApiClient(session, "test_token")

            # Make the call
            result = await client.fetch_space_index(123)

            assert result["dailyYield"] == 25.5
            assert len(result["deviceList"]) == 1


@pytest.mark.asyncio
async def test_error_handling():
    """Test API error handling."""
    with aioresponses() as m:
        # Mock an error response
        m.get(
            "https://api.sunlitsolar.de/rest/family/list",
            payload={"code": 1, "message": {"DE": "Error"}, "content": None},
        )

        async with aiohttp.ClientSession() as session:
            client = SunlitApiClient(session, "test_token")

            # Should raise an exception
            with pytest.raises(Exception):
                await client.fetch_families()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
