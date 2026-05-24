"""Tests for the battery local-mode switch (issue #160)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.sunlit.entities.device_switch import (
    SunlitBatteryLocalModeSwitch,
)


def _make_switch(local_mode_enabled=True, device_sn="dcbdccbffe3d"):
    """Build a switch wired to a mock device coordinator."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.api_client = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.data = {
        "devices": {
            "battery_001": {
                "support_local_mode": True,
                "local_mode_enabled": local_mode_enabled,
            }
        }
    }

    switch = SunlitBatteryLocalModeSwitch(
        coordinator=coordinator,
        entry_id="entry",
        family_id="34038",
        family_name="Test Family",
        device_id="battery_001",
        device_info_data={
            "deviceSn": device_sn,
            "deviceType": "ENERGY_STORAGE_BATTERY",
        },
    )
    # Bypass HA state writes (no hass in these unit tests).
    switch.async_write_ha_state = MagicMock()
    return switch, coordinator


def test_is_on_reflects_coordinator():
    """is_on tracks the coordinator's local_mode_enabled value."""
    on_switch, _ = _make_switch(True)
    assert on_switch.is_on is True

    off_switch, _ = _make_switch(False)
    assert off_switch.is_on is False


def test_is_on_none_when_missing():
    """is_on is None when the value is absent."""
    switch, coordinator = _make_switch(True)
    coordinator.data["devices"]["battery_001"].pop("local_mode_enabled")
    assert switch.is_on is None
    assert switch.available is False


def test_unique_id_and_name():
    """Switch has a stable unique_id and a short name."""
    switch, _ = _make_switch()
    assert (
        switch.unique_id
        == "sunlit_test_family_34038_battery_battery_001_local_mode"
    )
    assert switch._attr_name == "Local Mode"


@pytest.mark.asyncio
async def test_turn_on_calls_api_and_refreshes():
    """Turning on writes via the API, updates state, and refreshes."""
    switch, coordinator = _make_switch(False)

    await switch.async_turn_on()

    coordinator.api_client.update_battery_local_mode.assert_awaited_once_with(
        "dcbdccbffe3d", True
    )
    # Optimistic update applied
    assert coordinator.data["devices"]["battery_001"]["local_mode_enabled"] is True
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_off_calls_api():
    """Turning off sends enable=False with the device serial."""
    switch, coordinator = _make_switch(True)

    await switch.async_turn_off()

    coordinator.api_client.update_battery_local_mode.assert_awaited_once_with(
        "dcbdccbffe3d", False
    )


@pytest.mark.asyncio
async def test_api_error_raises_home_assistant_error():
    """A failing control call surfaces as HomeAssistantError."""
    switch, coordinator = _make_switch(True)
    coordinator.api_client.update_battery_local_mode.side_effect = Exception("boom")

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_serial_raises():
    """Without a device serial the switch refuses to write."""
    switch, coordinator = _make_switch(True, device_sn=None)

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    coordinator.api_client.update_battery_local_mode.assert_not_awaited()
