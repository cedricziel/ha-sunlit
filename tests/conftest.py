"""Pytest configuration and fixtures for tests."""

import sys
from pathlib import Path

import pytest
from aioresponses import aioresponses
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Add custom_components to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_aioresponse():
    """Create an aioresponses instance for mocking HTTP calls."""
    with aioresponses() as m:
        yield m


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MockConfigEntry(
        domain="sunlit",
        data={
            "access_token": "test_token_123",
            "families": [
                {"family_id": "34038", "family_name": "Garage"},
                {"family_id": "40488", "family_name": "Test"},
            ],
        },
        unique_id="sunlit",
        entry_id="test_entry_id",
    )


@pytest.fixture
def api_base_url():
    """Return the API base URL for mocking."""
    return "https://api.sunlitsolar.de/rest"


# API Response Fixtures
@pytest.fixture
def families_response():
    """Sample families API response."""
    return {
        "code": 0,
        "responseTime": 1757165913195,
        "message": {"DE": "Ok"},
        "content": [
            {
                "id": 34038,
                "name": "Garage",
                "address": "Halver",
                "deviceCount": 4,
                "countryCode": "DE",
                "price": {
                    "electricPrice": 0.3000,
                    "startTimestamp": 1743292800000,
                    "currency": "EUR",
                },
                "rabotOnboarding": None,
                "rabotCustomerId": None,
            },
            {
                "id": 40488,
                "name": "Test",
                "address": "Halver",
                "deviceCount": 0,
                "countryCode": "DE",
                "price": {
                    "electricPrice": 0.2800,
                    "startTimestamp": 1741651200000,
                    "currency": "EUR",
                },
                "rabotOnboarding": None,
                "rabotCustomerId": None,
            },
        ],
    }


@pytest.fixture
def device_list_response():
    """Sample device list API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": [
            {
                "deviceId": "meter_001",
                "deviceName": "Smart Meter",
                "deviceType": "SHELLY_3EM_METER",
                "spaceId": 34038,
                "deviceStatus": 1,  # Online
                "fault": False,
                "off": False,
            },
            {
                "deviceId": "inverter_001",
                "deviceName": "Solar Inverter",
                "deviceType": "YUNENG_MICRO_INVERTER",
                "spaceId": 34038,
                "deviceStatus": 1,  # Online
                "fault": False,
                "off": False,
            },
            {
                "deviceId": "battery_001",
                "deviceName": "Energy Storage",
                "deviceType": "ENERGY_STORAGE_BATTERY",
                "spaceId": 34038,
                "deviceStatus": 1,  # Online
                "fault": False,
                "off": False,
            },
        ],
    }


@pytest.fixture
def space_index_response():
    """Sample space index API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "deviceList": [
                {
                    "deviceId": "meter_001",
                    "deviceName": "Smart Meter",
                    "deviceType": "SHELLY_3EM_METER",
                    "status": "Online",
                    "total_ac_power": 1500,
                    "daily_buy_energy": 5.2,
                    "daily_ret_energy": 8.7,
                    "total_buy_energy": 1234.5,
                    "total_ret_energy": 2345.6,
                },
                {
                    "deviceId": "inverter_001",
                    "deviceName": "Solar Inverter",
                    "deviceType": "YUNENG_MICRO_INVERTER",
                    "status": "Online",
                    "current_power": 2500,
                    "total_power_generation": 15678.9,
                    "daily_earnings": 12.50,
                },
                {
                    "deviceId": "battery_001",
                    "deviceName": "Energy Storage",
                    "deviceType": "ENERGY_STORAGE_BATTERY",
                    "status": "Online",
                    "battery_level": 85,
                    "batterySoc": 85,
                    "input_power_total": 500,
                    "output_power_total": 0,
                },
            ],
            "dailyYield": 25.3,
            "dailyEarnings": 12.50,
            "homePower": 1200,
            "currency": "EUR",
            "boostModeEnabled": False,
            "boostModeSwitching": False,
            "batteryBypass": False,
            "batteryHeater1": False,
            "batteryHeater2": False,
            "batteryHeater3": False,
        },
    }


@pytest.fixture
def space_soc_response():
    """Sample space SOC API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "hwSocMin": 10,
            "hwSocMax": 95,
            "batterySocMin": 15,
            "batterySocMax": 90,
            "strategySocMin": 20,
            "strategySocMax": 85,
            "currentSocMin": 20,
            "currentSocMax": 85,
        },
    }


@pytest.fixture
def current_strategy_response():
    """Sample current strategy API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "strategy": "SELF_CONSUMPTION",
            "ratedPower": 5000,
            "maxOutputPower": 4500,
            "batteryStatus": "CHARGING",
            "batteryDeviceStatus": "ONLINE",
            "inverterDeviceStatus": "ONLINE",
            "meterDeviceStatus": "ONLINE",
        },
    }


@pytest.fixture
def strategy_history_response():
    """Sample strategy history API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": [
            {
                "timestamp": 1757165913195,
                "strategyType": "SELF_CONSUMPTION",
                "status": "ACTIVE",
            },
            {
                "timestamp": 1757165813195,
                "strategyType": "GRID_FEED",
                "status": "COMPLETED",
            },
        ],
    }


@pytest.fixture
def device_statistics_response():
    """Sample device statistics API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "batterySoc": 85,
            "chargeRemaining": 120,
            "dischargeRemaining": 480,
            "batteryMppt1InVol": 400.5,
            "batteryMppt1InCur": 8.2,
            "batteryMppt1InPower": 3284.1,
            "batteryMppt2InVol": 395.3,
            "batteryMppt2InCur": 7.8,
            "batteryMppt2InPower": 3083.34,
            "battery1Soc": 84,
            "battery1Mppt1InVol": 398.2,
            "battery1Mppt1InCur": 5.5,
            "battery1Mppt1InPower": 2190.1,
            "battery2Soc": 86,
            "battery2Mppt1InVol": 402.1,
            "battery2Mppt1InCur": 5.8,
            "battery2Mppt1InPower": 2332.18,
        },
    }


@pytest.fixture
def battery_io_power_response():
    """Sample battery IO power API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "inputPowerTotal": 500,
            "outputPowerTotal": 0,
            "batteryCount": 3,
            "chargingRemaining": 120,
            "dischargingRemaining": 480,
            "inverterCurrentPower": 2500,
        },
    }


@pytest.fixture
def charging_box_strategy_response():
    """Sample charging box strategy API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "ev3600AutoStrategyMode": "AUTO",
            "storageStrategy": "OPTIMIZE",
            "normalChargeBoxMode": "NORMAL",
            "inverterSn": ["INV001", "INV002"],
            "ev3600AutoStrategyExist": True,
            "ev3600AutoStrategyRunning": False,
            "tariffStrategyExist": True,
            "enableLocalSmartStrategy": True,
            "acCoupleEnabled": False,
            "boostOn": False,
        },
    }


@pytest.fixture
def api_error_response():
    """Sample API error response."""
    return {"code": 1, "message": {"DE": "Authentication failed"}, "content": None}




@pytest.fixture
async def hass_with_config_entry(hass, mock_config_entry):
    """HomeAssistant instance with config entry added."""
    mock_config_entry.add_to_hass(hass)
    return hass
