"""Test the Sunlit config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sunlit import DOMAIN
from custom_components.sunlit.api_client import SunlitAuthError, SunlitConnectionError
from custom_components.sunlit.const import CONF_ACCESS_TOKEN, CONF_FAMILIES


async def test_form_user_init(hass: HomeAssistant, enable_custom_integrations):
    """Test we get the form on user init."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}
    assert result["step_id"] == "user"


async def test_form_authentication_success(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_aioresponse,
    api_base_url,
    families_response,
):
    """Test successful authentication flow."""
    # Mock the login and family list API calls
    mock_aioresponse.post(
        f"{api_base_url}/login",
        payload={"access_token": "test_api_key_123"},
    )
    mock_aioresponse.get(
        f"{api_base_url}/family/list",
        payload=families_response,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Submit email and password
    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(return_value={"access_token": "test_api_key_123"})
        mock_client.get_families = AsyncMock(return_value=families_response["content"])

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "select_families"
        assert result2["errors"] == {}


async def test_form_family_selection(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_aioresponse,
    api_base_url,
    families_response,
):
    """Test family selection step."""
    mock_aioresponse.post(
        f"{api_base_url}/login",
        payload={"access_token": "test_api_key_123"},
    )
    mock_aioresponse.get(
        f"{api_base_url}/family/list",
        payload=families_response,
    )

    # Start flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Submit email and password
    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(return_value={"access_token": "test_api_key_123"})
        mock_client.get_families = AsyncMock(return_value=families_response["content"])

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        # Select families
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {"families": ["34038", "40488"]},
        )

        assert result3["type"] == FlowResultType.CREATE_ENTRY
        assert result3["title"] == "Sunlit Solar"
        assert result3["data"]["access_token"] == "test_api_key_123"
        assert "families" in result3["data"]
        assert len(result3["data"]["families"]) == 2


async def test_form_authentication_error(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_aioresponse,
    api_base_url,
    api_error_response,
):
    """Test authentication error handling."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(side_effect=SunlitAuthError("Authentication failed"))

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "invalid_password"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "user"
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_connection_error(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test connection error handling."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(side_effect=SunlitConnectionError("Cannot connect"))

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "user"
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_no_families_selected(
    hass: HomeAssistant,
    enable_custom_integrations,
    families_response,
):
    """Test error when no families are selected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(return_value={"access_token": "test_api_key_123"})
        mock_client.get_families = AsyncMock(return_value=families_response["content"])

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        # Try to submit without selecting families
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {"families": []},
        )

        assert result3["type"] == FlowResultType.FORM
        assert result3["step_id"] == "select_families"
        assert result3["errors"] == {"base": "no_selection"}


async def test_form_single_family_auto_select(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """Test automatic selection when only one family exists."""
    single_family_response = {
        "code": 0,
        "message": {"DE": "Ok"},
        "content": [
            {
                "id": 34038,
                "name": "Garage",
                "address": "Halver",
                "deviceCount": 4,
                "countryCode": "DE",
            }
        ],
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login.return_value = {"access_token": "test_api_key_123"}
        mock_client.get_families.return_value = single_family_response["content"]

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        # Should skip family selection and create entry directly
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Sunlit Solar"
        assert result2["data"]["access_token"] == "test_api_key_123"
        assert "families" in result2["data"]
        assert len(result2["data"]["families"]) == 1


async def test_form_duplicate_entry(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_config_entry,
):
    """Test duplicate entry prevention."""
    # Add existing entry
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
