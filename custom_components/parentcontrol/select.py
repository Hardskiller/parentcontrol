"""Who is watching on each player."""
from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, player_device_info
from .const import SELECT_AUTO, SELECT_UNRESTRICTED

LABELS = {
    "de": {SELECT_AUTO: "Automatisch", SELECT_UNRESTRICTED: "Unbeschränkt"},
    "en": {SELECT_AUTO: "Automatic", SELECT_UNRESTRICTED: "Unrestricted"},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one selection per player."""
    async_add_entities(WhoSelect(hass, entry, player) for player in entry.runtime_data.players)


class WhoSelect(SelectEntity):
    """Automatic uses every assigned profile; anything else needs the PIN."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "who"

    def __init__(
        self, hass: HomeAssistant, entry: ParentControlConfigEntry, player: str
    ) -> None:
        self._monitor = entry.runtime_data
        self._player = player
        self._attr_unique_id = f"{entry.entry_id}_{player}_who"
        self._attr_device_info = player_device_info(hass, entry, player)
        labels = LABELS.get(hass.config.language[:2], LABELS["en"])
        # Option labels are shown as they are, so the profiles appear by name.
        self._values = {
            labels[SELECT_AUTO]: SELECT_AUTO,
            **{
                self._monitor.profile_name(profile): profile
                for profile in self._monitor.device_profiles.get(player, [])
                if profile in self._monitor.profiles
            },
            labels[SELECT_UNRESTRICTED]: SELECT_UNRESTRICTED,
        }
        self._attr_options = list(self._values)

    async def async_added_to_hass(self) -> None:
        """Follow the monitor, which resets the choice when the device turns off."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._monitor.signal, self.async_write_ha_state)
        )

    @property
    def current_option(self) -> str | None:
        """Return the label of the current choice."""
        value = self._monitor.selection(self._player)
        return next((label for label, option in self._values.items() if option == value), None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the values behind the labels, for the card."""
        return {
            "wert": self._monitor.selection(self._player),
            "werte": self._values,
        }

    async def async_select_option(self, option: str) -> None:
        """Choose who is watching; only Automatic works without the PIN."""
        value = self._values[option]
        await self._monitor.lock.async_authorize(self._context, loosens=value != SELECT_AUTO)
        self._monitor.async_select(self._player, value)
        self.async_write_ha_state()
