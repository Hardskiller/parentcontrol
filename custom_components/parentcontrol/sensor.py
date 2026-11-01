"""Status of the check per media player."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info
from .const import STATUSES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one status sensor per player."""
    async_add_entities(StatusSensor(entry, player) for player in entry.runtime_data.players)


class StatusSensor(SensorEntity):
    """Shows what the check found on one player."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_translation_key = "status"

    def __init__(self, entry: ParentControlConfigEntry, player: str) -> None:
        self._monitor = entry.runtime_data
        self._player = player
        self._attr_name = f"YouTube-Prüfung {player.split('.', 1)[1]}"
        self._attr_unique_id = f"{entry.entry_id}_{player}"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow the monitor."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._monitor.signal, self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> str:
        """Return the status."""
        return self._monitor.status(self._player).status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the details."""
        status = self._monitor.status(self._player)
        attributes: dict[str, Any] = {
            "player": self._player,
            "titel": status.title,
            "kanal": status.channel,
            "alter": status.age,
        }
        if status.rating:
            attributes |= {
                "mindestalter": status.rating.min_age,
                "grund": status.rating.reason,
                "quelle": status.rating.source,
                "video_id": status.rating.video_id,
            }
        return attributes
