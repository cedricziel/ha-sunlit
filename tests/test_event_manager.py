"""Tests for the SOC event manager."""

from datetime import timedelta
from unittest.mock import Mock

import pytest

from custom_components.sunlit.event_manager import (
    EVENT_SOC_CHANGE,
    EVENT_SOC_LIMIT,
    EVENT_SOC_THRESHOLD,
    DEFAULT_THRESHOLDS,
    SunlitEventManager,
)


def create_hass_mock():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.bus = Mock()
    hass.bus.async_fire = Mock()
    return hass


def create_event_manager():
    """Create an event manager instance."""
    return SunlitEventManager(create_hass_mock(), "test_family")


class TestSunlitEventManager:
    """Test the Sunlit event manager."""

    def test_initialization(self):
        """Test event manager initialization."""
        event_manager = create_event_manager()
        assert event_manager.family_id == "test_family"
        assert event_manager.thresholds == DEFAULT_THRESHOLDS
        assert event_manager.change_threshold == 5
        assert event_manager._soc_states == {}

    def test_first_soc_update_no_events(self):
        """Test that first SOC update doesn't trigger events."""
        event_manager = create_event_manager()
        event_manager.update_soc_state("battery_1", 50.0)

        # Should not fire any events on first update
        event_manager.hass.bus.async_fire.assert_not_called()

        # Should store the state
        assert "battery_1" in event_manager._soc_states
        assert event_manager._soc_states["battery_1"].value == 50.0

    def test_threshold_crossing_events(self):
        """Test SOC threshold crossing events."""
        event_manager = create_event_manager()
        # Initialize with value above low threshold
        event_manager.update_soc_state("battery_1", 25.0)
        event_manager.hass.bus.async_fire.reset_mock()

        # Cross low threshold downward (also causes 7% change event)
        event_manager.update_soc_state("battery_1", 18.0)

        # Should fire both threshold and change events
        assert event_manager.hass.bus.async_fire.call_count == 2

        # Find the threshold event among the calls
        calls = event_manager.hass.bus.async_fire.call_args_list
        threshold_call = None
        for call in calls:
            if call[0][0] == EVENT_SOC_THRESHOLD:
                threshold_call = call
                break

        assert threshold_call is not None
        event_data = threshold_call[0][1]
        assert event_data["device_key"] == "battery_1"
        assert event_data["threshold_name"] == "low"
        assert event_data["threshold_value"] == 20
        assert event_data["current_soc"] == 18.0
        assert event_data["direction"] == "below"

    def test_threshold_crossing_upward(self):
        """Test SOC threshold crossing upward."""
        event_manager = create_event_manager()
        # Initialize below threshold
        event_manager.update_soc_state("battery_1", 15.0)
        event_manager.hass.bus.async_fire.reset_mock()

        # Cross low threshold upward (also causes 7% change event)
        event_manager.update_soc_state("battery_1", 22.0)

        # Should fire both threshold and change events
        assert event_manager.hass.bus.async_fire.call_count == 2

        # Find the threshold event
        calls = event_manager.hass.bus.async_fire.call_args_list
        threshold_call = None
        for call in calls:
            if call[0][0] == EVENT_SOC_THRESHOLD:
                threshold_call = call
                break

        assert threshold_call is not None
        event_data = threshold_call[0][1]
        assert event_data["threshold_name"] == "low"
        assert event_data["direction"] == "above"

    def test_significant_change_events(self):
        """Test significant SOC change events."""
        event_manager = create_event_manager()
        # Initialize
        event_manager.update_soc_state("battery_1", 50.0)
        event_manager.hass.bus.async_fire.reset_mock()

        # Make a significant change (≥5%)
        event_manager.update_soc_state("battery_1", 44.0)  # 6% decrease

        # Should fire change event
        event_manager.hass.bus.async_fire.assert_called_once()
        call_args = event_manager.hass.bus.async_fire.call_args

        assert call_args[0][0] == EVENT_SOC_CHANGE
        event_data = call_args[0][1]
        assert event_data["device_key"] == "battery_1"
        assert event_data["change_amount"] == 6.0
        assert event_data["direction"] == "decrease"

    def test_rate_limiting(self):
        """Test event rate limiting."""
        event_manager = create_event_manager()
        # Set short interval for testing
        event_manager.min_event_interval = timedelta(seconds=60)

        # Initialize and trigger first event
        event_manager.update_soc_state("battery_1", 25.0)
        event_manager.update_soc_state("battery_1", 18.0)  # Cross threshold and 7% change

        # Should fire 2 events (threshold + change)
        assert event_manager.hass.bus.async_fire.call_count == 2
        event_manager.hass.bus.async_fire.reset_mock()

        # Trigger another crossing immediately (should be rate limited)
        event_manager.update_soc_state("battery_1", 22.0)  # Cross back
        event_manager.update_soc_state("battery_1", 18.0)  # Cross again

        # Should not fire new event due to rate limiting
        event_manager.hass.bus.async_fire.assert_not_called()

    def test_limit_events(self):
        """Test SOC limit events."""
        event_manager = create_event_manager()
        limits = {
            "strategy_min": 20,
            "strategy_max": 80,
            "bms_min": 10,
            "bms_max": 95,
        }

        # Initialize
        event_manager.update_soc_state("battery_1", 25.0)
        event_manager.hass.bus.async_fire.reset_mock()

        # Reach strategy limit
        event_manager.update_soc_state("battery_1", 20.0, limits)

        # Should fire limit event
        event_manager.hass.bus.async_fire.assert_called()
        call_args = event_manager.hass.bus.async_fire.call_args

        assert call_args[0][0] == EVENT_SOC_LIMIT
        event_data = call_args[0][1]
        assert event_data["device_key"] == "battery_1"
        assert event_data["limit_type"] == "strategy_min"
        assert event_data["limit_value"] == 20

    def test_no_events_for_small_changes(self):
        """Test that small changes don't trigger events."""
        event_manager = create_event_manager()
        # Initialize
        event_manager.update_soc_state("battery_1", 50.0)
        event_manager.hass.bus.async_fire.reset_mock()

        # Make small changes (< 5%)
        event_manager.update_soc_state("battery_1", 52.0)  # 2% increase
        event_manager.update_soc_state("battery_1", 49.0)  # 3% total change

        # Should not fire any events
        event_manager.hass.bus.async_fire.assert_not_called()

    def test_multiple_threshold_crossings(self):
        """Test multiple threshold crossings in one update."""
        event_manager = create_event_manager()
        # Initialize at high value
        event_manager.update_soc_state("battery_1", 95.0)
        event_manager.hass.bus.async_fire.reset_mock()

        # Drop to very low value (crosses multiple thresholds)
        event_manager.update_soc_state("battery_1", 8.0)

        # Should fire multiple threshold events
        assert event_manager.hass.bus.async_fire.call_count >= 2  # At least high and critical_low

        # Check that critical_low event was fired
        calls = event_manager.hass.bus.async_fire.call_args_list
        threshold_names = [call[0][1]["threshold_name"] for call in calls if call[0][0] == EVENT_SOC_THRESHOLD]
        assert "critical_low" in threshold_names

    def test_configuration_update(self):
        """Test configuration updates."""
        event_manager = create_event_manager()
        new_config = {
            "soc_thresholds": {
                "critical_low": 5,
                "low": 15,
                "high": 85,
                "critical_high": 98,
            },
            "soc_change_threshold": 10,
            "min_event_interval_seconds": 30,
        }

        event_manager.update_configuration(new_config)

        assert event_manager.thresholds["critical_low"] == 5
        assert event_manager.thresholds["low"] == 15
        assert event_manager.change_threshold == 10
        assert event_manager.min_event_interval == timedelta(seconds=30)
