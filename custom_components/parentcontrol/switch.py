"""Switches for the whole check and the checkboxes of each player."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info, player_device_info
from .const import SETTINGS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switches."""
    async_add_entities(
        [
            CheckSwitch(entry),
            *(
                PlayerSettingSwitch(hass, entry, player, setting)
                for player in entry.runtime_data.players
                for setting in SETTINGS
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
        """Turn the check off."""
        self._monitor.async_set_enabled(False)
        self.async_write_ha_state()


class PlayerSettingSwitch(SwitchEntity):
    """One checkbox of one media player."""

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
        return self._monitor.setting(self._player, self._setting)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the checkbox."""
        self._monitor.async_set_setting(self._player, self._setting, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the checkbox."""
        self._monitor.async_set_setting(self._player, self._setting, False)
        self.async_write_ha_state()
