"""ParentControl: rates running YouTube videos and pauses unsuitable ones."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .monitor import Monitor

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentControlConfigEntry) -> bool:
    """Unload ParentControl."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ParentControlConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
