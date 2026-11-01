"""Switch that turns the check off, for example for a movie night."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch."""
    async_add_entities([CheckSwitch(entry)])


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
