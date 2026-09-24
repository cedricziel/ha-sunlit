"""Entities must appear when their data does, not only at setup time.

Platform setup runs once. A device that is offline while Home Assistant starts
contributes no keys to the coordinator snapshot, so anything derived from those
keys used to be skipped forever — the entity stayed in the registry as
``restored``/unavailable until the config entry was reloaded by hand, with
nothing logged to explain it.
"""

from unittest.mock import MagicMock, Mock

from homeassistant.core import HomeAssistant

from custom_components.sunlit.binary_sensor import (
    async_setup_entry as binary_sensor_setup_entry,
)
from custom_components.sunlit.const import DOMAIN
from custom_components.sunlit.coordinators.device import SunlitDeviceCoordinator
from custom_components.sunlit.coordinators.family import SunlitFamilyCoordinator
from custom_components.sunlit.sensor import async_setup_entry as sensor_setup_entry
from custom_components.sunlit.switch import async_setup_entry as switch_setup_entry


def _family_coordinator(family_data):
    coordinator = MagicMock(spec=SunlitFamilyCoordinator)
    coordinator.family_id = "10001"
    coordinator.family_name = "Test Family"
    coordinator.devices = {}
    coordinator.data = {"family": family_data}
    return coordinator


def _device_coordinator(devices=None, device_info=None):
    coordinator = MagicMock(spec=SunlitDeviceCoordinator)
    coordinator.family_id = "10001"
    coordinator.family_name = "Test Family"
    coordinator.devices = device_info or {}
    coordinator.data = {"devices": devices or {}, "aggregates": {}}
    coordinator.get_battery_module_count.return_value = 0
    return coordinator


def _install(hass, entry, family_coordinator, device_coordinator):
    hass.data[DOMAIN] = {
        entry.entry_id: {
            "10001": {
                "family": family_coordinator,
                "device": device_coordinator,
                "strategy": None,
                "mppt": None,
            }
        }
    }


def _added_keys(async_add_entities):
    """Collect entity_description keys across every add_entities call."""
    keys = []
    for call in async_add_entities.call_args_list:
        for entity in call[0][0]:
            if hasattr(entity, "entity_description"):
                keys.append(entity.entity_description.key)
    return keys


async def test_family_sensor_created_when_key_appears_later(
    hass: HomeAssistant,
    mock_config_entry,
):
    """A key missing at setup still gets its sensor on a later update.

    Mirrors a battery that is offline when HA starts: the cloud omits
    ``batteryLevel``/``batteryCount``, so ``total_stored_energy`` is absent
    from the first snapshot.
    """
    mock_config_entry.add_to_hass(hass)

    family_coordinator = _family_coordinator({"device_count": 1})
    device_coordinator = _device_coordinator()
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await sensor_setup_entry(hass, mock_config_entry, async_add_entities)

    assert "total_stored_energy" not in _added_keys(async_add_entities)

    # The battery comes online and the family coordinator publishes the key.
    family_coordinator.data["family"]["total_stored_energy"] = 7.138
    listener = family_coordinator.async_add_listener.call_args[0][0]
    listener()

    assert "total_stored_energy" in _added_keys(async_add_entities)


async def test_family_sensors_are_not_created_twice(
    hass: HomeAssistant,
    mock_config_entry,
):
    """Repeated coordinator updates must not duplicate existing entities."""
    mock_config_entry.add_to_hass(hass)

    family_coordinator = _family_coordinator({"device_count": 1})
    device_coordinator = _device_coordinator()
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await sensor_setup_entry(hass, mock_config_entry, async_add_entities)

    calls_after_setup = async_add_entities.call_count
    listener = family_coordinator.async_add_listener.call_args[0][0]
    listener()
    listener()

    keys = _added_keys(async_add_entities)
    assert async_add_entities.call_count == calls_after_setup
    assert len(keys) == len(set(keys)), "an entity was created more than once"


async def test_family_payload_is_not_polluted_by_merges(
    hass: HomeAssistant,
    mock_config_entry,
):
    """Merging strategy/aggregate keys must not write into the live payload.

    The merged dict only decides which keys deserve an entity; each sensor
    reads its value from its own coordinator. Since the builder now runs on
    every update, writing back would keep injecting foreign keys.
    """
    mock_config_entry.add_to_hass(hass)

    family_coordinator = _family_coordinator({"device_count": 1})
    device_coordinator = _device_coordinator()
    device_coordinator.data["aggregates"] = {"total_solar_power": 931.0}
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await sensor_setup_entry(hass, mock_config_entry, async_add_entities)

    assert "total_solar_power" in _added_keys(async_add_entities)
    assert family_coordinator.data["family"] == {"device_count": 1}


async def test_builder_error_does_not_escape_to_the_coordinator(
    hass: HomeAssistant,
    mock_config_entry,
):
    """A failing build must not break the coordinator's listener dispatch."""
    mock_config_entry.add_to_hass(hass)

    family_coordinator = _family_coordinator({"device_count": 1})
    device_coordinator = _device_coordinator()
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await sensor_setup_entry(hass, mock_config_entry, async_add_entities)

    # A malformed payload: the builder iterates devices and will raise.
    device_coordinator.data["devices"] = "not-a-dict"
    listener = device_coordinator.async_add_listener.call_args[0][0]

    listener()  # must swallow the error rather than propagate it


async def test_device_sensors_created_when_device_appears_later(
    hass: HomeAssistant,
    mock_config_entry,
):
    """A device absent from the first device list still gets its sensors."""
    mock_config_entry.add_to_hass(hass)

    family_coordinator = _family_coordinator({"device_count": 0})
    device_coordinator = _device_coordinator()
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await sensor_setup_entry(hass, mock_config_entry, async_add_entities)

    assert "battery_level" not in _added_keys(async_add_entities)

    device_info = {
        "deviceType": "ENERGY_STORAGE_BATTERY",
        "deviceSn": "dcbdccc00235",
    }
    device_coordinator.devices = {"battery_001": device_info}
    device_coordinator.data["devices"] = {"battery_001": {"battery_level": 83.0}}
    listener = device_coordinator.async_add_listener.call_args[0][0]
    listener()

    assert "battery_level" in _added_keys(async_add_entities)


async def test_local_mode_switch_created_when_support_appears_later(
    hass: HomeAssistant,
    mock_config_entry,
):
    """The local-mode switch appears once the battery advertises support."""
    mock_config_entry.add_to_hass(hass)

    device_info = {
        "deviceType": "ENERGY_STORAGE_BATTERY",
        "deviceSn": "dcbdccc00235",
    }
    family_coordinator = _family_coordinator({"device_count": 1})
    device_coordinator = _device_coordinator(
        devices={"battery_001": {}},
        device_info={"battery_001": device_info},
    )
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await switch_setup_entry(hass, mock_config_entry, async_add_entities)

    assert async_add_entities.call_count == 0

    device_coordinator.data["devices"]["battery_001"]["support_local_mode"] = True
    listener = device_coordinator.async_add_listener.call_args[0][0]
    listener()

    switches = async_add_entities.call_args[0][0]
    assert len(switches) == 1


async def test_family_binary_sensor_created_when_key_appears_later(
    hass: HomeAssistant,
    mock_config_entry,
):
    """Binary sensors follow the same rule as sensors."""
    mock_config_entry.add_to_hass(hass)

    family_coordinator = _family_coordinator({"device_count": 1})
    device_coordinator = _device_coordinator()
    _install(hass, mock_config_entry, family_coordinator, device_coordinator)

    async_add_entities = Mock()
    await binary_sensor_setup_entry(hass, mock_config_entry, async_add_entities)

    assert "has_fault" not in _added_keys(async_add_entities)

    family_coordinator.data["family"]["has_fault"] = False
    listener = family_coordinator.async_add_listener.call_args[0][0]
    listener()

    assert "has_fault" in _added_keys(async_add_entities)
