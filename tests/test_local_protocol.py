"""Tests for the BK215 local-mode protocol decode and framing."""

from __future__ import annotations

import json

from custom_components.sunlit.local import protocol


def test_decode_value_scaling():
    """Each scaling convention decodes per docs/local-protocol.md."""
    decoded = protocol.decode_telemetry(
        {
            "t211": 50,  # battery %, raw
            "t33": 97,  # power W, raw
            "t49": 1234,  # energy kWh, x0.001
            "t50": 5000,  # PV power W, x0.01
            "t536": 430,  # MPPT voltage V, x0.1
            "t537": 21,  # MPPT current A, x0.1
            "t220": 298,  # cell temp degC, -273
        }
    )
    assert decoded["t211"] == 50
    assert decoded["t33"] == 97
    assert decoded["t49"] == 1.234
    assert decoded["t50"] == 50.0
    assert decoded["t536"] == 43.0
    assert decoded["t537"] == 2.1
    assert decoded["t220"] == 25


def test_decode_drops_unset_sentinel():
    """0xFFFFFFFF registers are omitted from the decoded map."""
    decoded = protocol.decode_telemetry({"t211": protocol.UNSET, "t33": 100})
    assert "t211" not in decoded
    assert decoded["t33"] == 100


def test_decode_drops_unknown_registers():
    """Registers not in the map are ignored rather than passed through raw."""
    decoded = protocol.decode_telemetry({"t999": 5, "t211": 42})
    assert decoded == {"t211": 42}


def test_module_soc_registers_present():
    """Head unit plus seven module SOC slots all decode as battery %."""
    raw = dict.fromkeys(["t592", "t593", "t595", "t1001", "t1004"], 80)
    decoded = protocol.decode_telemetry(raw)
    assert all(decoded[reg] == 80 for reg in raw)


def test_heater_bits():
    """The t586 bitfield splits into head + module booleans."""
    # bits 0 (main) and 2 (module 2) set => 0b101 = 5
    bits = protocol.heater_bits(0b101)
    assert bits[0] is True
    assert bits[1] is False
    assert bits[2] is True
    assert protocol.heater_bits(protocol.UNSET) == []


def test_is_protocol_line_filters():
    """Blank, keepalive, and malformed lines are rejected."""
    assert protocol.is_protocol_line('{"code":24658,"data":{"t211":50}}')
    assert not protocol.is_protocol_line("")
    assert not protocol.is_protocol_line("   ")
    assert not protocol.is_protocol_line(r"\xaa\xaa")
    assert not protocol.is_protocol_line("garbage")
    # two concatenated objects on one line are rejected
    assert not protocol.is_protocol_line('{"code":1}{"code":2}')


def test_parse_message():
    """A valid line parses into (code, data)."""
    parsed = protocol.parse_message('{"code":24658,"data":{"t211":50}}')
    assert parsed == (24658, {"t211": 50})
    assert protocol.parse_message("not json") is None


def test_parse_message_rejects_non_integer_data_values():
    """Strings, floats, and bools in data values reject the whole message.

    decode_telemetry multiplies by a scale factor; admitting strings/floats
    would either crash or quietly poison entity state.
    """
    assert protocol.parse_message('{"code":24658,"data":{"t211":"50"}}') is None
    assert protocol.parse_message('{"code":24658,"data":{"t211":1.5}}') is None
    assert protocol.parse_message('{"code":24658,"data":{"t211":true}}') is None
    # A non-string key would be unusual but also invalid for a register name.
    assert protocol.parse_message('{"code":24658,"data":{"1":50}}') == (
        24658,
        {"1": 50},
    )


def test_iter_messages_buffers_partial_line():
    """A trailing unterminated fragment is returned as the remainder."""
    buffer = '{"code":24658,"data":{"t33":1}}\n{"code":24661,"data":{"t34":2'
    messages, remainder = protocol.iter_messages(buffer)
    assert messages == [(24658, {"t33": 1})]
    assert remainder == '{"code":24661,"data":{"t34":2'

    # Feeding the remainder + rest yields the second message.
    messages, remainder = protocol.iter_messages(remainder + "}}\n")
    assert messages == [(24661, {"t34": 2})]
    assert remainder == ""


def test_build_set_payload_minimal_and_terminated():
    """A set payload carries only the changed field and ends in a newline."""
    payload = protocol.build_set_payload("t598", 1)
    assert payload.endswith("\n")
    envelope = json.loads(payload)
    assert envelope == {"code": protocol.CODE_SET, "data": {"t598": 1}}
    assert " " not in payload  # compact separators


def test_is_set_ack_success():
    """A field echoed as 0 means success; anything else is failure."""
    assert protocol.is_set_ack_success("t598", {"t598": 0})
    assert not protocol.is_set_ack_success("t598", {"t598": 1})
    assert not protocol.is_set_ack_success("t598", {})
