"""Tests for the Sunlit API client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.sunlit.api_client import (
    SunlitApiClient,
    SunlitApiError,
    SunlitAuthError,
    SunlitConnectionError,
)


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = MagicMock(spec=aiohttp.ClientSession)
    # Set up request as a regular MagicMock (not AsyncMock)
    session.request = MagicMock()
    return session


@pytest.fixture
def api_client(mock_session):
    """Create a SunlitApiClient instance with mock session."""
    return SunlitApiClient(mock_session, "test_token")


def setup_mock_response(mock_session, status, json_data=None, text_data=None):
    """Helper to set up mock response correctly."""
    mock_response = AsyncMock()
    mock_response.status = status
    if json_data is not None:
        mock_response.json = AsyncMock(return_value=json_data)
    if text_data is not None:
        mock_response.text = AsyncMock(return_value=text_data)

    # Create context manager
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    # Return context manager from request
    mock_session.request.return_value = mock_context
    return mock_response


@pytest.mark.asyncio
async def test_fetch_families_success(api_client, mock_session):
    """Test successful fetching of families."""
    # Setup mock response
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "message": {"DE": "Ok"},
            "content": [
                {
                    "id": 34038,
                    "name": "Garage",
                    "address": "Halver",
                    "deviceCount": 4,
                    "countryCode": "DE",
                },
                {
                    "id": 40488,
                    "name": "Test",
                    "address": "Halver",
                    "deviceCount": 0,
                    "countryCode": "DE",
                },
            ],
        },
    )

    # Test
    families = await api_client.fetch_families()

    # Assertions
    assert len(families) == 2
    assert families[0]["name"] == "Garage"
    assert families[0]["id"] == 34038
    assert families[1]["name"] == "Test"

    # Verify request was made correctly
    mock_session.request.assert_called_once()
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "GET"
    assert "/family/list" in call_args[0][1]
    assert call_args[1]["headers"]["Authorization"] == "Bearer test_token"


@pytest.mark.asyncio
async def test_fetch_families_auth_error(api_client, mock_session):
    """Test authentication error when fetching families."""
    # Setup 401 response
    setup_mock_response(mock_session, 401)

    # Test
    with pytest.raises(SunlitAuthError) as exc_info:
        await api_client.fetch_families()

    assert "Invalid authentication token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_families_connection_error(api_client, mock_session):
    """Test connection error when fetching families."""
    # Setup 500 response
    setup_mock_response(mock_session, 500, text_data="Internal Server Error")

    # Test
    with pytest.raises(SunlitConnectionError) as exc_info:
        await api_client.fetch_families()

    assert "API request failed with status 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_families_api_error(api_client, mock_session):
    """Test API error response."""
    # Setup response with error code
    setup_mock_response(
        mock_session, 200, {"code": 1, "message": "Something went wrong"}
    )

    # Test
    with pytest.raises(SunlitApiError) as exc_info:
        await api_client.fetch_families()

    assert "API error: Something went wrong" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_family_data_success(api_client, mock_session):
    """Test successful fetching of family data."""
    # Setup response
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "content": {
                "power": 1500,
                "energy": 12.5,
                "temperature": 22.3,
                "status": "online",
            },
        },
    )

    # Test
    data = await api_client.fetch_family_data(34038)

    # Assertions
    assert data["power"] == 1500
    assert data["energy"] == 12.5
    assert data["temperature"] == 22.3

    # Verify request was made correctly
    call_args = mock_session.request.call_args
    assert "/family/34038/data" in call_args[0][1]


@pytest.mark.asyncio
async def test_test_connection_success(api_client, mock_session):
    """Test successful connection test."""
    # Setup successful families response
    setup_mock_response(mock_session, 200, {"code": 0, "content": []})

    # Test
    result = await api_client.test_connection()
    assert result is True


def test_process_sensor_data_dict():
    """Test processing dictionary data."""
    client = SunlitApiClient(None, "test")

    data = {
        "temperature": 22.5,
        "humidity": 65,
        "location": {"city": "Berlin", "lat": 52.52, "lon": 13.405},
        "nested": {"deeply": {"nested": "value"}},
    }

    processed = client.process_sensor_data(data)

    assert processed["temperature"] == 22.5
    assert processed["humidity"] == 65
    assert processed["location_city"] == "Berlin"
    assert processed["location_lat"] == 52.52
    assert "nested_deeply" not in processed  # Only one level of nesting


def test_process_sensor_data_list():
    """Test processing list data."""
    client = SunlitApiClient(None, "test")

    data = [
        {"id": 1, "name": "Device 1", "power": 100},
        {"id": 2, "name": "Device 2", "power": 200},
    ]

    processed = client.process_sensor_data(data)

    assert processed["item_0_id"] == 1
    assert processed["item_0_name"] == "Device 1"
    assert processed["item_0_power"] == 100
    assert processed["item_1_id"] == 2
    assert processed["item_1_name"] == "Device 2"


def test_process_sensor_data_mixed():
    """Test processing mixed data types."""
    client = SunlitApiClient(None, "test")

    data = {
        "string": "value",
        "integer": 42,
        "float": 3.14,
        "boolean": True,
        "null": None,
        "array": [1, 2, 3],
        "object": {"key": "value"},
    }

    processed = client.process_sensor_data(data)

    assert processed["string"] == "value"
    assert processed["integer"] == 42
    assert processed["float"] == 3.14
    assert processed["boolean"] is True
    assert "null" not in processed
    assert "array" not in processed
    assert processed["object_key"] == "value"


@pytest.mark.asyncio
async def test_timeout_error(api_client, mock_session):
    """Test timeout error handling."""
    # Mock timeout
    mock_session.request.side_effect = TimeoutError()

    # Test
    with pytest.raises(SunlitConnectionError) as exc_info:
        await api_client.fetch_families()

    assert "Request timeout" in str(exc_info.value)


@pytest.mark.asyncio
async def test_client_error(api_client, mock_session):
    """Test aiohttp client error handling."""
    # Mock client error
    mock_session.request.side_effect = aiohttp.ClientError("Connection refused")

    # Test
    with pytest.raises(SunlitConnectionError) as exc_info:
        await api_client.fetch_families()

    assert "Connection error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_statistics_success(api_client, mock_session):
    """Test successful fetching of device statistics."""
    # Setup response with full device statistics
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "responseTime": 1757166469831,
            "message": {"DE": "Ok"},
            "content": {
                "deviceId": 41714,
                "sn": "xxxxxxxxxxxx",
                "status": "Online",
                "subStatus": None,
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "batterySoc": 10.0,
                "battery1Soc": 11.0,
                "battery2Soc": 11.0,
                "battery3Soc": None,
                "fault": False,
                "batteryLevel": 10.0,
                "batteryMppt1Data": {
                    "batteryMpptInVol": 29.0,
                    "batteryMpptInCur": 12.3,
                    "batteryMpptInPower": 356.7,
                    "mpptName": "MPPT1"
                },
                "batteryMppt2Data": {
                    "batteryMpptInVol": 0,
                    "batteryMpptInCur": 0,
                    "batteryMpptInPower": 0.0,
                    "mpptName": "MPPT2"
                },
                "mpptCollectTime": 1757166462661,
            },
        },
    )

    # Test
    data = await api_client.fetch_device_statistics(41714)

    # Assertions
    assert data["deviceId"] == 41714
    assert data["sn"] == "xxxxxxxxxxxx"
    assert data["status"] == "Online"
    assert data["deviceType"] == "ENERGY_STORAGE_BATTERY"
    assert data["batterySoc"] == 10.0
    assert data["fault"] is False
    assert data["batteryMppt1Data"]["batteryMpptInPower"] == 356.7

    # Verify request was made correctly (POST with JSON payload)
    mock_session.request.assert_called_once()
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "POST"
    assert "/v1.1/statistics/static/device" in call_args[0][1]
    assert call_args[1]["json"] == {"deviceId": 41714}
    assert call_args[1]["headers"]["Authorization"] == "Bearer test_token"


@pytest.mark.asyncio
async def test_fetch_device_statistics_auth_error(api_client, mock_session):
    """Test authentication error when fetching device statistics."""
    # Setup 401 response
    setup_mock_response(mock_session, 401)

    # Test
    with pytest.raises(SunlitAuthError) as exc_info:
        await api_client.fetch_device_statistics(41714)

    assert "Invalid authentication token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_statistics_not_found(api_client, mock_session):
    """Test device not found error."""
    # Setup response with error code indicating device not found
    setup_mock_response(
        mock_session,
        200,
        {"code": 1, "message": "Device not found"},
    )

    # Test
    with pytest.raises(SunlitApiError) as exc_info:
        await api_client.fetch_device_statistics(99999)

    assert "API error: Device not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_statistics_connection_error(api_client, mock_session):
    """Test connection error when fetching device statistics."""
    # Setup 500 response
    setup_mock_response(mock_session, 500, text_data="Internal Server Error")

    # Test
    with pytest.raises(SunlitConnectionError) as exc_info:
        await api_client.fetch_device_statistics(41714)

    assert "API request failed with status 500" in str(exc_info.value)
