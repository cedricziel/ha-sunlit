"""Family-level Total MPPT Energy sensor (issue #72 follow-up).

The MPPT coordinator computes a family rollup (``total_mppt_energy``) but it
was never surfaced: the merge in sensor.py added device-id-keyed entries to
``family_data`` instead of the rollup, so no family sensor was created.
"""

from unittest.mock import MagicMock, Mock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.sunlit.const import DOMAIN, FAMILY_SENSORS
from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator
from custom_components.sunlit.coordinators.family import SunlitFamilyCoordinator
from custom_components.sunlit.coordinators.mppt import SunlitMpptEnergyCoordinator
from custom_components.sunlit.entities.helpers import (
    get_device_class_for_sensor,
    get_state_class_for_sensor,
    get_unit_for_sensor,
)
from custom_components.sunlit.sensor import async_setup_entry


def test_total_mppt_energy_registered_and_classified():
    """The rollup is registered and classified as energy / total_increasing / kWh."""
    assert "total_mppt_energy" in FAMILY_SENSORS
    assert get_device_class_for_sensor("total_mppt_energy") == SensorDeviceClass.ENERGY
    assert (
        get_state_class_for_sensor("total_mppt_energy")
        == SensorStateClass.TOTAL_INCREASING
    )
    assert get_unit_for_sensor("total_mppt_energy") == UnitOfEnergy.KILO_WATT_HOUR


async def test_family_total_mppt_energy_sensor_created(
    hass: HomeAssistant,
    mock_config_entry,
):
    """async_setup_entry creates the family rollup sensor bound to the MPPT coordinator."""
    mock_config_entry.add_to_hass(hass)

    family_coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    family_coordinator.family_id = "10001"
    family_coordinator.family_name = "Test Family"
    family_coordinator.devices = {}
    family_coordinator.data = {"family": {"device_count": 1}}

    device_coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    device_coordinator.family_id = "10001"
    device_coordinator.family_name = "Test Family"
    device_coordinator.devices = {}
    device_coordinator.data = {"devices": {}, "aggregates": {}}

    mppt_coordinator = MagicMock(spec=SunlitMpptEnergyCoordinator)
    mppt_coordinator.family_id = "10001"
    mppt_coordinator.family_name = "Test Family"
    mppt_coordinator.last_update_success = True
    mppt_coordinator.data = {
        "mppt_energy": {"10003": {"battery1Mppt1Energy": 0.5}},
        "total_mppt_energy": 2.5,
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "10001": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": mppt_coordinator,
            }
        }
    }

    async_add_entities = Mock()
    await async_setup_entry(hass, mock_config_entry, async_add_entities)

    sensors = async_add_entities.call_args[0][0]
    by_key = {
        s.entity_description.key: s
        for s in sensors
        if hasattr(s, "entity_description")
    }

    assert "total_mppt_energy" in by_key, "family Total MPPT Energy sensor not created"
    sensor = by_key["total_mppt_energy"]
    # Must be bound to the MPPT coordinator (so HA keeps it polling, too).
    assert sensor.coordinator is mppt_coordinator
    assert sensor.entity_description.device_class == SensorDeviceClass.ENERGY
    # Reads the top-level rollup, not the nested per-device dict.
    assert sensor.native_value == 2.5
    assert sensor.available is True
