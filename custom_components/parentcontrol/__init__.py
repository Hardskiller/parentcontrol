"""ParentControl: rates running YouTube videos and pauses unsuitable ones."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, MAX_AGE, SERVICE_ALLOW_CHANNEL, SERVICE_BLOCK_CHANNEL
from .monitor import Monitor

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

ATTR_AGE = "age"
ATTR_CHANNEL = "channel"
ATTR_ONLY_THIS_DEVICE = "only_this_device"
ATTR_PLAYER = "player"
SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CHANNEL): cv.string,
        vol.Optional(ATTR_PLAYER): cv.entity_id,
        vol.Optional(ATTR_AGE): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_AGE)),
        vol.Optional(ATTR_ONLY_THIS_DEVICE, default=False): cv.boolean,
    }
)

type ParentControlConfigEntry = ConfigEntry[Monitor]


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Group all entities under one service device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="ParentControl",
        entry_type=DeviceEntryType.SERVICE,
    )


def player_name(hass: HomeAssistant, player: str) -> str:
    """Return the readable name of a media player."""
    state = hass.states.get(player)
    return state.name if state else player.split(".", 1)[1]


def player_device_info(hass: HomeAssistant, entry: ConfigEntry, player: str) -> DeviceInfo:
    """Group the entities of one media player."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{player}")},
        name=f"ParentControl {player_name(hass, player)}",
        entry_type=DeviceEntryType.SERVICE,
        via_device=(DOMAIN, entry.entry_id),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ParentControlConfigEntry) -> bool:
    """Set up ParentControl."""
    monitor = Monitor(hass, entry)
    await monitor.async_load()
    entry.runtime_data = monitor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    monitor.async_start()
    entry.async_on_unload(monitor.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    async def async_list_channel(call: ServiceCall) -> None:
        """Add a channel, by default the one running on the given player."""
        player = call.data.get(ATTR_PLAYER)
        if player and player not in monitor.players:
            raise ServiceValidationError(f"{player} wird nicht überwacht")
        channel = call.data.get(ATTR_CHANNEL) or (monitor.status(player).channel if player else None)
        if not channel:
            raise ServiceValidationError("Kein Kanal angegeben oder gerade aktiv")
        only_this_device = call.data[ATTR_ONLY_THIS_DEVICE]
        if only_this_device and not player:
            raise ServiceValidationError("Für ein einzelnes Gerät fehlt der Player")
        monitor.async_list_channel(
            call.service == SERVICE_ALLOW_CHANNEL,
            channel,
            call.data.get(ATTR_AGE),
            player if only_this_device else None,
        )

    for service in (SERVICE_ALLOW_CHANNEL, SERVICE_BLOCK_CHANNEL):
        hass.services.async_register(DOMAIN, service, async_list_channel, SERVICE_SCHEMA)
        entry.async_on_unload(lambda name=service: hass.services.async_remove(DOMAIN, name))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentControlConfigEntry) -> bool:
    """Unload ParentControl."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ParentControlConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
