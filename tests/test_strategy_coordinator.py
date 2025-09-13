"""Test the Sunlit strategy history coordinator."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sunlit.coordinators.strategy import (
    SunlitStrategyHistoryCoordinator,
)


async def test_strategy_coordinator_update_success(
    hass: HomeAssistant,
    enable_custom_integrations,
    strategy_history_response,
):
    """Test successful strategy history update."""
    api_client = AsyncMock()
    api_client.fetch_space_strategy_history.return_value = strategy_history_response[
        "content"
    ]

    coordinator = SunlitStrategyHistoryCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data is not None
    assert "strategy" in data
    strategy_data = data["strategy"]

    # Check latest strategy data
    assert strategy_data["last_strategy_type"] == "SELF_CONSUMPTION"
    assert strategy_data["last_strategy_status"] == "ACTIVE"
    # The timestamp is dynamically generated (2 hours ago), so just check it exists
    assert "last_strategy_change" in strategy_data
    assert isinstance(strategy_data["last_strategy_change"], int)

    # Check changes today (should be 2 based on mock data)
    assert strategy_data["strategy_changes_today"] == 2

    # Check history is stored
    assert "strategy_history" in strategy_data
    assert len(strategy_data["strategy_history"]) == 2

    # Verify API call
    api_client.fetch_space_strategy_history.assert_called_once_with("34038")


async def test_strategy_coordinator_no_history(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test strategy coordinator with no history."""
    api_client = AsyncMock()
    api_client.fetch_space_strategy_history.return_value = {"content": []}

    coordinator = SunlitStrategyHistoryCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    assert data is not None
    assert "strategy" in data
    strategy_data = data["strategy"]

    # Should have empty data when no history
    assert "last_strategy_type" not in strategy_data
    assert "last_strategy_change" not in strategy_data
    assert "strategy_changes_today" not in strategy_data


async def test_strategy_coordinator_api_failure(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test strategy coordinator handles API failures gracefully."""
    api_client = AsyncMock()
    api_client.fetch_space_strategy_history.side_effect = Exception("API failed")

    coordinator = SunlitStrategyHistoryCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    # Should not raise, but return empty data
    data = await coordinator._async_update_data()

    assert data == {"strategy": {}}


async def test_strategy_coordinator_changes_today_calculation(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test strategy coordinator correctly calculates changes today."""
    api_client = AsyncMock()

    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    two_days_ago = now - timedelta(days=2)

    api_client.fetch_space_strategy_history.return_value = {
        "content": [
            {
                "modifyDate": int(one_hour_ago.timestamp() * 1000),
                "strategy": "SELF_CONSUMPTION",
                "status": "ACTIVE",
            },
            {
                "modifyDate": int(two_days_ago.timestamp() * 1000),
                "strategy": "TIME_OF_USE",
                "status": "ACTIVE",
            },
        ]
    }

    coordinator = SunlitStrategyHistoryCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    data = await coordinator._async_update_data()

    strategy_data = data["strategy"]

    # Should only count the change from 1 hour ago as "today"
    assert strategy_data["strategy_changes_today"] == 1


async def test_strategy_coordinator_update_interval(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test strategy coordinator has correct update interval."""
    api_client = AsyncMock()
    api_client.fetch_space_strategy_history.return_value = {"content": []}

    coordinator = SunlitStrategyHistoryCoordinator(
        hass,
        api_client,
        "34038",
        "Test Family",
    )

    # Should have 5 minute update interval
    assert coordinator.update_interval == timedelta(minutes=5)
