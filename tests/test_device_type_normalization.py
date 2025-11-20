"""Tests for device type normalization."""

from custom_components.sunlit.const import (
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_INVERTER_SOLAR,
    DEVICE_TYPE_METER,
    DEVICE_TYPE_METER_PRO,
)
from custom_components.sunlit.entities.base import normalize_device_type


def test_normalize_shelly_3em_meter():
    """SHELLY_3EM_METER should normalize to 'meter'."""
    result = normalize_device_type(DEVICE_TYPE_METER)
    assert result == "meter"


def test_normalize_shelly_pro3em_meter():
    """SHELLY_PRO3EM_METER should normalize to 'meter'."""
    result = normalize_device_type(DEVICE_TYPE_METER_PRO)
    assert result == "meter"


def test_normalize_yuneng_micro_inverter():
    """YUNENG_MICRO_INVERTER should normalize to 'inverter'."""
    result = normalize_device_type(DEVICE_TYPE_INVERTER)
    assert result == "inverter"


def test_normalize_solar_micro_inverter():
    """SOLAR_MICRO_INVERTER should normalize to 'inverter'."""
    result = normalize_device_type(DEVICE_TYPE_INVERTER_SOLAR)
    assert result == "inverter"


def test_normalize_energy_storage_battery():
    """ENERGY_STORAGE_BATTERY should normalize to 'battery'."""
    result = normalize_device_type(DEVICE_TYPE_BATTERY)
    assert result == "battery"


def test_normalize_unknown_type_fallback():
    """Unknown types should use fallback logic (lowercase, no underscores)."""
    # Test with a made-up device type
    result = normalize_device_type("CUSTOM_DEVICE_TYPE")
    assert result == "customdevicetype"

    # Test with another unknown type
    result = normalize_device_type("SOME_OTHER_METER")
    assert result == "someothermeter"


def test_normalize_preserves_unique_id_stability():
    """Both meter variants should produce same normalized type for unique_id."""
    meter_normal = normalize_device_type(DEVICE_TYPE_METER)
    meter_pro = normalize_device_type(DEVICE_TYPE_METER_PRO)
    assert meter_normal == meter_pro == "meter"


def test_normalize_preserves_inverter_unique_id_stability():
    """Both inverter variants should produce same normalized type for unique_id."""
    inverter_yuneng = normalize_device_type(DEVICE_TYPE_INVERTER)
    inverter_solar = normalize_device_type(DEVICE_TYPE_INVERTER_SOLAR)
    assert inverter_yuneng == inverter_solar == "inverter"
