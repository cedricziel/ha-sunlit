"""Tests for the BK215 local-channel manager.

The manager's job is reconciliation: starting/stopping a TCP client per
battery to match the cloud-reported ``local_mode_enabled`` state and
pushing translated telemetry into the device coordinator. These tests use
a fake coordinator and a fake client to exercise that reconciliation
without touching real sockets — the real TCP client is covered by
test_local_tcp_client.py against a loopback server.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from custom_components.sunlit.local.manager import LocalChannelManager

BATTERY_DEVICE_ID = "1001"
BATTERY_SERIAL = "HP-BK215-001"
BATTERY_HOST = "192.168.1.50"
BATTERY_PORT = 8000


class FakeCoordinator:
    """Stand-in for SunlitDeviceCoordinator with the bits the manager touches."""

    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None
        self.devices: dict[str, dict[str, Any]] = {}
        self._listeners: list[Callable[[], None]] = []

    def async_add_listener(
        self, update_callback: Callable[[], None]
    ) -> Callable[[], None]:
        self._listeners.append(update_callback)

        def _unsub() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _unsub

    def async_set_updated_data(self, data: dict[str, Any]) -> None:
        self.data = data
        for callback in list(self._listeners):
            callback()

    # Test helpers ---------------------------------------------------------

    def seed_battery(
        self,
        *,
        device_id: str = BATTERY_DEVICE_ID,
        serial: str = BATTERY_SERIAL,
        support_local_mode: bool = True,
        local_mode_enabled: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Push an initial coordinator state with one battery present."""
        self.devices = {device_id: {"deviceId": device_id, "deviceSn": serial}}
        device_data: dict[str, Any] = {
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "support_local_mode": support_local_mode,
            "local_mode_enabled": local_mode_enabled,
        }
        if extra:
            device_data.update(extra)
        self.async_set_updated_data({"devices": {device_id: device_data}})


class FakeClient:
    """TCP client stand-in capturing start/stop and exposing the callback."""

    instances: ClassVar[list[FakeClient]] = []

    def __init__(
        self,
        *,
        host: str,
        port: int,
        on_telemetry: Callable[[dict[str, Any]], None] | None = None,
        on_state_change: Callable[[bool], None] | None = None,
        name: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_telemetry = on_telemetry
        self.on_state_change = on_state_change
        self.name = name
        self.started = False
        self.stopped = False
        FakeClient.instances.append(self)

    def start(self) -> None:
        self.started = True

    async def async_stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def _reset_fake_clients():
    FakeClient.instances.clear()
    yield
    FakeClient.instances.clear()


@pytest.fixture
def batteries() -> dict[str, dict[str, Any]]:
    """A populated batteries map keyed by serial."""
    return {
        BATTERY_SERIAL: {
            "serial": BATTERY_SERIAL,
            "host": BATTERY_HOST,
            "port": BATTERY_PORT,
            "sw_version": "1.2.3",
            "hw_version": "BK215",
        }
    }


def _make_manager(
    hass, coordinator: FakeCoordinator, batteries: dict[str, dict[str, Any]]
) -> LocalChannelManager:
    return LocalChannelManager(
        hass,
        device_coordinators={"34038": coordinator},
        batteries=batteries,
        client_factory=FakeClient,
    )


async def test_starts_client_when_local_mode_enabled(hass, batteries):
    """A battery with support+enabled+host gets a client started."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery()
    manager = _make_manager(hass, coordinator, batteries)

    manager.start()

    assert len(FakeClient.instances) == 1
    client = FakeClient.instances[0]
    assert client.host == BATTERY_HOST
    assert client.port == BATTERY_PORT
    assert client.name == BATTERY_SERIAL
    assert client.started is True

    await manager.async_stop()


async def test_skips_battery_with_unknown_host(hass):
    """A battery whose serial isn't in the batteries map is left alone."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery()
    # batteries map is empty -> no known host
    manager = _make_manager(hass, coordinator, batteries={})

    manager.start()

    assert FakeClient.instances == []
    await manager.async_stop()


async def test_skips_battery_when_local_mode_disabled(hass, batteries):
    """When local_mode_enabled is False, no client is started."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery(local_mode_enabled=False)
    manager = _make_manager(hass, coordinator, batteries)

    manager.start()

    assert FakeClient.instances == []
    await manager.async_stop()


async def test_starts_when_flag_flips_on_after_setup(hass, batteries):
    """A battery that turns local mode on at runtime gets a client started."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery(local_mode_enabled=False)
    manager = _make_manager(hass, coordinator, batteries)
    manager.start()
    assert FakeClient.instances == []

    # Flip the flag on via a coordinator update (as the cloud poll would).
    coordinator.seed_battery(local_mode_enabled=True)

    assert len(FakeClient.instances) == 1
    assert FakeClient.instances[0].started is True

    await manager.async_stop()


async def test_stops_client_when_local_mode_flips_off(hass, batteries):
    """A previously running client is torn down when the flag flips off."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery()
    manager = _make_manager(hass, coordinator, batteries)
    manager.start()
    client = FakeClient.instances[0]
    assert client.started

    coordinator.seed_battery(local_mode_enabled=False)
    # Stopping happens via hass.async_create_task; let the loop run.
    await hass.async_block_till_done()

    assert client.stopped is True
    await manager.async_stop()


async def test_telemetry_merges_into_coordinator(hass, batteries):
    """A telemetry push is translated and merged onto the battery device."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery(extra={"battery_level": 30, "input_power_total": 0})
    manager = _make_manager(hass, coordinator, batteries)
    manager.start()
    client = FakeClient.instances[0]

    # Simulate the TCP client delivering decoded telemetry.
    client.on_telemetry({"t211": 73, "t33": 1200, "t536": 43.0})

    device = coordinator.data["devices"][BATTERY_DEVICE_ID]
    assert device["battery_level"] == 73
    assert device["batterySoc"] == 73
    assert device["input_power_total"] == 1200
    assert device["batteryMppt1InVol"] == 43.0
    # Unrelated cloud fields are preserved.
    assert device["deviceType"] == "ENERGY_STORAGE_BATTERY"

    await manager.async_stop()


async def test_telemetry_for_unknown_device_is_ignored(hass, batteries):
    """A push for a device_id not in the coordinator is silently dropped."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery()
    manager = _make_manager(hass, coordinator, batteries)
    manager.start()
    client = FakeClient.instances[0]

    # Remove the battery from the coordinator between bind and push.
    coordinator.async_set_updated_data({"devices": {}})

    # This should not raise even though the device is gone.
    client.on_telemetry({"t211": 99})

    assert coordinator.data == {"devices": {}}
    await manager.async_stop()


async def test_async_stop_tears_down_all_clients(hass, batteries):
    """async_stop closes every running client and detaches listeners."""
    coordinator = FakeCoordinator()
    coordinator.seed_battery()
    manager = _make_manager(hass, coordinator, batteries)
    manager.start()
    client = FakeClient.instances[0]

    await manager.async_stop()

    assert client.stopped is True
    # A subsequent coordinator update must not resurrect anything.
    coordinator.seed_battery()
    assert len(FakeClient.instances) == 1
