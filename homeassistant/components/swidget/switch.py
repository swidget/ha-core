"""Support for TPLink lights."""
from __future__ import annotations

import logging
from typing import Any, cast

from swidget.swidgetdevice import DeviceType, SwidgetDevice
from swidget.swidgetoutlet import SwidgetOutlet
from swidget.swidgetswitch import SwidgetSwitch
import voluptuous as vol

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwidgetDataUpdateCoordinator
from .entity import CoordinatedSwidgetEntity, async_refresh_after

_LOGGER = logging.getLogger(__name__)
DURATION = "duration"
VAL = vol.Range(min=1, max=1440)
SERVICE_SWIDGET_SET_COUNTDOWN_TIMER = "set_countdown_timer"
SWIDGET_SET_COUNTDOWN_TIMER_SCHEMA = cv.make_entity_service_schema({DURATION: VAL})


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Switch."""
    coordinator: SwidgetDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[SwidgetSwitchGeneric] = []

    # if coordinator.device.is_dimmer:
    #     entities.append(SwidgetPlugSwitch(cast(SwidgetDimmer, coordinator.device), coordinator))
    if coordinator.device.is_outlet:
        entities.append(
            SwidgetPlugSwitch(cast(SwidgetOutlet, coordinator.device), coordinator)
        )
    if coordinator.device.is_switch:
        entities.append(
            SwidgetPlugSwitch(cast(SwidgetSwitch, coordinator.device), coordinator)
        )
    if coordinator.device.insert_type == "USB":
        entities.append(
            SwidgetUSBSwitch(cast(SwidgetOutlet, coordinator.device), coordinator)
        )
    async_add_entities(entities)

    if coordinator.device.device_type == DeviceType.TimerSwitch:
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            SERVICE_SWIDGET_SET_COUNTDOWN_TIMER,
            SWIDGET_SET_COUNTDOWN_TIMER_SCHEMA,
            "set_countdown_timer",
        )


class SwidgetSwitchGeneric(CoordinatedSwidgetEntity, SwitchEntity):
    """Representation of a swidget switch."""

    def set_attr(self) -> None:
        """Set the attributes specific to the switch type."""
        raise NotImplementedError()

    def __init__(
        self,
        device: SwidgetDevice,
        coordinator: SwidgetDataUpdateCoordinator,
    ) -> None:
        """Initialize the switch."""
        super().__init__(device, coordinator)
        self.set_attr()


class SwidgetPlugSwitch(SwidgetSwitchGeneric):
    """Representation of a swidget plug."""

    def set_attr(self) -> None:
        """Set the attributes for the plug."""
        self._attr_name = "Controlled Outlet"
        self._attr_unique_id = f"{self.device}_controlled_outlet"

    @async_refresh_after
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.device.turn_on()

    @async_refresh_after
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.device.turn_off()

    @property
    def is_on(self) -> bool:
        """Check if switch is on."""
        return self.device.is_on

    async def set_countdown_timer(self, **kwargs: Any) -> None:
        """Set the switch timer."""
        if DURATION in kwargs:
            await self.device.set_countdown_timer(kwargs[DURATION])


class SwidgetUSBSwitch(SwidgetSwitchGeneric):
    """Representation of a swidget USB witch."""

    def set_attr(self) -> None:
        """Set the attributes for the usb."""
        self._attr_name = "USB Outlet"
        self._attr_unique_id = f"{self.device}_usb_outlet"

    @async_refresh_after
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.device.turn_on_usb_insert()

    @async_refresh_after
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.device.turn_off_usb_insert()

    @property
    def is_on(self) -> bool:
        """Check if switch is on."""
        return self.device.usb_is_on
