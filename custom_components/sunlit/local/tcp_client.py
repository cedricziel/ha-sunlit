"""Asyncio TCP client for the BK215 local-mode channel.

A single persistent connection per battery. The device pushes telemetry
unsolicited; we decode it and hand it to ``on_telemetry``. Writes go out as
``0x6056`` set requests and resolve when the matching ``0x6057`` ack arrives.

The client owns its own reconnect lifecycle: :meth:`start` launches a
background task that connects, listens, and re-dials on drop until
:meth:`async_stop` is called. It is deliberately Home Assistant-agnostic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging
from typing import Any

from .protocol import (
    CODE_SET_ACK,
    DEFAULT_PORT,
    TELEMETRY_CODES,
    build_set_payload,
    decode_telemetry,
    is_set_ack_success,
    iter_messages,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0  # seconds to establish the TCP connection
HEARTBEAT_TIMEOUT = 60.0  # silence after which we assume the link is dead
RECONNECT_DELAY = 5.0  # backoff between reconnect attempts
READ_SIZE = 2048  # bytes per socket read
MAX_BUFFER = 65536  # drop a runaway line that never terminates
SET_TIMEOUT = 2.0  # seconds to wait for a set ack


class BK215LocalClient:
    """Persistent TCP client for one BK215 battery."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        on_telemetry: Callable[[dict[str, Any]], None] | None = None,
        on_state_change: Callable[[bool], None] | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            host: LAN address of the battery (from zeroconf).
            port: TCP control port (defaults to the observed 8000).
            on_telemetry: called with each decoded telemetry map.
            on_state_change: called with the new ``connected`` value on change.
            name: label for log lines (e.g. the serial number).
        """
        self._host = host
        self._port = port
        self._on_telemetry = on_telemetry
        self._on_state_change = on_state_change
        self._name = name or f"{host}:{port}"

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._closing = False
        self._connected = False
        self._pending_acks: dict[str, list[asyncio.Future[bool]]] = {}

    @property
    def connected(self) -> bool:
        """Whether the socket is currently up."""
        return self._connected

    def start(self) -> None:
        """Launch the connect/listen/reconnect background task."""
        if self._task is not None and not self._task.done():
            return
        self._closing = False
        self._task = asyncio.create_task(self._run(), name=f"bk215-local-{self._name}")

    async def async_stop(self) -> None:
        """Stop the client and close the connection."""
        self._closing = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close_connection()
        self._fail_pending_acks()

    async def set_register(
        self, field: str, value: int, timeout: float = SET_TIMEOUT
    ) -> bool:
        """Write a single register and wait for the device's ack.

        Returns True on a success ack, False if not connected, the write
        fails, or no successful ack arrives within ``timeout``.
        """
        if not self._connected or self._writer is None:
            return False

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending_acks.setdefault(field, []).append(future)
        try:
            self._writer.write(build_set_payload(field, value).encode("ascii"))
            await self._writer.drain()
            return await asyncio.wait_for(future, timeout)
        except (TimeoutError, OSError) as err:
            _LOGGER.debug("[%s] set %s=%s failed: %s", self._name, field, value, err)
            return False
        finally:
            waiters = self._pending_acks.get(field)
            if waiters and future in waiters:
                waiters.remove(future)
            if waiters is not None and not waiters:
                self._pending_acks.pop(field, None)

    # --- internals ---------------------------------------------------------

    async def _run(self) -> None:
        """Connect, listen, and re-dial until stopped."""
        while not self._closing:
            try:
                await self._connect()
                await self._listen()
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError) as err:
                _LOGGER.debug("[%s] connection error: %s", self._name, err)
            finally:
                await self._close_connection()
            if self._closing:
                break
            await asyncio.sleep(RECONNECT_DELAY)

    async def _connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
        )
        self._set_connected(True)
        _LOGGER.info("[%s] connected", self._name)

    async def _listen(self) -> None:
        """Read and dispatch frames until EOF, error, or heartbeat timeout."""
        assert self._reader is not None
        buffer = ""
        while not self._closing:
            data = await asyncio.wait_for(
                self._reader.read(READ_SIZE), HEARTBEAT_TIMEOUT
            )
            if not data:  # EOF: peer closed the connection
                _LOGGER.debug("[%s] peer closed connection", self._name)
                break
            buffer += data.decode("ascii", errors="ignore")
            messages, buffer = iter_messages(buffer)
            for code, payload in messages:
                self._handle_message(code, payload)
            if len(buffer) > MAX_BUFFER:  # never-terminated junk: drop it
                buffer = ""

    def _handle_message(self, code: int, data: dict[str, int]) -> None:
        if code in TELEMETRY_CODES:
            decoded = decode_telemetry(data)
            if decoded and self._on_telemetry is not None:
                self._safe_callback("on_telemetry", self._on_telemetry, decoded)
        elif code == CODE_SET_ACK:
            self._resolve_acks(data)

    def _resolve_acks(self, data: dict[str, int]) -> None:
        for field in list(self._pending_acks):
            if field not in data:
                continue
            success = is_set_ack_success(field, data)
            for future in self._pending_acks.get(field, []):
                if not future.done():
                    future.set_result(success)

    def _fail_pending_acks(self) -> None:
        for waiters in self._pending_acks.values():
            for future in waiters:
                if not future.done():
                    future.set_result(False)
        self._pending_acks.clear()

    async def _close_connection(self) -> None:
        self._set_connected(False)
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(OSError, asyncio.TimeoutError):
                await asyncio.wait_for(self._writer.wait_closed(), CONNECT_TIMEOUT)
        self._reader = None
        self._writer = None

    def _set_connected(self, value: bool) -> None:
        if value == self._connected:
            return
        self._connected = value
        if self._on_state_change is not None:
            self._safe_callback("on_state_change", self._on_state_change, value)

    def _safe_callback(self, name: str, callback: Callable, *args: Any) -> None:
        """Invoke a user callback; log and swallow any exception.

        Callbacks run on the listen task; an unhandled exception there would
        terminate the background loop and silently disable the client.
        """
        try:
            callback(*args)
        except Exception:  # pragma: no cover - defensive isolation
            _LOGGER.exception("[%s] %s callback raised", self._name, name)
