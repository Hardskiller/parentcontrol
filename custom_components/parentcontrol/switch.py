"""Switches for the whole check, each player and each child profile."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info, player_device_info, profile_device_info
from .const import DEVICE_SETTINGS, PROFILE_SETTINGS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switches."""
    monitor = entry.runtime_data
    async_add_entities(
        [
            CheckSwitch(entry),
            *(
                DeviceSwitch(hass, entry, player, setting)
                for player in monitor.players
                for setting in DEVICE_SETTINGS
            ),
            *(
                ProfileSwitch(entry, profile, setting)
                for profile in monitor.profiles
                for setting in PROFILE_SETTINGS
            ),
        ]
    )


class CheckSwitch(SwitchEntity):
    """Turns the check on or off for all players."""

    _attr_has_entity_name = True
    _attr_translation_key = "check"

    def __init__(self, entry: ParentControlConfigEntry) -> None:
        self._monitor = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_check"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        """Return whether the check is active."""
        return self._monitor.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the check on."""
        self._monitor.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the check off; needs the PIN."""
        await self._monitor.lock.async_authorize(self._context, loosens=True)
        self._monitor.async_set_enabled(False)
        self.async_write_ha_state()


class DeviceSwitch(SwitchEntity):
    """A checkbox that belongs to the player, not to a child."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ParentControlConfigEntry,
        player: str,
        setting: str,
    ) -> None:
        self._monitor = entry.runtime_data
        self._player = player
        self._setting = setting
        self._attr_translation_key = setting
        self._attr_unique_id = f"{entry.entry_id}_{player}_{setting}"
        self._attr_device_info = player_device_info(hass, entry, player)

    @property
    def is_on(self) -> bool:
        """Return whether the checkbox is set."""
        return self._monitor.device_setting(self._player, self._setting)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the checkbox."""
        self._monitor.async_set_device_setting(self._player, self._setting, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the checkbox."""
        self._monitor.async_set_device_setting(self._player, self._setting, False)
        self.async_write_ha_state()


class ProfileSwitch(SwitchEntity):
    """A rule of one child."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ParentControlConfigEntry, profile: str, setting: str) -> None:
        self._monitor = entry.runtime_data
        self._profile = profile
        self._setting = setting
        self._attr_translation_key = setting
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile}_{setting}"
        self._attr_device_info = profile_device_info(entry, profile)

    @property
    def is_on(self) -> bool:
        """Return whether the rule is set."""
        return self._monitor.profile_setting(self._profile, self._setting)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the rule."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the rule."""
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        await self._monitor.lock.async_authorize(
            self._context, loosens=self._monitor.loosens_setting(self._setting, value)
        )
        self._monitor.async_set_profile_setting(self._profile, self._setting, value)
        self.async_write_ha_state()
