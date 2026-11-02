"""Lock that opens the settings for a few minutes with the PIN."""
from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info
from .const import PIN_PATTERN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lock."""
    async_add_entities([SettingsLock(entry)])


class SettingsLock(LockEntity):
    """Locked means non-admin users cannot weaken the protection."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "settings"

    def __init__(self, entry: ParentControlConfigEntry) -> None:
        self._lock = entry.runtime_data.lock
        self._attr_unique_id = f"{entry.entry_id}_settings_lock"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow the lock."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._lock.signal, self.async_write_ha_state)
        )

    @property
    def code_format(self) -> str | None:
        """Ask for the PIN only to unlock; locking needs no code."""
        return None if self._lock.is_open else PIN_PATTERN

    @property
    def is_locked(self) -> bool:
        """Return whether the settings are locked."""
        return not self._lock.is_open

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return how long the lock stays open or blocked."""
        return {
            "offen_sekunden": self._lock.open_seconds,
            "gesperrt_sekunden": self._lock.blocked_seconds,
        }

    async def async_unlock(self, **kwargs: Any) -> None:
        """Open the settings with the PIN."""
        await self._lock.async_unlock(kwargs.get("code"), self._context)
        self.async_write_ha_state()

    async def async_lock(self, **kwargs: Any) -> None:
        """Close the settings; anyone may do this."""
        self._lock.async_lock()
        self.async_write_ha_state()
