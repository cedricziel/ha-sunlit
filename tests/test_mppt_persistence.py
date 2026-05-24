"""MPPT energy persistence across restarts (issue #72 follow-up).

Driven by the sanitized real battery payload in tests/fixtures/api/.
"""

from unittest.mock import MagicMock

from custom_components.sunlit.coordinators.mppt import SunlitMpptEnergyCoordinator

from tests.fixtures import load_api_fixture

BATTERY_DEVICE_ID = "10003"


def _battery_device_coordinator() -> MagicMock:
    """A device-coordinator stub serving the real battery statistics."""
    stats = load_api_fixture("device_statistics_ENERGY_STORAGE_BATTERY_10003")
    device_data = {**stats, "deviceType": "ENERGY_STORAGE_BATTERY", "module_count": 3}
    dev = MagicMock()
    dev.data = {"devices": {BATTERY_DEVICE_ID: device_data}}
    dev.get_battery_module_count.return_value = 3
    return dev


async def test_mppt_energy_persists_across_restart(hass, hass_storage):
    """Accumulated energy is restored by a fresh coordinator (simulated restart)."""
    dev = _battery_device_coordinator()

    # First lifecycle: accumulate energy over a simulated hour.
    coord_a = SunlitMpptEnergyCoordinator(hass, dev, "10001", "Test Family")
    await coord_a._async_update_data()
    for key in list(coord_a.last_mppt_update):
        coord_a.last_mppt_update[key] -= 3600
    await coord_a._async_update_data()
    accumulated = coord_a.mppt_energy["10003_battery1Mppt1Energy"]
    assert accumulated > 0

    # Flush the debounced save.
    await coord_a._store.async_save(coord_a._data_to_store())

    # Second lifecycle (restart): a fresh coordinator restores the totals.
    coord_b = SunlitMpptEnergyCoordinator(hass, dev, "10001", "Test Family")
    assert coord_b.mppt_energy == {}
    await coord_b._async_update_data()  # triggers restore on first run
    assert coord_b.mppt_energy["10003_battery1Mppt1Energy"] == accumulated


async def test_no_energy_spike_after_restore(hass, hass_storage):
    """The first tick after a restart restores the value without a phantom spike.

    Restoring the per-channel timestamp would make the first update integrate
    over the entire offline period; we restore only the energy totals, so the
    value must come back unchanged.
    """
    coordinator = SunlitMpptEnergyCoordinator(
        hass, _battery_device_coordinator(), "10001", "Test Family"
    )
    # Pre-seed persisted state as if a previous run had accumulated 5 kWh.
    await coordinator._store.async_save(
        {"mppt_energy": {"10003_battery1Mppt1Energy": 5.0}}
    )

    result = await coordinator._async_update_data()

    energy = result["mppt_energy"][BATTERY_DEVICE_ID]
    assert energy["battery1Mppt1Energy"] == 5.0  # restored, no spike
