"""Viewing hours of each child profile."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, profile_device_info
from .const import (
    WINDOW_WEEKDAY_END,
    WINDOW_WEEKDAY_START,
    WINDOW_WEEKEND_END,
    WINDOW_WEEKEND_START,
    WINDOWS,
)
from .profiles import format_time, parse_time, window_minutes

# The other end of the same window, to tell whether a change widens it.
PARTNER = {
    WINDOW_WEEKDAY_START: WINDOW_WEEKDAY_END,
    WINDOW_WEEKDAY_END: WINDOW_WEEKDAY_START,
    WINDOW_WEEKEND_START: WINDOW_WEEKEND_END,
    WINDOW_WEEKEND_END: WINDOW_WEEKEND_START,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up four viewing times per profile."""
    async_add_entities(
        ProfileTime(entry, profile, key)
        for profile in entry.runtime_data.profiles
        for key in WINDOWS
    )


class ProfileTime(TimeEntity):
    """Start or end of a viewing window; the same start and end means all day."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ParentControlConfigEntry, profile: str, key: str) -> None:
        self._monitor = entry.runtime_data
        self._profile = profile
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile}_{key}"
        self._attr_device_info = profile_device_info(entry, profile)

    def _get(self, key: str) -> str:
        return self._monitor.profile_value(self._profile, key, "00:00")

    @property
    def native_value(self) -> time:
        """Return the time."""
        minute = parse_time(self._get(self._key))
        return time(minute // 60, minute % 60)

    async def async_set_value(self, value: time) -> None:
        """Change the time; widening the window needs the PIN."""
        new = format_time(value)
        partner = self._get(PARTNER[self._key])
        start_first = self._key in (WINDOW_WEEKDAY_START, WINDOW_WEEKEND_START)
        old_window = (self._get(self._key), partner) if start_first else (partner, self._get(self._key))
        new_window = (new, partner) if start_first else (partner, new)
        await self._monitor.lock.async_authorize(
            self._context,
            loosens=not window_minutes(*new_window) <= window_minutes(*old_window),
        )
        self._monitor.async_set_profile_value(self._profile, self._key, new)
        self.async_write_ha_state()
