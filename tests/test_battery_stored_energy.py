"""Tests for battery stored-energy derivation (issue #190)."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.sunlit.const import BATTERY_MODULE_CAPACITY_KWH
from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator

CAP = BATTERY_MODULE_CAPACITY_KWH


def _battery_device_list():
    return [
        {
            "deviceId": "battery_001",
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "status": "Online",
            "batteryLevel": 80,
            "deviceCount": 3,
        }
    ]


async def _run(hass, stats):
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = _battery_device_list()
    api_client.fetch_device_statistics.return_value = stats
    api_client.fetch_device_details.return_value = {}
    coordinator = SunlitDeviceCoordinator(hass, api_client, "34038", "Test Family")
    data = await coordinator._async_update_data()
    return data["devices"]["battery_001"]


async def test_stored_energy_single_module(
    hass: HomeAssistant, enable_custom_integrations
):
    """One module: pack = head + 1 module = 2 x 2.15 kWh."""
    battery = await _run(
        hass,
        {
            "batterySoc": 50,
            "battery1DeviceModel": "B_215",
            "battery1Soc": 50,
        },
    )

    assert battery["stored_energy"] == round(50 / 100 * (1 + 1) * CAP, 3)
    assert battery["battery1StoredEnergy"] == round(50 / 100 * CAP, 3)
    # No phantom second module.
    assert "battery2StoredEnergy" not in battery


async def test_stored_energy_multi_module(
    hass: HomeAssistant, enable_custom_integrations
):
    """Two modules: pack = head + 2 modules = 3 x 2.15 kWh; per-module independent."""
    battery = await _run(
        hass,
        {
            "batterySoc": 80,
            "battery1DeviceModel": "B_215",
            "battery1Soc": 70,
            "battery2DeviceModel": "B_215",
            "battery2Soc": 90,
        },
    )

    assert battery["stored_energy"] == round(80 / 100 * (1 + 2) * CAP, 3)
    assert battery["battery1StoredEnergy"] == round(70 / 100 * CAP, 3)
    assert battery["battery2StoredEnergy"] == round(90 / 100 * CAP, 3)


async def test_stored_energy_absent_without_soc(
    hass: HomeAssistant, enable_custom_integrations
):
    """No system SOC -> no stored_energy key (avoid a misleading 0)."""
    battery = await _run(
        hass,
        {
            "battery1DeviceModel": "B_215",
            # batterySoc and battery1Soc absent
        },
    )

    assert "stored_energy" not in battery
    assert "battery1StoredEnergy" not in battery
