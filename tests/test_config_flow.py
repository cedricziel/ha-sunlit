"""Test the Sunlit config flow."""

from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.sunlit import DOMAIN
from custom_components.sunlit.api_client import SunlitAuthError, SunlitConnectionError
from custom_components.sunlit.const import CONF_ACCESS_TOKEN, CONF_FAMILIES


def _zeroconf_discovery_info(serial: str = "HP-BK215-001") -> ZeroconfServiceInfo:
    """Build a ZeroconfServiceInfo mimicking a BK215 mDNS advertisement."""
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.168.1.50"),
        ip_addresses=[ip_address("192.168.1.50")],
        port=80,
        hostname="hp-bk215-001.local.",
        type="_http._tcp.local.",
        name="hp-bk215-001._http._tcp.local.",
        properties={
            "id": serial,
            "port": "80",
            "fw_ver": "1.2.3",
            "model": "BK215",
        },
    )


async def test_form_user_init(hass: HomeAssistant):
    """Test we get the form on user init."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}
    assert result["step_id"] == "user"


async def test_form_authentication_success(
    hass: HomeAssistant,
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
        mock_client.fetch_families = AsyncMock(
            return_value=families_response["content"]
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "select_families"
        assert result2["errors"] == {}


async def test_form_family_selection(
    hass: HomeAssistant,
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
        mock_client.fetch_families = AsyncMock(
            return_value=families_response["content"]
        )

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
        assert result3["title"] == "Sunlit (Garage, Test)"
        assert result3["data"]["access_token"] == "test_api_key_123"
        assert "families" in result3["data"]
        assert len(result3["data"]["families"]) == 2


async def test_form_authentication_error(
    hass: HomeAssistant,
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
        mock_client.login = AsyncMock(
            side_effect=SunlitAuthError("Authentication failed")
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "invalid_password"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "user"
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_connection_error(
    hass: HomeAssistant,
):
    """Test connection error handling."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(
            side_effect=SunlitConnectionError("Cannot connect")
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "user"
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_no_families_selected(
    hass: HomeAssistant,
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
        mock_client.fetch_families = AsyncMock(
            return_value=families_response["content"]
        )

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
        mock_client.login = AsyncMock(return_value={"access_token": "test_api_key_123"})
        mock_client.fetch_families = AsyncMock(
            return_value=single_family_response["content"]
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )

        # Should show family selection even with single family
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "select_families"

        # Select the single family
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {"families": ["34038"]},
        )

        assert result3["type"] == FlowResultType.CREATE_ENTRY
        assert result3["title"] == "Sunlit (Garage)"
        assert result3["data"]["access_token"] == "test_api_key_123"
        assert "families" in result3["data"]
        assert len(result3["data"]["families"]) == 1


async def test_form_duplicate_entry(
    hass: HomeAssistant,
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


async def test_zeroconf_discovery_shows_confirm(hass: HomeAssistant):
    """A discovered BK215 should present a confirmation step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(),
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"]["serial_number"] == "HP-BK215-001"


async def test_zeroconf_confirm_proceeds_to_user(hass: HomeAssistant):
    """Confirming a discovery should funnel into the credential step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(),
    )

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "user"


async def test_zeroconf_discovery_full_flow(
    hass: HomeAssistant,
    families_response,
):
    """A discovery should be able to complete the normal cloud setup."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(),
    )
    assert result["step_id"] == "zeroconf_confirm"

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result2["step_id"] == "user"

    with patch(
        "custom_components.sunlit.config_flow.SunlitApiClient",
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.login = AsyncMock(return_value={"access_token": "test_api_key_123"})
        mock_client.fetch_families = AsyncMock(
            return_value=families_response["content"]
        )

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {"email": "test@example.com", "password": "test_password"},
        )
        assert result3["step_id"] == "select_families"

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {"families": ["34038"]},
        )

    assert result4["type"] == FlowResultType.CREATE_ENTRY
    assert result4["data"][CONF_ACCESS_TOKEN] == "test_api_key_123"
    assert len(result4["data"][CONF_FAMILIES]) == 1


async def test_zeroconf_discovery_already_configured(
    hass: HomeAssistant,
    mock_config_entry,
):
    """Discovery should abort when the account is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(),
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
