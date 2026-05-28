"""Tests for the BK215 local-mode TCP client against a loopback mock server."""

from __future__ import annotations

import asyncio
import json

import pytest

from custom_components.sunlit.local import protocol
from custom_components.sunlit.local.tcp_client import BK215LocalClient


class MockBK215Server:
    """A minimal asyncio TCP server mimicking the battery's push protocol.

    Pushes any queued telemetry lines to a connecting client and, on receiving
    a ``0x6056`` set request, replies with a ``0x6057`` ack echoing the field
    as ``0`` (success).
    """

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self.port = 0
        self.connections = 0
        self.received: list[dict] = []
        self._push_lines: list[str] = []
        self.ack_value = 0  # value echoed back in the set ack

    def queue_telemetry(self, code: int, data: dict) -> None:
        self._push_lines.append(json.dumps({"code": code, "data": data}) + "\n")

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=0
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connections += 1
        for line in self._push_lines:
            writer.write(line.encode("ascii"))
        await writer.drain()
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                parsed = protocol.parse_message(raw.decode("ascii").strip())
                if parsed is None:
                    continue
                code, data = parsed
                self.received.append({"code": code, "data": data})
                if code == protocol.CODE_SET:
                    field = next(iter(data))
                    ack = {
                        "code": protocol.CODE_SET_ACK,
                        "data": {field: self.ack_value},
                    }
                    writer.write((json.dumps(ack) + "\n").encode("ascii"))
                    await writer.drain()
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


@pytest.fixture
async def server(socket_enabled):
    """A loopback mock server. ``socket_enabled`` lifts the HA socket block."""
    srv = MockBK215Server()
    await srv.start()
    yield srv
    await srv.stop()


async def test_receives_and_decodes_telemetry(server: MockBK215Server):
    """Pushed telemetry is decoded and delivered to the callback."""
    server.queue_telemetry(0x6052, {"t211": 50, "t33": 97, "t536": 430})

    received: list[dict] = []
    client = BK215LocalClient("127.0.0.1", server.port, on_telemetry=received.append)
    client.start()
    try:
        await _wait_for(lambda: received)
    finally:
        await client.async_stop()

    assert received[0] == {"t211": 50, "t33": 97, "t536": 43.0}


async def test_set_register_succeeds_on_ack(server: MockBK215Server):
    """A write returns True when the device acks the field with 0."""
    client = BK215LocalClient("127.0.0.1", server.port)
    client.start()
    try:
        await _wait_for(lambda: client.connected)
        result = await client.set_register("t598", 1)
    finally:
        await client.async_stop()

    assert result is True
    assert server.received == [{"code": protocol.CODE_SET, "data": {"t598": 1}}]


async def test_set_register_fails_on_negative_ack(server: MockBK215Server):
    """A non-zero ack value is reported as failure."""
    server.ack_value = 1
    client = BK215LocalClient("127.0.0.1", server.port)
    client.start()
    try:
        await _wait_for(lambda: client.connected)
        result = await client.set_register("t598", 1, timeout=1.0)
    finally:
        await client.async_stop()

    assert result is False


async def test_set_register_fails_when_disconnected(server: MockBK215Server):
    """Writing before a connection exists returns False, not an exception."""
    client = BK215LocalClient("127.0.0.1", server.port)
    # never started
    assert await client.set_register("t598", 1) is False


async def test_reconnects_after_drop(server: MockBK215Server):
    """The client re-dials after the server closes the connection."""
    client = BK215LocalClient("127.0.0.1", server.port)
    # speed the test up: shorten the reconnect backoff
    import custom_components.sunlit.local.tcp_client as mod

    original = mod.RECONNECT_DELAY
    mod.RECONNECT_DELAY = 0.05
    client.start()
    try:
        await _wait_for(lambda: server.connections >= 1)
        await client._close_connection()  # simulate a drop
        await _wait_for(lambda: server.connections >= 2, timeout=3.0)
    finally:
        mod.RECONNECT_DELAY = original
        await client.async_stop()

    assert server.connections >= 2


async def test_state_change_callback(server: MockBK215Server):
    """on_state_change fires True on connect and False on stop."""
    states: list[bool] = []
    client = BK215LocalClient("127.0.0.1", server.port, on_state_change=states.append)
    client.start()
    try:
        await _wait_for(lambda: client.connected)
    finally:
        await client.async_stop()

    assert states[0] is True
    assert states[-1] is False


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    """Poll ``predicate`` until truthy or raise on timeout."""
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)
