"""Tests for the local-register -> cloud-entity-key translation."""

from __future__ import annotations

from custom_components.sunlit.local.translate import translate_to_device_keys


def test_system_soc_populates_both_cloud_keys():
    """t211 fills both battery_level and batterySoc (the cloud carries both)."""
    result = translate_to_device_keys({"t211": 73})
    assert result == {"battery_level": 73, "batterySoc": 73}


def test_total_power_registers():
    """t33 and t34 map to the totals used by the family-level sensors."""
    result = translate_to_device_keys({"t33": 1200, "t34": 850})
    assert result == {"input_power_total": 1200, "output_power_total": 850}


def test_head_mppt_voltage_current_power():
    """Head MPPT 1 and 2 each map V/I/Power to the cloud's batteryMpptN* keys."""
    decoded = {
        "t536": 43.0,
        "t537": 2.1,
        "t544": 42.8,
        "t545": 1.9,
        "t50": 90,
        "t62": 81,
    }
    result = translate_to_device_keys(decoded)
    assert result == {
        "batteryMppt1InVol": 43.0,
        "batteryMppt1InCur": 2.1,
        "batteryMppt2InVol": 42.8,
        "batteryMppt2InCur": 1.9,
        "batteryMppt1InPower": 90,
        "batteryMppt2InPower": 81,
    }


def test_all_seven_module_socs_map():
    """Modules 1..7 SOCs cover the t593-t595 and t1001-t1004 slot ranges."""
    decoded = {
        "t593": 80,
        "t594": 81,
        "t595": 82,
        "t1001": 83,
        "t1002": 84,
        "t1003": 85,
        "t1004": 86,
    }
    result = translate_to_device_keys(decoded)
    assert result == {
        "battery1Soc": 80,
        "battery2Soc": 81,
        "battery3Soc": 82,
        "battery4Soc": 83,
        "battery5Soc": 84,
        "battery6Soc": 85,
        "battery7Soc": 86,
    }


def test_module_mppt_voltage_current_power():
    """Each module's MPPT V/I/Power maps to batteryNMppt1* cloud keys."""
    decoded = {
        # Module 1
        "t552": 41.0,
        "t553": 1.5,
        "t63": 62,
        # Module 4
        "t969": 40.5,
        "t970": 1.2,
        "t812": 49,
    }
    result = translate_to_device_keys(decoded)
    assert result == {
        "battery1Mppt1InVol": 41.0,
        "battery1Mppt1InCur": 1.5,
        "battery1Mppt1InPower": 62,
        "battery4Mppt1InVol": 40.5,
        "battery4Mppt1InCur": 1.2,
        "battery4Mppt1InPower": 49,
    }


def test_unmapped_registers_are_dropped():
    """Local registers without a cloud equivalent are silently ignored."""
    # t592 (head real SOC), t49 (daily generation), t586 (heater bitfield)
    # all have no corresponding cloud entity key today.
    result = translate_to_device_keys({"t592": 75, "t49": 1.234, "t586": 5})
    assert result == {}


def test_empty_input_returns_empty():
    """A push with no data shouldn't synthesize keys."""
    assert translate_to_device_keys({}) == {}
