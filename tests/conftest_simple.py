"""Simple pytest configuration without HomeAssistant framework."""

import sys
from pathlib import Path

# Add custom_components to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture
def api_base_url():
    """Return the API base URL for mocking."""
    return "https://api.sunlitsolar.de/rest"
