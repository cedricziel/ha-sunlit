"""Manage BK215 local-mode TCP clients gated by the cloud's local-mode flag.

For each family's device coordinator, the manager watches every battery
that advertises ``supportLocalMode`` and the live ``localModeEnabled`` flag.
When both are true and the battery's LAN address is known (captured into
``entry.data[CONF_BATTERIES]`` by the zeroconf step), a persistent TCP
client is started; telemetry pushes are translated and merged into the
device coordinator so existing sensors refresh faster than the 30 s cloud
poll.

The cloud poll stays as the floor: a dropped TCP connection or a routine
cloud refresh both still keep entities populated.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback

from ..const import DEVICE_TYPE_BATTERY
from .tcp_client import BK215LocalClient
from .translate import translate_to_device_keys

_LOGGER = logging.getLogger(__name__)


class LocalChannelManager:
    """Reconcile BK215 local TCP clients with cloud-reported state."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_coordinators: dict[str, Any],
        batteries: dict[str, dict[str, Any]],
        *,
        client_factory: Callable[..., BK215LocalClient] = BK215LocalClient,
    ) -> None:
        """Initialize the manager.

        Args:
            hass: HomeAssistant instance for scheduling teardown tasks.
            device_coordinators: ``family_id`` -> SunlitDeviceCoordinator.
            batteries: ``serial`` -> ``{host, port, sw_version, hw_version}``
                from ``entry.data[CONF_BATTERIES]``.
            client_factory: TCP client constructor (overridable for tests).
        """
        self._hass = hass
        self._device_coordinators = device_coordinators
        self._batteries = batteries
        self._client_factory = client_factory
        self._clients: dict[str, BK215LocalClient] = {}
        self._unsubscribers: list[Callable[[], None]] = []

    def start(self) -> None:
        """Subscribe to every coordinator and reconcile against current state."""
        for coordinator in self._device_coordinators.values():
            unsub = coordinator.async_add_listener(self._make_listener(coordinator))
            self._unsubscribers.append(unsub)
            # Reconcile once now so we don't wait for the next coordinator tick.
            self._on_coordinator_update(coordinator)

    async def async_stop(self) -> None:
        """Detach from coordinators and stop every running client."""
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()
        for client in list(self._clients.values()):
            await client.async_stop()
        self._clients.clear()

    def _make_listener(self, coordinator: Any) -> Callable[[], None]:
        """Bind a coordinator into a no-arg listener callback."""

        @callback
        def listener() -> None:
            self._on_coordinator_update(coordinator)

        return listener

    @callback
    def _on_coordinator_update(self, coordinator: Any) -> None:
        """Reconcile every battery in this coordinator's data."""
        if coordinator.data is None:
            return
        devices = coordinator.data.get("devices", {})
        for device_id, device_data in devices.items():
            if device_data.get("deviceType") != DEVICE_TYPE_BATTERY:
                continue
            self._reconcile_battery(coordinator, device_id, device_data)

    def _reconcile_battery(
        self,
        coordinator: Any,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Start or stop the local client for one battery to match state."""
        cloud_device = (
            coordinator.devices.get(device_id) if coordinator.devices else None
        )
        serial = cloud_device.get("deviceSn") if cloud_device else None
        if not serial:
            return

        wants_local = bool(
            device_data.get("support_local_mode")
            and device_data.get("local_mode_enabled")
        )
        battery_info = self._batteries.get(serial)
        current_client = self._clients.get(serial)

        if wants_local and battery_info and current_client is None:
            self._start_client(serial, battery_info, coordinator, device_id)
        elif (not wants_local or not battery_info) and current_client is not None:
            self._stop_client(serial)

    def _start_client(
        self,
        serial: str,
        battery_info: dict[str, Any],
        coordinator: Any,
        device_id: str,
    ) -> None:
        host = battery_info["host"]
        port = battery_info["port"]
        _LOGGER.info(
            "Starting local channel for battery %s at %s:%s", serial, host, port
        )
        client = self._client_factory(
            host=host,
            port=port,
            on_telemetry=self._make_telemetry_callback(coordinator, device_id),
            name=serial,
        )
        client.start()
        self._clients[serial] = client

    def _stop_client(self, serial: str) -> None:
        client = self._clients.pop(serial, None)
        if client is None:
            return
        _LOGGER.info("Stopping local channel for battery %s", serial)
        # Listeners run in a sync context; defer the async teardown.
        self._hass.async_create_task(client.async_stop())

    def _make_telemetry_callback(
        self, coordinator: Any, device_id: str
    ) -> Callable[[dict[str, Any]], None]:
        """Bind coordinator+device into a telemetry-handling callable."""

        def on_telemetry(decoded: dict[str, Any]) -> None:
            self._push_telemetry(coordinator, device_id, decoded)

        return on_telemetry

    @callback
    def _push_telemetry(
        self,
        coordinator: Any,
        device_id: str,
        decoded: dict[str, Any],
    ) -> None:
        """Merge translated local registers into the coordinator's data."""
        translated = translate_to_device_keys(decoded)
        if not translated:
            return
        current_data = coordinator.data
        if not current_data:
            return
        devices = current_data.get("devices", {})
        if device_id not in devices:
            return
        merged = {**devices[device_id], **translated}
        new_data = {
            **current_data,
            "devices": {**devices, device_id: merged},
        }
        coordinator.async_set_updated_data(new_data)
