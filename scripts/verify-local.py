#!/usr/bin/env python3
"""Probe a live BK215 to verify the local-mode TCP protocol assumptions.

Eats our own dogfood: imports the same ``custom_components.sunlit.local``
modules the integration uses. If this script works against a real device,
the integration code does too.

By default the script is **read-only**: it discovers a BK215 via mDNS,
opens a persistent TCP connection, prints decoded telemetry for 30 s,
then quits. Pass ``--raw`` to see the unfiltered byte stream (e.g. to
spot 0xAA keepalives the high-level client filters out). Pass
``--write tNNN=value`` to test the set / 0x6057-ack path against one
register; the flag is intentionally explicit so a write doesn't happen
by accident.

Usage::

    .venv/bin/python scripts/verify-local.py
    .venv/bin/python scripts/verify-local.py --listen 120
    .venv/bin/python scripts/verify-local.py --host 192.168.1.50 --raw 15
    .venv/bin/python scripts/verify-local.py --write t362=15  # CAREFUL
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

# Run-from-anywhere: make the repo importable without an install step.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from custom_components.sunlit.local.protocol import (  # noqa: E402
    DEFAULT_PORT,
    TELEMETRY_CODES,
)
from custom_components.sunlit.local.tcp_client import BK215LocalClient  # noqa: E402

ZEROCONF_SERVICE_TYPE = "_http._tcp.local."
ZEROCONF_NAME_FRAGMENT = "hp-bk215"


def _now() -> str:
    """Compact ISO timestamp with milliseconds for diagnostic output."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def discover_bk215(timeout: float = 5.0) -> dict[str, Any] | None:
    """Browse mDNS for ``hp-bk215*`` and return its (host, port, props).

    Returns ``None`` if nothing is found within ``timeout`` seconds. The
    returned dict carries the parsed first IP address, the TXT ``port``
    value (the TCP control port, not the mDNS service port), and the full
    TXT properties so a caller can spot-check our assumptions.
    """
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    found: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

    resolve_tasks: list[asyncio.Task] = []

    def _handler(*, zeroconf, service_type, name, state_change):
        if state_change != ServiceStateChange.Added:
            return
        if ZEROCONF_NAME_FRAGMENT not in name.lower():
            return
        resolve_tasks.append(
            asyncio.create_task(_resolve(zeroconf, service_type, name))
        )

    async def _resolve(zc, service_type, name):
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(zc, 3000):
            return
        addresses = info.parsed_addresses()
        if not addresses:
            return
        properties = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in (info.properties or {}).items()
        }
        host = addresses[0]
        # TXT carries the control port; the mDNS service port is the _http
        # port and not what the local channel uses.
        port_raw = properties.get("port")
        try:
            port = int(port_raw) if port_raw is not None else DEFAULT_PORT
        except (TypeError, ValueError):
            port = DEFAULT_PORT
        if not found.done():
            found.set_result(
                {
                    "service_name": name,
                    "host": host,
                    "addresses": addresses,
                    "service_port": info.port,
                    "tcp_port": port,
                    "properties": properties,
                }
            )

    azc = AsyncZeroconf()
    browser = AsyncServiceBrowser(
        azc.zeroconf, [ZEROCONF_SERVICE_TYPE], handlers=[_handler]
    )
    try:
        return await asyncio.wait_for(found, timeout=timeout)
    except TimeoutError:
        return None
    finally:
        await browser.async_cancel()
        await azc.async_close()


def _format_discovery(info: dict[str, Any]) -> str:
    lines = [
        f"  service:    {info['service_name']}",
        f"  host:       {info['host']}  (all: {info['addresses']})",
        f"  mDNS port:  {info['service_port']}  (the _http port; not used)",
        f"  TCP port:   {info['tcp_port']}  (from TXT 'port'; used by local channel)",
        "  TXT properties:",
    ]
    for key, value in sorted(info["properties"].items()):
        lines.append(f"    {key}: {value!r}")
    return "\n".join(lines)


async def listen_decoded(host: str, port: int, seconds: float) -> None:
    """Listen for ``seconds`` and print every decoded telemetry push.

    Also tracks the per-code message counts so we can confirm the protocol
    doc's claim about three telemetry kinds (0x6052/0x6055/0x6060).
    """
    push_count = 0
    code_counts: dict[int, int] = dict.fromkeys(TELEMETRY_CODES, 0)
    field_counts: dict[str, int] = {}
    state_history: list[tuple[str, bool]] = []

    def _on_telemetry(decoded: dict[str, Any]) -> None:
        nonlocal push_count
        push_count += 1
        for field in decoded:
            field_counts[field] = field_counts.get(field, 0) + 1
        compact = ", ".join(f"{k}={v}" for k, v in sorted(decoded.items()))
        print(f"[{_now()}]  #{push_count:>3}  {compact}")

    def _on_state(connected: bool) -> None:
        state_history.append((_now(), connected))
        marker = "connected" if connected else "disconnected"
        print(f"[{_now()}]  -- {marker} --")

    client = BK215LocalClient(
        host=host,
        port=port,
        on_telemetry=_on_telemetry,
        on_state_change=_on_state,
        name=f"{host}:{port}",
    )

    # We can't intercept code counts via the high-level client, so we also
    # tap the raw line stream by patching _handle_message. Cheaper than
    # reimplementing the connection.
    original_handle = client._handle_message

    def _counting_handle(code: int, data: dict[str, int]) -> None:
        if code in code_counts:
            code_counts[code] += 1
        original_handle(code, data)

    client._handle_message = _counting_handle  # type: ignore[assignment]

    client.start()
    try:
        await asyncio.sleep(seconds)
    finally:
        await client.async_stop()

    print()
    print(f"Listened for {seconds:.1f}s; received {push_count} telemetry pushes.")
    if push_count:
        rate = push_count / seconds
        print(f"  Push rate:  {rate:.2f}/s  ({1 / rate:.2f}s between pushes)")
    print("  Per-code counts:")
    for code, count in sorted(code_counts.items()):
        print(f"    0x{code:04X} ({code}): {count}")
    print(f"  Distinct fields seen: {len(field_counts)}")
    top_fields = sorted(field_counts.items(), key=lambda kv: -kv[1])[:15]
    for field, count in top_fields:
        print(f"    {field}: {count}")
    if state_history:
        print(f"  State transitions: {len(state_history)}")


async def listen_raw(host: str, port: int, seconds: float) -> None:
    """Dump raw bytes from the socket, both hex and ASCII, for ``seconds``.

    This bypasses the protocol layer entirely so we can observe the 0xAA
    keepalive bytes the doc mentions but the high-level client filters
    out, plus any framing oddities (concatenated objects, etc.).
    """
    print(f"[{_now()}]  opening raw TCP {host}:{port}")
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=5.0
    )
    print(f"[{_now()}]  connected; reading for {seconds:.1f}s")

    total = 0
    keepalive_count = 0
    try:
        end_at = asyncio.get_running_loop().time() + seconds
        while True:
            remaining = end_at - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=remaining)
            except TimeoutError:
                break
            if not chunk:
                print(f"[{_now()}]  peer closed connection")
                break
            total += len(chunk)
            keepalive_count += chunk.count(b"\xaa")
            preview = chunk[:96]
            hex_preview = preview.hex(" ")
            ascii_preview = "".join(
                c if 32 <= ord(c) < 127 else "." for c in preview.decode("latin-1")
            )
            print(
                f"[{_now()}]  +{len(chunk):>4}B  "
                f"hex={hex_preview}{'...' if len(chunk) > 96 else ''}"
            )
            print(f"             ascii={ascii_preview!r}")
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except (TimeoutError, OSError):
            pass

    print()
    print(f"Raw bytes received: {total}")
    print(f"  0xAA bytes (keepalives): {keepalive_count}")


def _parse_write(spec: str) -> tuple[str, int]:
    """Parse ``--write tNNN=value`` into (field, int_value)."""
    if "=" not in spec:
        raise argparse.ArgumentTypeError(f"--write must be FIELD=VALUE, got {spec!r}")
    field, value_str = spec.split("=", 1)
    field = field.strip()
    try:
        value = int(value_str.strip())
    except ValueError as err:
        raise argparse.ArgumentTypeError(
            f"--write value must be an int, got {value_str!r}"
        ) from err
    if not field.startswith("t"):
        raise argparse.ArgumentTypeError(
            f"--write field must look like 'tNNN', got {field!r}"
        )
    return field, value


async def perform_write(host: str, port: int, field: str, value: int) -> None:
    """Send one set request, await its ack, and watch the value stick."""
    pre_values: list[int] = []
    post_values: list[int] = []
    phase = {"name": "pre"}

    def _capture(decoded: dict[str, Any]) -> None:
        if field not in decoded:
            return
        target = pre_values if phase["name"] == "pre" else post_values
        target.append(decoded[field])
        print(f"[{_now()}]  observed {field}={decoded[field]} ({phase['name']})")

    client = BK215LocalClient(
        host=host, port=port, on_telemetry=_capture, name=f"{host}:{port}"
    )
    client.start()

    try:
        # Watch for ~5 s so we capture the current value before mutating.
        print(f"[{_now()}]  pre-write listen for 5s to capture {field} baseline")
        await asyncio.sleep(5.0)
        baseline = pre_values[-1] if pre_values else None
        print(f"[{_now()}]  baseline {field}={baseline!r}  ->  writing {value}")

        phase["name"] = "post"
        ok = await client.set_register(field, value)
        print(f"[{_now()}]  set-ack success={ok}")

        # Listen for ~15 s to confirm the change persists in subsequent
        # telemetry pushes.
        print(f"[{_now()}]  post-write listen for 15s to confirm {field}")
        await asyncio.sleep(15.0)

        if post_values:
            print(f"[{_now()}]  post-write {field} values seen: {post_values}")
            if all(v == value for v in post_values):
                print(f"[{_now()}]  ✓ device telemetry now reports {field}={value}")
            else:
                print(f"[{_now()}]  ✗ telemetry did NOT settle on {value}")
        else:
            print(f"[{_now()}]  (no post-write {field} pushes observed; can't confirm)")

        if baseline is not None and baseline != value:
            print(
                f"[{_now()}]  REMINDER: original value was {baseline}; "
                f"re-run with --write {field}={baseline} to restore."
            )
    finally:
        await client.async_stop()


async def _amain(args: argparse.Namespace) -> int:
    if args.host is None:
        print(f"[{_now()}]  discovering hp-bk215* via mDNS...")
        discovery = await discover_bk215(timeout=args.discovery_timeout)
        if discovery is None:
            print("No BK215 found on the local network.")
            print("Pass --host HOST [--port PORT] to skip discovery.")
            return 2
        print(_format_discovery(discovery))
        host = discovery["host"]
        port = args.port if args.port is not None else discovery["tcp_port"]
    else:
        host = args.host
        port = args.port if args.port is not None else DEFAULT_PORT

    print()
    print(f"[{_now()}]  target = {host}:{port}")
    print()

    if args.write is not None:
        if args.raw:
            print("--write and --raw are mutually exclusive.")
            return 2
        field, value = args.write
        await perform_write(host, port, field, value)
    elif args.raw:
        await listen_raw(host, port, args.raw)
    else:
        await listen_decoded(host, port, args.listen)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--host",
        help="LAN address of the BK215 (skip mDNS discovery).",
    )
    parser.add_argument(
        "--port",
        type=int,
        help=f"TCP control port (default: TXT 'port' or {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--listen",
        type=float,
        default=30.0,
        help="Seconds to listen for decoded telemetry (default: 30).",
    )
    parser.add_argument(
        "--raw",
        nargs="?",
        type=float,
        const=15.0,
        default=None,
        metavar="SECS",
        help="Print raw socket bytes (no protocol parsing) for N seconds (default 15).",
    )
    parser.add_argument(
        "--write",
        type=_parse_write,
        metavar="FIELD=VALUE",
        help="(MUTATING) Write one register and confirm via ack + telemetry.",
    )
    parser.add_argument(
        "--discovery-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for mDNS discovery (default: 5).",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
