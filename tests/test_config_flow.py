"""Test the Sunlit config flow."""

from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.sunlit import DOMAIN
from custom_components.sunlit.api_client import SunlitAuthError, SunlitConnectionError
from custom_components.sunlit.const import (
    CONF_ACCESS_TOKEN,
    CONF_BATTERIES,
    CONF_FAMILIES,
)


def _zeroconf_discovery_info(
    serial: str = "HP-BK215-001",
    host: str = "192.168.1.50",
    properties: dict[str, str] | None = None,
) -> ZeroconfServiceInfo:
    """Build a ZeroconfServiceInfo mimicking a BK215 mDNS advertisement.

    The mDNS service ``port`` is the device's ``_http`` port (80); the real
    TCP control port is advertised separately in the TXT ``port`` property
    (observed as 8000) and is what the local-mode channel uses.
    """
    txt = {
        "id": serial,
        "port": "8000",
        "fw_ver": "1.2.3",
        "model": "BK215",
    }
    if properties is not None:
        txt.update(properties)
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname=f"{serial.lower()}.local.",
        type="_http._tcp.local.",
        name=f"{serial.lower()}._http._tcp.local.",
        properties=txt,
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
    # The discovered battery is stamped onto the new entry so the local
    # channel can pick up its LAN address without waiting for another mDNS round.
    batteries = result4["data"][CONF_BATTERIES]
    assert batteries == {
        "HP-BK215-001": {
            "serial": "HP-BK215-001",
            "host": "192.168.1.50",
            "port": 8000,
            "sw_version": "1.2.3",
            "hw_version": "BK215",
        }
    }


async def test_zeroconf_discovery_already_configured(
    hass: HomeAssistant,
    mock_config_entry,
):
    """Discovery into a configured account merges LAN info, then aborts."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(),
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # First-time discovery against a pre-existing entry should populate
    # the batteries map.
    assert mock_config_entry.data[CONF_BATTERIES] == {
        "HP-BK215-001": {
            "serial": "HP-BK215-001",
            "host": "192.168.1.50",
            "port": 8000,
            "sw_version": "1.2.3",
            "hw_version": "BK215",
        }
    }


async def test_zeroconf_rediscovery_updates_changed_host(
    hass: HomeAssistant,
    mock_config_entry,
):
    """A rediscovery with a new IP rewrites the entry's batteries map."""
    mock_config_entry.add_to_hass(hass)

    # First advertisement at the original address.
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(host="192.168.1.50"),
    )
    assert mock_config_entry.data[CONF_BATTERIES]["HP-BK215-001"]["host"] == (
        "192.168.1.50"
    )

    # DHCP gave the battery a new lease.
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_discovery_info(host="192.168.1.99"),
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_BATTERIES]["HP-BK215-001"]["host"] == (
        "192.168.1.99"
    )
    # The change should trigger a reload so the local channel picks up the
    # new address.
    mock_reload.assert_called_once_with(mock_config_entry.entry_id)


async def test_zeroconf_rediscovery_no_change_does_not_reload(
    hass: HomeAssistant,
    mock_config_entry,
):
    """Repeat advertisements with identical info must not reload the entry."""
    mock_config_entry.add_to_hass(hass)

    # Prime the entry with one advertisement.
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_discovery_info(),
    )

    # Identical re-advertisement should be a no-op.
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_discovery_info(),
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_reload.assert_not_called()


async def test_zeroconf_falls_back_to_default_port_when_txt_port_missing(
    hass: HomeAssistant,
    mock_config_entry,
):
    """A TXT advertisement without a usable port falls back to 8000."""
    mock_config_entry.add_to_hass(hass)

    discovery = _zeroconf_discovery_info()
    discovery.properties.pop("port")

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery,
    )

    assert mock_config_entry.data[CONF_BATTERIES]["HP-BK215-001"]["port"] == 8000


async def test_zeroconf_aborts_when_serial_missing(hass: HomeAssistant):
    """A TXT record with no ``id`` (serial) is rejected as invalid."""
    discovery = _zeroconf_discovery_info()
    discovery.properties.pop("id")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery"
