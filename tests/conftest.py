"""Pytest configuration and fixtures for tests."""
import sys
from pathlib import Path

# Add custom_components to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock
import aiohttp


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp session for testing."""
    session = MagicMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def mock_response_context():
    """Create a mock response context manager."""
    mock_response = AsyncMock()
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    return mock_response


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
                    "currency": "EUR"
                },
                "rabotOnboarding": None,
                "rabotCustomerId": None
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
                    "currency": "EUR"
                },
                "rabotOnboarding": None,
                "rabotCustomerId": None
            }
        ]
    }


@pytest.fixture
def family_data_response():
    """Sample family data API response."""
    return {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": {
            "power": 1500,
            "energy_today": 12.5,
            "energy_total": 1250.8,
            "temperature": 22.3,
            "humidity": 65,
            "status": "online",
            "devices": {
                "inverter": {
                    "power": 1500,
                    "voltage": 230,
                    "current": 6.5
                },
                "battery": {
                    "soc": 85,
                    "voltage": 52.1,
                    "current": 10.2
                }
            }
        }
    }


@pytest.fixture
def api_error_response():
    """Sample API error response."""
    return {
        "code": 1,
        "message": "Authentication failed",
        "content": None
    }