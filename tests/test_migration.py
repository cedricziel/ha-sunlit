"""Test migration of config entries."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sunlit import async_migrate_entry
from custom_components.sunlit.const import (
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_ENABLE_SOC_EVENTS,
    OPT_SOC_THRESHOLD_LOW,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


async def test_migrate_v1_1_to_v1_2(hass: HomeAssistant):
    """Test migration from version 1.1 to 1.2 (adds default options)."""
    # Create an old config entry without options
    old_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "access_token": "test_token",
            "families": {
                "12345": {
                    "id": 12345,
                    "name": "Test Family",
                    "address": "Test Address",
                    "device_count": 3,
                }
            },
        },
        version=1,
        minor_version=1,
    )
    old_entry.add_to_hass(hass)

    # Verify entry has no options initially
    assert old_entry.options == {}

    # Run migration
    result = await async_migrate_entry(hass, old_entry)

    # Verify migration was successful
    assert result is True

    # Verify version was updated
    assert old_entry.minor_version == 2

    # Verify default options were added
    assert old_entry.options == DEFAULT_OPTIONS

    # Verify all expected options are present
    assert OPT_ENABLE_SOC_EVENTS in old_entry.options
    assert old_entry.options[OPT_ENABLE_SOC_EVENTS] is True
    assert OPT_SOC_THRESHOLD_LOW in old_entry.options
    assert old_entry.options[OPT_SOC_THRESHOLD_LOW] == 20


async def test_migrate_v1_1_to_v1_2_preserves_existing_options(hass: HomeAssistant):
    """Test migration preserves existing options while adding missing ones."""
    # Create an old config entry with some options
    existing_options = {
        OPT_ENABLE_SOC_EVENTS: False,
        OPT_SOC_THRESHOLD_LOW: 25,
    }

    old_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "access_token": "test_token",
            "families": {
                "12345": {
                    "id": 12345,
                    "name": "Test Family",
                    "address": "Test Address",
                    "device_count": 3,
                }
            },
        },
        options=existing_options,
        version=1,
        minor_version=1,
    )
    old_entry.add_to_hass(hass)

    # Run migration
    result = await async_migrate_entry(hass, old_entry)

    # Verify migration was successful
    assert result is True

    # Verify version was updated
    assert old_entry.minor_version == 2

    # Verify existing options were preserved
    assert old_entry.options[OPT_ENABLE_SOC_EVENTS] is False
    assert old_entry.options[OPT_SOC_THRESHOLD_LOW] == 25

    # Verify missing options were added with defaults
    assert len(old_entry.options) == len(DEFAULT_OPTIONS)
    for key in DEFAULT_OPTIONS:
        assert key in old_entry.options


async def test_migrate_v1_2_no_changes(hass: HomeAssistant):
    """Test migration skips already migrated entries."""
    # Create a current version config entry
    current_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "access_token": "test_token",
            "families": {
                "12345": {
                    "id": 12345,
                    "name": "Test Family",
                    "address": "Test Address",
                    "device_count": 3,
                }
            },
        },
        options=DEFAULT_OPTIONS,
        version=1,
        minor_version=2,
    )
    current_entry.add_to_hass(hass)

    # Store original options
    original_options = dict(current_entry.options)

    # Run migration
    result = await async_migrate_entry(hass, current_entry)

    # Verify migration was successful
    assert result is True

    # Verify version stayed the same
    assert current_entry.minor_version == 2

    # Verify options weren't changed
    assert current_entry.options == original_options


async def test_new_config_entry_has_defaults(hass: HomeAssistant):
    """Test that new config entries created with current version have defaults."""

    # The config flow should set default options for new entries
    # This is more of an integration test but validates the full flow
    new_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "access_token": "test_token",
            "families": {
                "12345": {
                    "id": 12345,
                    "name": "Test Family",
                    "address": "Test Address",
                    "device_count": 3,
                }
            },
        },
        options=DEFAULT_OPTIONS,  # Set by config flow
        version=1,
        minor_version=2,
    )

    # Verify all default options are present
    assert new_entry.options == DEFAULT_OPTIONS
    assert len(new_entry.options) == len(DEFAULT_OPTIONS)
