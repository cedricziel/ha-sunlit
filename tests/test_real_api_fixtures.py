"""Tests driven by sanitized real API responses (tests/fixtures/api/).

Captured with scripts/capture_fixtures.py. These guard against API shape
drift (the class of bug behind #95) and pin the MPPT energy accumulation
behavior behind #72.
"""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.core import HomeAssistant

from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator
from custom_components.sunlit.coordinators.mppt import SunlitMpptEnergyCoordinator
from custom_components.sunlit.entities.battery_module_sensor import (
    SunlitBatteryModuleSensor,
)

from tests.fixtures import load_api_fixture

BATTERY_STATS = "device_statistics_ENERGY_STORAGE_BATTERY_10003"
BATTERY_DEVICE_ID = "10003"


def test_real_battery_stats_expose_expected_mppt_fields():
    """Contract: the live battery payload still contains the fields our code reads.

    If the API renames these, the coordinators silently produce nothing; this
    fails loudly instead.
    """
    stats = load_api_fixture(BATTERY_STATS)

    # Head-unit MPPTs consumed by _calculate_main_mppt_energy.
    for key in ("batteryMppt1InPower", "batteryMppt2InPower"):
        assert key in stats, f"missing {key}"

    # Module MPPTs consumed by _calculate_module_mppt_energy.
    for key in ("battery1Mppt1InPower", "battery2Mppt1InPower"):
        assert key in stats, f"missing {key}"
        assert stats[key] is not None and stats[key] > 0


async def test_device_coordinator_processes_real_battery(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """The device coordinator derives the expected keys from the real payload."""
    device_list = load_api_fixture("device_list_family_10001")
    stats = load_api_fixture(BATTERY_STATS)

    api_client = AsyncMock()
    api_client.fetch_device_list.return_value = device_list
    api_client.fetch_device_statistics.return_value = stats

    coordinator = SunlitDeviceCoordinator(hass, api_client, "10001", "Test Family")
    data = await coordinator._async_update_data()

    battery = data["devices"][BATTERY_DEVICE_ID]
    assert battery["deviceType"] == "ENERGY_STORAGE_BATTERY"
    assert battery["module_count"] == 3  # from deviceCount in the device list
    assert battery["batterySoc"] == 100.0
    assert battery["battery1Mppt1InPower"] == 12.9  # module MPPT power copied through
    assert battery["battery2Mppt1InPower"] == 35.2


async def test_mppt_energy_accumulates_for_modules(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Regression for #72: module MPPT Total Energy must accumulate, not stay 0.

    Uses the real battery statistics. After a simulated hour with the modules
    producing power, every MPPT channel (head unit + modules) must report
    energy > 0.
    """
    stats = load_api_fixture(BATTERY_STATS)
    device_data = {**stats, "deviceType": "ENERGY_STORAGE_BATTERY", "module_count": 3}

    device_coordinator = MagicMock()
    device_coordinator.data = {"devices": {BATTERY_DEVICE_ID: device_data}}
    device_coordinator.get_battery_module_count.return_value = 3

    coordinator = SunlitMpptEnergyCoordinator(
        hass, device_coordinator, "10001", "Test Family"
    )

    # First update initializes accumulators to 0.
    first = await coordinator._async_update_data()
    initial = first["mppt_energy"][BATTERY_DEVICE_ID]
    assert initial["battery1Mppt1Energy"] == 0
    assert initial["battery2Mppt1Energy"] == 0

    # Simulate an hour elapsing on every channel.
    for key in list(coordinator.last_mppt_update):
        coordinator.last_mppt_update[key] -= 3600

    second = await coordinator._async_update_data()
    energy = second["mppt_energy"][BATTERY_DEVICE_ID]

    # Modules 1 & 2 produce power, so energy must be > 0 (the #72 bug showed 0).
    assert energy["battery1Mppt1Energy"] > 0
    assert energy["battery2Mppt1Energy"] > 0
    # Head-unit MPPTs accumulate too.
    assert energy["batteryMppt1Energy"] > 0
    assert energy["batteryMppt2Energy"] > 0
    assert second["total_mppt_energy"] > 0


async def test_mppt_sensor_subscribes_to_mppt_coordinator(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Regression for #72: the MPPT coordinator must gain a listener.

    HomeAssistant only schedules a coordinator's periodic refresh while it has
    at least one listener. The MPPT-energy sensors' primary coordinator is the
    device coordinator, so unless they explicitly subscribe to the MPPT
    coordinator it never polls past startup and energy freezes at 0.
    """
    api_client = AsyncMock()
    device_coordinator = SunlitDeviceCoordinator(
        hass, api_client, "10001", "Test Family"
    )
    mppt_coordinator = SunlitMpptEnergyCoordinator(
        hass, device_coordinator, "10001", "Test Family"
    )

    sensor = SunlitBatteryModuleSensor(
        coordinator=device_coordinator,
        description=SensorEntityDescription(
            key="battery1Mppt1Energy", name="MPPT Total Energy"
        ),
        entry_id="entry",
        family_id="10001",
        family_name="Test Family",
        device_id=BATTERY_DEVICE_ID,
        device_info_data={
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "deviceSn": "SN1001",
        },
        module_number=1,
        mppt_coordinator=mppt_coordinator,
    )
    sensor.hass = hass

    # Nothing is subscribed to the MPPT coordinator yet -> it would never poll.
    assert len(mppt_coordinator._listeners) == 0

    await sensor.async_added_to_hass()

    # The fix subscribes the sensor, so HA will keep the coordinator scheduled.
    assert len(mppt_coordinator._listeners) == 1

    # Adding the listener scheduled a real refresh timer; cancel it so the test
    # leaves no lingering timers.
    await mppt_coordinator.async_shutdown()
    await device_coordinator.async_shutdown()
