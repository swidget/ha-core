"""Config flow for Swidget integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from swidget.discovery import SwidgetDiscoveredDevice, discover_devices
from swidget.exceptions import SwidgetException
from swidget.swidgetdevice import SwidgetDevice
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE,
    CONF_HOST,
    CONF_MAC,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import async_trigger_discovery
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
DISCOVERY_INTERVAL = timedelta(minutes=15)
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST, default=""): str,
        vol.Optional("password"): str,
    }
)


async def async_discover_devices(
    hass: HomeAssistant,
) -> dict[str, SwidgetDiscoveredDevice]:
    """Force discover Swidget devices using."""
    discovered_devices: dict[str, SwidgetDiscoveredDevice] = await discover_devices()
    return discovered_devices


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Return info that you want to store in the config entry.
    try:
        device = SwidgetDevice(
            data["host"], data["token_name"], data["password"], False
        )
        await device.update()
        return {"title": f"{device.friendly_name}"}
    except SwidgetException as exc:
        raise CannotConnect from exc


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Swidget component."""
    hass.data[DOMAIN] = {}

    if discovered_devices := await async_discover_devices(hass):
        async_trigger_discovery(hass, discovered_devices)

    async def _async_discovery(*_: Any) -> None:
        if discovered := await async_discover_devices(hass):
            async_trigger_discovery(hass, discovered)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_discovery)
    async_track_time_interval(hass, _async_discovery, DISCOVERY_INTERVAL)
    return True


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swidget."""

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, SwidgetDiscoveredDevice] = {}
        self._discovered_device: SwidgetDiscoveredDevice | None = None

    VERSION = 1

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> FlowResult:
        """Handle integration discovery."""
        return await self._async_handle_discovery(
            discovery_info[CONF_HOST], discovery_info[CONF_MAC]
        )

    async def _async_handle_discovery(self, host: str, mac: str) -> FlowResult:
        """Handle any discovery."""
        await self.async_set_unique_id(dr.format_mac(mac))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._async_abort_entries_match({CONF_HOST: host})
        self.context[CONF_HOST] = host
        for progress in self._async_in_progress():
            if progress.get("context", {}).get(CONF_HOST) == host:
                return self.async_abort(reason="already_in_progress")

        self._discovered_device = SwidgetDiscoveredDevice(mac, host)
        await self.async_set_unique_id(dr.format_mac(mac), raise_on_progress=True)
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovered_device is not None
        if user_input is not None:
            user_input["host"] = self._discovered_device.host
            info = await validate_input(self.hass, user_input)
            return self.async_create_entry(title=info["title"], data=user_input)

        self._set_confirm_only()
        placeholders = {
            "name": self._discovered_device.friendly_name,
            "host": self._discovered_device.host,
        }
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("password"): str,
                    vol.Required("token_name", default="x-secret-key"): str,
                }
            ),
            description_placeholders=placeholders,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            if not (user_input[CONF_HOST]):
                return await self.async_step_pick_device()

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the step to pick discovered device."""
        if user_input is not None:
            user_input["host"] = self._discovered_devices[user_input["device"]].host
            info = await validate_input(self.hass, user_input)
            return self.async_create_entry(title=info["title"], data=user_input)

        configured_devices = {
            entry.unique_id for entry in self._async_current_entries()
        }
        self._discovered_devices = await async_discover_devices(self.hass)

        devices_name = {
            mac: f"{device.friendly_name} ({device.host})"
            for mac, device in self._discovered_devices.items()
            if mac not in configured_devices
        }

        # Check if there is at least one device
        if not devices_name:
            return self.async_abort(reason="no_devices_found")
        options = [
            SelectOptionDict(value="x-secret-key", label="x-secret-key"),
            SelectOptionDict(value="x-site-key", label="x-site-key"),
            SelectOptionDict(value="x-user-key", label="x-user-key"),
        ]

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): vol.In(devices_name),
                    vol.Required("token_name"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required("password"): str,
                }
            ),
        )

    @callback
    def _async_create_entry_from_device(
        self, device: SwidgetDiscoveredDevice
    ) -> FlowResult:
        """Create a config entry from a smart device."""
        self._abort_if_unique_id_configured(updates={CONF_MAC: device.mac})
        return self.async_create_entry(
            title=device.friendly_name,
            data={CONF_HOST: device.host},
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""