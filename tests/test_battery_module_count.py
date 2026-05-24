"""Battery module-count derivation (issue #73).

`deviceCount` counts the BK215 head unit, so it over-reports by one and used
to spawn a phantom empty B215 module. The count is now derived from the
populated `battery{N}DeviceModel` slots in the statistics.
"""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator

from tests.fixtures import load_api_fixture

BATTERY_DEVICE_ID = "10003"


def test_count_battery_modules_helper():
    """The helper counts populated DeviceModel slots, not deviceCount or SOC."""
    coordinator = object.__new__(SunlitDeviceCoordinator)

    # Two real extension modules.
    assert (
        coordinator._count_battery_modules(
            {"battery1DeviceModel": "B_215", "battery2DeviceModel": "B_215"}
        )
        == 2
    )
    # Head-only battery (BK215): no extension modules.
    assert coordinator._count_battery_modules({"batterySoc": 100}) == 0
    # A 0%-charged module must still count (DeviceModel is the signal, not SOC).
    assert (
        coordinator._count_battery_modules(
            {"battery1DeviceModel": "B_215", "battery1Soc": 0}
        )
        == 1
    )


async def test_module_count_excludes_head_unit(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """deviceCount=3 (head + 2 modules) must yield 2 modules, not 3 (#73)."""
    device_list = load_api_fixture("device_list_family_10001")
    stats = load_api_fixture("device_statistics_ENERGY_STORAGE_BATTERY_10003")

    # Sanity: the captured fixture really has the over-counting deviceCount.
    battery_entry = next(
        d for d in device_list if d["deviceType"] == "ENERGY_STORAGE_BATTERY"
    )
    assert battery_entry["deviceCount"] == 3

    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = device_list
    api_client.fetch_device_statistics.return_value = stats

    coordinator = SunlitDeviceCoordinator(hass, api_client, "10001", "Test Family")
    data = await coordinator._async_update_data()
    coordinator.data = data  # _async_update_data() doesn't set self.data directly

    battery = data["devices"][BATTERY_DEVICE_ID]
    assert battery["module_count"] == 2  # head excluded
    assert coordinator.get_battery_module_count(BATTERY_DEVICE_ID) == 2
    # No phantom slot-3 data is copied through.
    assert "battery3Mppt1InPower" not in battery


async def test_offline_battery_module_count_fallback(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Offline battery: no statistics, fall back to deviceCount minus the head."""
    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = [
        {
            "deviceId": 99,
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "status": "Offline",
            "deviceCount": 3,
        }
    ]

    coordinator = SunlitDeviceCoordinator(hass, api_client, "10001", "Test Family")
    data = await coordinator._async_update_data()

    battery = data["devices"]["99"]
    assert battery["module_count"] == 2  # 3 (stack) - 1 (head)
    # Statistics are not fetched for an offline device.
    api_client.fetch_device_statistics.assert_not_called()
