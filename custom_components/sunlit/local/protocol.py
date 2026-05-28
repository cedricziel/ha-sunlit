"""BK215 local-mode TCP protocol: framing, register decode, set payloads.

Clean-room reimplementation from ``docs/local-protocol.md`` (a behavioural spec
only). This module is intentionally Home Assistant-agnostic and side-effect
free so it can be unit-tested against a plain asyncio socket.

The device pushes newline-delimited compact JSON envelopes::

    {"code": 24658, "data": {"t211": 50, "t33": 97, ...}}

``code`` selects the envelope kind (telemetry vs set-ack); ``data`` maps
``tNNN`` register names to raw integers. Unset registers carry the sentinel
``0xFFFFFFFF`` and must be ignored.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any

# --- Transport -------------------------------------------------------------

# Observed TCP control port. The mDNS A-record gives the host; the control
# port is advertised in the TXT ``port`` property (not the _http service port).
DEFAULT_PORT = 8000

# A register carrying this value is unset and should be treated as "no data".
UNSET = 0xFFFFFFFF

# --- Message codes ---------------------------------------------------------

CODE_SET = 0x6056  # client -> device: write one or more registers
CODE_SET_ACK = 0x6057  # device -> client: write ack (field == 0 => success)

# device -> client: unsolicited telemetry pushes (three interleaved kinds)
TELEMETRY_CODES = frozenset({0x6052, 0x6055, 0x6060})


# --- Value scaling ---------------------------------------------------------

Decoder = Callable[[int], Any]


def _linear(factor: float, ndigits: int) -> Decoder:
    """Decode ``raw * factor`` rounded to ``ndigits`` (0 => int)."""

    def decode(raw: int) -> float | int:
        value = raw * factor
        return round(value) if ndigits == 0 else round(value, ndigits)

    return decode


def _offset(offset: int) -> Decoder:
    """Decode ``raw - offset`` (used for Kelvin-ish cell temperatures)."""
    return lambda raw: raw - offset


def heater_bits(raw: int) -> list[bool]:
    """Split the ``t586`` heater bitfield into per-unit booleans.

    Bit 0 is the main unit, bits 1..7 are extension modules 1..7.
    """
    if raw == UNSET:
        return []
    return [bool((raw >> bit) & 1) for bit in range(8)]


# --- Register map ----------------------------------------------------------


@dataclass(frozen=True)
class Register:
    """Decoding metadata for one ``tNNN`` register."""

    decode: Decoder
    unit: str | None = None
    device_class: str | None = None


def _battery(raw_unit: str = "%") -> Register:
    return Register(_linear(1, 0), raw_unit, "battery")


def _power() -> Register:
    return Register(_linear(1, 0), "W", "power")


def _pv_power() -> Register:
    # PV input power is reported centi-watts.
    return Register(_linear(0.01, 2), "W", "power")


def _energy() -> Register:
    return Register(_linear(0.001, 3), "kWh", "energy")


def _voltage() -> Register:
    return Register(_linear(0.1, 1), "V", "voltage")


def _current() -> Register:
    return Register(_linear(0.1, 1), "A", "current")


def _temperature() -> Register:
    return Register(_offset(273), "°C", "temperature")


# Module SOC registers: head unit (t592) + modules 1..7. The slot ordering is
# t593,t594,t595 then jumps to t1001..t1004 for modules 4..7.
_MODULE_SOC = ["t592", "t593", "t594", "t595", "t1001", "t1002", "t1003", "t1004"]
# Per-module MPPT (voltage, current) register pairs, modules 1..7.
_MODULE_MPPT = [
    ("t552", "t553"),
    ("t560", "t561"),
    ("t568", "t569"),
    ("t969", "t970"),
    ("t977", "t978"),
    ("t985", "t986"),
    ("t993", "t994"),
]
# Min cell temperature per unit: head (t220) + modules 1..7.
_CELL_TEMP = ["t220", "t233", "t246", "t259", "t836", "t849", "t862", "t875"]


def _build_registers() -> dict[str, Register]:
    regs: dict[str, Register] = {
        "t211": _battery(),  # system SOC (remaining capacity)
        "t33": _power(),  # total input power
        "t34": _power(),  # total output power
        "t49": _energy(),  # daily generation
        "t66": _energy(),  # daily output energy
        "t710": _energy(),  # charging-box daily AC-charge energy
        "t711": _power(),  # charging-box AC input power
        "t701_4": _power(),  # car-charge mode power
        "t702_4": _power(),  # home-appliance mode power
        # main MPPT 1 & 2 (voltage, current)
        "t536": _voltage(),
        "t537": _current(),
        "t544": _voltage(),
        "t545": _current(),
        "t586": Register(int, None, None),  # heater bitfield (use heater_bits)
        "t475": Register(int, "dB", "signal_strength"),  # RSSI (see decode note)
    }
    # SOC per unit
    for reg in _MODULE_SOC:
        regs[reg] = _battery()
    # PV1..PV9 input power
    for reg in ("t50", "t62", "t63", "t64", "t65", "t812", "t813", "t814", "t815"):
        regs[reg] = _pv_power()
    # per-module MPPT pairs
    for vol_reg, cur_reg in _MODULE_MPPT:
        regs[vol_reg] = _voltage()
        regs[cur_reg] = _current()
    # cell temperatures
    for reg in _CELL_TEMP:
        regs[reg] = _temperature()
    return regs


REGISTERS: dict[str, Register] = _build_registers()


def decode_telemetry(data: dict[str, int]) -> dict[str, Any]:
    """Decode a raw telemetry ``data`` map into scaled values.

    Unset registers (``0xFFFFFFFF``) and unknown register names are dropped.
    Known registers are scaled per their :class:`Register` definition.
    """
    decoded: dict[str, Any] = {}
    for name, raw in data.items():
        if raw == UNSET:
            continue
        register = REGISTERS.get(name)
        if register is None:
            continue
        decoded[name] = register.decode(raw)
    return decoded


# --- Framing ---------------------------------------------------------------


def is_protocol_line(line: str) -> bool:
    """Return whether ``line`` is a single, well-formed protocol envelope.

    Filters out blank lines, ``0xAA`` keepalive bytes, and any line that does
    not look like exactly one ``{"code": ...}`` object.
    """
    stripped = line.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if "\\xaa" in lowered or "code" not in lowered:
        return False
    if not lowered.startswith('{"code":'):
        return False
    # Guard against concatenated objects on one line.
    return lowered.count("code") == 1


def parse_message(line: str) -> tuple[int, dict[str, int]] | None:
    """Parse one protocol line into ``(code, data)`` or ``None`` if invalid."""
    if not is_protocol_line(line):
        return None
    try:
        envelope = json.loads(line)
    except (ValueError, TypeError):
        return None
    code = envelope.get("code")
    if not isinstance(code, int):
        return None
    data = envelope.get("data") or {}
    if not isinstance(data, dict):
        return None
    return code, data


def iter_messages(buffer: str) -> tuple[list[tuple[int, dict[str, int]]], str]:
    """Split a raw read ``buffer`` into parsed messages and a leftover tail.

    Returns ``(messages, remainder)`` where ``remainder`` is an unterminated
    trailing fragment to be prepended to the next read.
    """
    messages: list[tuple[int, dict[str, int]]] = []
    *complete, remainder = buffer.split("\n")
    for line in complete:
        parsed = parse_message(line)
        if parsed is not None:
            messages.append(parsed)
    return messages, remainder


# --- Writing registers -----------------------------------------------------


def build_set_payload(field: str, value: int) -> str:
    """Build a ``code 0x6056`` set request carrying only ``field``.

    The device expects every unchanged register to be omitted (it treats them
    as the unset sentinel), so we send a minimal envelope with just the one
    field being written, as newline-terminated compact JSON.
    """
    envelope = {"code": CODE_SET, "data": {field: value}}
    return json.dumps(envelope, separators=(",", ":")) + "\n"


def is_set_ack_success(field: str, data: dict[str, int]) -> bool:
    """Return whether a set-ack ``data`` map reports success for ``field``.

    The device acks a write by echoing the field with value ``0``.
    """
    return data.get(field) == 0
