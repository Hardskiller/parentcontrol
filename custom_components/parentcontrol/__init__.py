"""ParentControl: rates running YouTube videos and pauses unsuitable ones."""
from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.loader import async_get_integration

from .const import (
    CONF_NAME,
    CONF_PIN_HASH,
    DEVICE_SETTINGS,
    DOMAIN,
    HEALTH,
    MAX_AGE,
    PROFILE_SETTINGS,
    SERVICE_ALLOW_CHANNEL,
    SERVICE_ALLOW_WORD,
    SERVICE_BLOCK_CHANNEL,
    SERVICE_REMOVE_CHANNEL,
    SERVICE_REMOVE_WORD,
    STATS,
)
from .monitor import Monitor
from .pinlock import PinLock

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

ATTR_AGE = "age"
ATTR_CHANNEL = "channel"
ATTR_LIST = "list"
ATTR_PLAYER = "player"
ATTR_PROFILE = "profile"
ATTR_WORD = "word"
LIST_ALLOWED = "allowed"
LIST_BLOCKED = "blocked"
CHANNEL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CHANNEL): cv.string,
        vol.Optional(ATTR_PLAYER): cv.entity_id,
        vol.Optional(ATTR_AGE): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_AGE)),
        vol.Optional(ATTR_PROFILE): cv.string,
    }
)
REMOVE_SCHEMA = CHANNEL_SCHEMA.extend(
    {vol.Required(ATTR_LIST): vol.In([LIST_ALLOWED, LIST_BLOCKED])}
)
WORD_SCHEMA = vol.Schema(
    {vol.Required(ATTR_WORD): cv.string, vol.Optional(ATTR_PROFILE): cv.string}
)

CARD_URL = f"/{DOMAIN}/{DOMAIN}-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / f"{DOMAIN}-card.js"

type ParentControlConfigEntry = ConfigEntry[Monitor]


def entity_ids(
    hass: HomeAssistant,
    entry: ConfigEntry,
    player: str | None = None,
    profile: str | None = None,
) -> dict[str, str]:
    """Map the roles of the entities to their entity ids, for the card."""
    if player:
        prefix = f"{entry.entry_id}_{player}"
        roles = {
            "status": ("sensor", prefix),
            "watch_time": ("sensor", f"{prefix}_watch_time"),
            "history": ("sensor", f"{prefix}_history"),
            "select": ("select", f"{prefix}_who"),
            **{setting: ("switch", f"{prefix}_{setting}") for setting in DEVICE_SETTINGS},
        }
    elif profile:
        prefix = f"{entry.entry_id}_profile_{profile}"
        roles = {
            "profile": ("sensor", prefix),
            "age": ("number", f"{prefix}_age"),
            **{setting: ("switch", f"{prefix}_{setting}") for setting in PROFILE_SETTINGS},
        }
    else:
        prefix = entry.entry_id
        roles = {
            "lock": ("lock", f"{prefix}_settings_lock"),
            "check": ("switch", f"{prefix}_check"),
            **{stat: ("sensor", f"{prefix}_{stat}") for stat in STATS},
            **{name: ("binary_sensor", f"{prefix}_{name}_health") for name in HEALTH},
        }
    registry = er.async_get(hass)
    found = {
        role: registry.async_get_entity_id(domain, DOMAIN, unique_id)
        for role, (domain, unique_id) in roles.items()
    }
    return {role: entity_id for role, entity_id in found.items() if entity_id}


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard card and load it on every dashboard."""
    if hass.http is None or "frontend" not in hass.config.components:
        return
    # Imported here, because tests run without the frontend.
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    flags = hass.data.setdefault(f"{DOMAIN}_card", {})
    if flags.get("registered"):
        return
    flags["registered"] = True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    version = (await async_get_integration(hass, DOMAIN)).version
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")


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


def profile_device_info(entry: ConfigEntry, profile: str) -> DeviceInfo:
    """Group the entities of one child profile."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_profile_{profile}")},
        name=f"ParentControl {entry.options['profiles'][profile][CONF_NAME]}",
        entry_type=DeviceEntryType.SERVICE,
        via_device=(DOMAIN, entry.entry_id),
    )


def _remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry, monitor: Monitor) -> None:
    """Remove devices of players and profiles that were taken out in the options."""
    expected = {
        entry.entry_id,
        *(f"{entry.entry_id}_{player}" for player in monitor.players),
        *(f"{entry.entry_id}_profile_{profile}" for profile in monitor.profiles),
    }
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not any(domain == DOMAIN and ident in expected for domain, ident in device.identifiers):
            registry.async_remove_device(device.id)


async def async_setup_entry(hass: HomeAssistant, entry: ParentControlConfigEntry) -> bool:
    """Set up ParentControl."""
    locks: dict[str, PinLock] = hass.data.setdefault(DOMAIN, {})
    lock = locks.get(entry.entry_id) or PinLock(hass, f"{DOMAIN}_{entry.entry_id}")
    locks[entry.entry_id] = lock
    lock.pin_hash = entry.options.get(CONF_PIN_HASH)
    entry.async_on_unload(lock.async_unload)
    monitor = Monitor(hass, entry, lock)
    await monitor.async_load()
    entry.runtime_data = monitor
    _remove_stale_devices(hass, entry, monitor)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    monitor.async_start()
    entry.async_on_unload(monitor.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await _async_register_card(hass)

    def find_profile(call: ServiceCall) -> str | None:
        if not (value := call.data.get(ATTR_PROFILE)):
            return None
        if not (profile := monitor.find_profile(value)):
            raise ServiceValidationError(f"Profil {value} gibt es nicht")
        return profile

    async def async_list_channel(call: ServiceCall) -> None:
        """Change a channel list, by default for the channel running on the given player."""
        player = call.data.get(ATTR_PLAYER)
        if player and player not in monitor.players:
            raise ServiceValidationError(f"{player} wird nicht überwacht")
        channel = call.data.get(ATTR_CHANNEL) or (monitor.status(player).channel if player else None)
        if not channel:
            raise ServiceValidationError("Kein Kanal angegeben oder gerade aktiv")
        profile = find_profile(call)
        if call.service == SERVICE_REMOVE_CHANNEL:
            # Taking a channel off the blocked list weakens the protection.
            from_allowed = call.data[ATTR_LIST] == LIST_ALLOWED
            await lock.async_authorize(call.context, loosens=not from_allowed)
            monitor.async_remove_channel(from_allowed, channel, profile)
            return
        allow = call.service == SERVICE_ALLOW_CHANNEL
        await lock.async_authorize(call.context, loosens=allow)
        monitor.async_list_channel(allow, channel, call.data.get(ATTR_AGE), profile)

    async def async_word(call: ServiceCall) -> None:
        """Allow a swear word, or take it back."""
        allow = call.service == SERVICE_ALLOW_WORD
        profile = find_profile(call)
        await lock.async_authorize(call.context, loosens=allow)
        monitor.async_set_word(allow, call.data[ATTR_WORD], profile)

    for service, handler, schema in (
        (SERVICE_ALLOW_CHANNEL, async_list_channel, CHANNEL_SCHEMA),
        (SERVICE_BLOCK_CHANNEL, async_list_channel, CHANNEL_SCHEMA),
        (SERVICE_REMOVE_CHANNEL, async_list_channel, REMOVE_SCHEMA),
        (SERVICE_ALLOW_WORD, async_word, WORD_SCHEMA),
        (SERVICE_REMOVE_WORD, async_word, WORD_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, service, handler, schema)
        entry.async_on_unload(lambda name=service: hass.services.async_remove(DOMAIN, name))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentControlConfigEntry) -> bool:
    """Unload ParentControl."""
    # A reload after a list change must not lose a delayed save.
    await entry.runtime_data.async_save_now()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ParentControlConfigEntry) -> None:
    """Forget the lock state."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)


async def _async_reload(hass: HomeAssistant, entry: ParentControlConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
