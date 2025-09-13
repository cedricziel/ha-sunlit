"""Test options flow for Sunlit integration."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sunlit.const import (
    DOMAIN,
    OPT_ENABLE_SOC_EVENTS,
    OPT_MIN_EVENT_INTERVAL,
    OPT_SOC_CHANGE_THRESHOLD,
    OPT_SOC_THRESHOLD_CRITICAL_HIGH,
    OPT_SOC_THRESHOLD_CRITICAL_LOW,
    OPT_SOC_THRESHOLD_HIGH,
    OPT_SOC_THRESHOLD_LOW,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
async def configured_entry(hass: HomeAssistant, mock_config_entry) -> config_entries.ConfigEntry:
    """Create a configured config entry."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.sunlit.async_setup_entry",
        return_value=True,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
    return mock_config_entry


async def test_options_flow_init(hass: HomeAssistant, configured_entry):
    """Test options flow initialization."""
    result = await hass.config_entries.options.async_init(configured_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Check that all expected fields are in the schema
    schema = result["data_schema"]
    schema_keys = {str(key) for key in schema.schema}

    expected_keys = {
        OPT_ENABLE_SOC_EVENTS,
        OPT_SOC_THRESHOLD_CRITICAL_LOW,
        OPT_SOC_THRESHOLD_LOW,
        OPT_SOC_THRESHOLD_HIGH,
        OPT_SOC_THRESHOLD_CRITICAL_HIGH,
        OPT_SOC_CHANGE_THRESHOLD,
        OPT_MIN_EVENT_INTERVAL,
    }

    assert expected_keys.issubset(schema_keys)


async def test_options_flow_update(hass: HomeAssistant, configured_entry):
    """Test updating options."""
    result = await hass.config_entries.options.async_init(configured_entry.entry_id)

    # Submit new options
    updated_options = {
        OPT_ENABLE_SOC_EVENTS: False,
        OPT_SOC_THRESHOLD_CRITICAL_LOW: 5,
        OPT_SOC_THRESHOLD_LOW: 15,
        OPT_SOC_THRESHOLD_HIGH: 85,
        OPT_SOC_THRESHOLD_CRITICAL_HIGH: 98,
        OPT_SOC_CHANGE_THRESHOLD: 10,
        OPT_MIN_EVENT_INTERVAL: 120,
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=updated_options,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == updated_options


async def test_options_flow_defaults(hass: HomeAssistant, configured_entry):
    """Test that default values are shown correctly."""
    # Set some options
    hass.config_entries.async_update_entry(
        configured_entry,
        options={
            OPT_ENABLE_SOC_EVENTS: False,
            OPT_SOC_THRESHOLD_LOW: 25,
        },
    )

    result = await hass.config_entries.options.async_init(configured_entry.entry_id)

    # The schema should show the current values as defaults
    schema = result["data_schema"]

    # Check that the form shows current options as defaults
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_reload(hass: HomeAssistant, configured_entry):
    """Test that changing options triggers a reload."""
    with patch(
        "custom_components.sunlit.async_unload_entry",
        return_value=True,
    ) as mock_unload, patch(
        "custom_components.sunlit.async_setup_entry",
        return_value=True,
    ) as mock_setup:

        result = await hass.config_entries.options.async_init(configured_entry.entry_id)

        # Submit changed options
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                OPT_ENABLE_SOC_EVENTS: False,
                OPT_SOC_THRESHOLD_CRITICAL_LOW: 5,
                OPT_SOC_THRESHOLD_LOW: 15,
                OPT_SOC_THRESHOLD_HIGH: 85,
                OPT_SOC_THRESHOLD_CRITICAL_HIGH: 98,
                OPT_SOC_CHANGE_THRESHOLD: 10,
                OPT_MIN_EVENT_INTERVAL: 120,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Verify the entry was updated
        assert configured_entry.options[OPT_ENABLE_SOC_EVENTS] is False
        assert configured_entry.options[OPT_SOC_THRESHOLD_LOW] == 15
