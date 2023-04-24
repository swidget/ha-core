"""Test the init file of Swidget."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.swidget.const import DOMAIN
from homeassistant.core import HomeAssistant


async def test_discovery(hass: HomeAssistant) -> None:
    """Test Device Discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "homeassistant.components.swidget.config_flow.async_discover_devices",
        return_value={},
    ):
        res2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert res2["reason"] == "no_devices_found"
