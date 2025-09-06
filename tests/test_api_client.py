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
                    "mpptName": "MPPT1",
                },
                "batteryMppt2Data": {
                    "batteryMpptInVol": 0,
                    "batteryMpptInCur": 0,
                    "batteryMpptInPower": 0.0,
                    "mpptName": "MPPT2",
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


@pytest.mark.asyncio
async def test_fetch_battery_io_power_success(api_client, mock_session):
    """Test successful fetching of battery IO power statistics."""
    # Setup response with power data
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "responseTime": 1757166471233,
            "message": {"DE": "Ok"},
            "content": {
                "powerList": [
                    {
                        "key": "14:55",
                        "batteryInputPower": 0.0,
                        "batteryOutputPower": 0.0,
                    },
                    {
                        "key": "15:00",
                        "batteryInputPower": 164.0,
                        "batteryOutputPower": 0.0,
                    },
                    {
                        "key": "15:03",
                        "batteryInputPower": 363.0,
                        "batteryOutputPower": 349.0,
                    },
                    {
                        "key": "15:05",
                        "batteryInputPower": 363.0,
                        "batteryOutputPower": 352.0,
                    },
                ]
            },
        },
    )

    # Test
    power_list = await api_client.fetch_battery_io_power(41714, 2025, 9, 6)

    # Assertions
    assert len(power_list) == 4
    assert power_list[0]["key"] == "14:55"
    assert power_list[0]["batteryInputPower"] == 0.0
    assert power_list[0]["batteryOutputPower"] == 0.0
    assert power_list[2]["key"] == "15:03"
    assert power_list[2]["batteryInputPower"] == 363.0
    assert power_list[2]["batteryOutputPower"] == 349.0

    # Verify request was made correctly (POST with JSON payload)
    mock_session.request.assert_called_once()
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "POST"
    assert "/v1.3/statistics/instantPower/batteryIO" in call_args[0][1]
    assert call_args[1]["json"] == {
        "deviceId": 41714,
        "year": "2025",
        "month": "09",
        "day": "06",
    }


@pytest.mark.asyncio
async def test_fetch_battery_io_power_empty(api_client, mock_session):
    """Test empty power list response."""
    # Setup response with empty power list
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "message": {"DE": "Ok"},
            "content": {"powerList": []},
        },
    )

    # Test
    power_list = await api_client.fetch_battery_io_power(41714, 2025, 1, 1)

    # Assertions
    assert power_list == []


@pytest.mark.asyncio
async def test_fetch_battery_io_power_auth_error(api_client, mock_session):
    """Test authentication error when fetching battery IO power."""
    # Setup 401 response
    setup_mock_response(mock_session, 401)

    # Test
    with pytest.raises(SunlitAuthError) as exc_info:
        await api_client.fetch_battery_io_power(41714, 2025, 9, 6)

    assert "Invalid authentication token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_battery_io_power_today(api_client, mock_session):
    """Test fetching today's battery IO power statistics."""
    from datetime import datetime

    # Setup response
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "message": {"DE": "Ok"},
            "content": {
                "powerList": [
                    {
                        "key": "10:00",
                        "batteryInputPower": 100.0,
                        "batteryOutputPower": 95.0,
                    }
                ]
            },
        },
    )

    # Test
    power_list = await api_client.fetch_battery_io_power_today(41714)

    # Assertions
    assert len(power_list) == 1
    assert power_list[0]["key"] == "10:00"

    # Verify correct date was used
    now = datetime.now()
    call_args = mock_session.request.call_args
    assert call_args[1]["json"]["year"] == str(now.year)
    assert call_args[1]["json"]["month"] == f"{now.month:02d}"
    assert call_args[1]["json"]["day"] == f"{now.day:02d}"


@pytest.mark.asyncio
async def test_fetch_battery_io_power_date_formatting(api_client, mock_session):
    """Test that dates are properly formatted with leading zeros."""
    # Setup response
    setup_mock_response(
        mock_session,
        200,
        {"code": 0, "content": {"powerList": []}},
    )

    # Test with single digit month and day
    await api_client.fetch_battery_io_power(41714, 2025, 3, 5)

    # Verify date formatting in request
    call_args = mock_session.request.call_args
    assert call_args[1]["json"]["month"] == "03"
    assert call_args[1]["json"]["day"] == "05"
    assert call_args[1]["json"]["year"] == "2025"


@pytest.mark.asyncio
async def test_fetch_device_details_success(api_client, mock_session):
    """Test successful fetching of device details for a Shelly meter."""
    # Setup response with Shelly meter details
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "responseTime": 1757166462946,
            "message": {"DE": "Ok"},
            "content": {
                "deviceId": 55478,
                "deviceSn": "XXXXXXXXXXXX",
                "createDate": 1742636857000,
                "firmwareVersion": None,
                "familyItem": {"id": 34038, "name": "Garage"},
                "status": "Offline",
                "manufacturer": "Shelly3EM",
                "deviceType": "SHELLY_3EM_METER",
                "ssid": "WLAN-XXXXX",
                "stationName": None,
                "collectorSn": None,
                "maxOutputPower": None,
                "maxAllowedPower": None,
                "ratedPower": None,
                "xmChannel": True,
                "subStatus": None,
                "collectorFirmwareVersion": None,
                "hwVersion": None,
                "batteryChargingBoxDto": None,
                "batteryBoxStatus": "NotExist",
                "supportReboot": None,
                "systemMultiStatus": None,
            },
        },
    )

    # Test
    details = await api_client.fetch_device_details(55478)

    # Assertions
    assert details["deviceId"] == 55478
    assert details["deviceSn"] == "XXXXXXXXXXXX"
    assert details["deviceType"] == "SHELLY_3EM_METER"
    assert details["status"] == "Offline"
    assert details["manufacturer"] == "Shelly3EM"
    assert details["familyItem"]["id"] == 34038
    assert details["familyItem"]["name"] == "Garage"
    assert details["batteryBoxStatus"] == "NotExist"

    # Verify request was made correctly (GET with no JSON payload)
    mock_session.request.assert_called_once()
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "GET"
    assert "/device/55478" in call_args[0][1]
    assert "json" not in call_args[1]  # No JSON payload for GET request


@pytest.mark.asyncio
async def test_fetch_device_details_battery(api_client, mock_session):
    """Test fetching device details for a battery device."""
    # Setup response with battery device details
    setup_mock_response(
        mock_session,
        200,
        {
            "code": 0,
            "message": {"DE": "Ok"},
            "content": {
                "deviceId": 41714,
                "deviceSn": "XXXXXXXXXXXX",
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "status": "Online",
                "familyItem": {"id": 34038, "name": "Garage"},
                "manufacturer": "SunlitBattery",
                "firmwareVersion": "1.2.3",
                "maxOutputPower": 5000,
                "ratedPower": 5000,
                "batteryBoxStatus": "Normal",
            },
        },
    )

    # Test
    details = await api_client.fetch_device_details(41714)

    # Assertions
    assert details["deviceId"] == 41714
    assert details["deviceType"] == "ENERGY_STORAGE_BATTERY"
    assert details["status"] == "Online"
    assert details["firmwareVersion"] == "1.2.3"
    assert details["maxOutputPower"] == 5000
    assert details["batteryBoxStatus"] == "Normal"


@pytest.mark.asyncio
async def test_fetch_device_details_not_found(api_client, mock_session):
    """Test device not found error."""
    # Setup response with error code
    setup_mock_response(
        mock_session,
        200,
        {"code": 1, "message": "Device not found"},
    )

    # Test
    with pytest.raises(SunlitApiError) as exc_info:
        await api_client.fetch_device_details(99999)

    assert "API error: Device not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_details_auth_error(api_client, mock_session):
    """Test authentication error when fetching device details."""
    # Setup 401 response
    setup_mock_response(mock_session, 401)

    # Test
    with pytest.raises(SunlitAuthError) as exc_info:
        await api_client.fetch_device_details(55478)

    assert "Invalid authentication token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_details_connection_error(api_client, mock_session):
    """Test connection error when fetching device details."""
    # Setup 500 response
    setup_mock_response(mock_session, 500, text_data="Internal Server Error")

    # Test
    with pytest.raises(SunlitConnectionError) as exc_info:
        await api_client.fetch_device_details(55478)

    assert "API request failed with status 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_list_success(api_client, mock_session):
    """Test successful device list fetch with multiple device types."""
    # Setup successful response with various device types
    response_data = {
        "code": 0,
        "responseTime": 1757166459864,
        "message": {"DE": "Ok"},
        "content": {
            "content": [
                {
                    "deviceId": 55478,
                    "deviceSn": "XXXXXXXXXXF4",  # Anonymized
                    "deviceType": "SHELLY_3EM_METER",
                    "status": "Offline",
                    "fault": False,
                    "off": True,
                    "totalAcPower": 3050.78,
                    "dailyBuyEnergy": 7.21,
                    "dailyRetEnergy": 0.12,
                    "totalBuyEnergy": 3744.46,
                    "totalRetEnergy": 53.38,
                    "batteryLevel": None,
                },
                {
                    "deviceId": 55438,
                    "deviceSn": "EXXXXXXXXX549",  # Anonymized
                    "deviceType": "YUNENG_MICRO_INVERTER",
                    "status": "Offline",
                    "fault": False,
                    "off": True,
                    "today": {
                        "currentPower": 645,
                        "totalPowerGeneration": 1.33186,
                        "totalEarnings": {"earnings": 0.41, "currency": "EUR"},
                    },
                    "batteryLevel": None,
                },
                {
                    "deviceId": 41714,
                    "deviceSn": "dcbdccbffe3d",
                    "deviceType": "ENERGY_STORAGE_BATTERY",
                    "status": "Online",
                    "fault": False,
                    "off": False,
                    "batteryLevel": 10.0,
                    "inputPowerTotal": 96.0,
                    "outputPowerTotal": 92.0,
                    "heaterStatusList": [False, False, False],
                },
            ],
            "pageable": {"pageNumber": 0, "pageSize": 20},
            "totalElements": 3,
            "totalPages": 1,
            "numberOfElements": 3,
            "first": True,
            "last": True,
            "empty": False,
        },
    }
    setup_mock_response(mock_session, 200, response_data)

    # Test fetching all devices
    devices = await api_client.fetch_device_list(34038)

    assert len(devices) == 3
    assert devices[0]["deviceType"] == "SHELLY_3EM_METER"
    assert devices[1]["deviceType"] == "YUNENG_MICRO_INVERTER"
    assert devices[2]["deviceType"] == "ENERGY_STORAGE_BATTERY"
    assert devices[2]["batteryLevel"] == 10.0


@pytest.mark.asyncio
async def test_fetch_device_list_with_type_filter(api_client, mock_session):
    """Test device list fetch with device type filter."""
    # Setup response with only battery devices
    response_data = {
        "code": 0,
        "content": {
            "content": [
                {
                    "deviceId": 41714,
                    "deviceSn": "dcbdccbffe3d",
                    "deviceType": "ENERGY_STORAGE_BATTERY",
                    "status": "Online",
                    "batteryLevel": 10.0,
                }
            ],
            "totalElements": 1,
        },
    }
    setup_mock_response(mock_session, 200, response_data)

    # Test fetching only battery devices
    devices = await api_client.fetch_device_list(34038, "ENERGY_STORAGE_BATTERY")

    assert len(devices) == 1
    assert devices[0]["deviceType"] == "ENERGY_STORAGE_BATTERY"


@pytest.mark.asyncio
async def test_fetch_device_list_empty(api_client, mock_session):
    """Test device list fetch with no devices."""
    # Setup empty response
    response_data = {
        "code": 0,
        "content": {"content": [], "totalElements": 0, "empty": True},
    }
    setup_mock_response(mock_session, 200, response_data)

    devices = await api_client.fetch_device_list(40488)

    assert devices == []


@pytest.mark.asyncio
async def test_fetch_device_list_auth_error(api_client, mock_session):
    """Test device list fetch handles authentication errors."""
    # Setup 401 response
    setup_mock_response(mock_session, 401)

    with pytest.raises(SunlitAuthError) as exc_info:
        await api_client.fetch_device_list(34038)

    assert "Invalid authentication token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_device_list_connection_error(api_client, mock_session):
    """Test device list fetch handles connection errors."""
    # Setup 500 response
    setup_mock_response(mock_session, 500, text_data="Internal Server Error")

    with pytest.raises(SunlitConnectionError) as exc_info:
        await api_client.fetch_device_list(34038)

    assert "API request failed with status 500" in str(exc_info.value)
