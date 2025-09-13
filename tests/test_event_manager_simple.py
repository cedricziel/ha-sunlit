"""Simple tests for the SOC event manager without HomeAssistant fixtures."""

import sys
sys.path.insert(0, '.')

from datetime import timedelta
from unittest.mock import Mock

from custom_components.sunlit.event_manager import (
    EVENT_SOC_THRESHOLD,
    EVENT_SOC_CHANGE,
    SunlitEventManager,
)


def test_event_manager_basic_functionality():
    """Test basic event manager functionality."""
    # Create mocked HomeAssistant instance
    hass = Mock()
    hass.bus = Mock()
    hass.bus.async_fire = Mock()

    # Create event manager
    event_manager = SunlitEventManager(hass, "test_family")

    # Test initialization
    assert event_manager.family_id == "test_family"
    assert event_manager.change_threshold == 5

    # First update should not trigger events
    event_manager.update_soc_state("battery_1", 50.0)
    hass.bus.async_fire.assert_not_called()

    # Reset mock and test threshold crossing
    hass.bus.async_fire.reset_mock()

    # Cross low threshold (20%) - from 50% to 18%
    event_manager.update_soc_state("battery_1", 18.0)

    # Should fire multiple events (threshold + significant change)
    assert hass.bus.async_fire.called, "Expected events to be fired"
    assert hass.bus.async_fire.call_count >= 1, "Expected at least one event"

    # Check all fired events
    all_calls = hass.bus.async_fire.call_args_list
    event_types = [call[0][0] for call in all_calls]

    # Should have both threshold and change events
    assert EVENT_SOC_THRESHOLD in event_types, f"Expected threshold event in {event_types}"
    assert EVENT_SOC_CHANGE in event_types, f"Expected change event in {event_types}"

    # Find the threshold event
    threshold_call = next(call for call in all_calls if call[0][0] == EVENT_SOC_THRESHOLD)
    threshold_data = threshold_call[0][1]
    assert threshold_data["device_key"] == "battery_1"
    assert threshold_data["threshold_name"] == "low"
    assert threshold_data["direction"] == "below"

    print("✓ Event manager basic functionality test passed")


def test_soc_change_events():
    """Test significant SOC change events."""
    hass = Mock()
    hass.bus = Mock()
    hass.bus.async_fire = Mock()

    event_manager = SunlitEventManager(hass, "test_family")

    # Initialize
    event_manager.update_soc_state("battery_1", 50.0)
    hass.bus.async_fire.reset_mock()

    # Make significant change (6% decrease, above 5% threshold)
    event_manager.update_soc_state("battery_1", 44.0)

    # Should fire change event
    assert hass.bus.async_fire.called
    call_args = hass.bus.async_fire.call_args
    assert call_args[0][0] == EVENT_SOC_CHANGE

    event_data = call_args[0][1]
    assert event_data["device_key"] == "battery_1"
    assert event_data["change_amount"] == 6.0
    assert event_data["direction"] == "decrease"

    print("✓ SOC change events test passed")


def test_rate_limiting():
    """Test event rate limiting."""
    hass = Mock()
    hass.bus = Mock()
    hass.bus.async_fire = Mock()

    event_manager = SunlitEventManager(hass, "test_family")
    event_manager.min_event_interval = timedelta(seconds=60)

    # Initialize and trigger first event
    event_manager.update_soc_state("battery_1", 25.0)
    event_manager.update_soc_state("battery_1", 18.0)  # Cross threshold

    # Should fire at least one event (could be multiple due to threshold + change)
    assert hass.bus.async_fire.call_count >= 1, f"Expected events, got {hass.bus.async_fire.call_count}"
    initial_call_count = hass.bus.async_fire.call_count
    hass.bus.async_fire.reset_mock()

    # Trigger another crossing immediately (should be rate limited)
    event_manager.update_soc_state("battery_1", 22.0)  # Cross back up
    event_manager.update_soc_state("battery_1", 18.0)  # Cross down again

    # Should not fire new event due to rate limiting
    hass.bus.async_fire.assert_not_called()

    print("✓ Rate limiting test passed")


if __name__ == "__main__":
    test_event_manager_basic_functionality()
    test_soc_change_events()
    test_rate_limiting()
    print("\n✅ All event manager tests passed!")
