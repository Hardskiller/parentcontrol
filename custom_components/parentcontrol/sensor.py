"""Status, watch time, latest videos and video statistics."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info, entity_ids, player_device_info, player_name
from .const import STATS, STATUSES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors per player and the shared statistics."""
    players = entry.runtime_data.players
    async_add_entities(
        [
            *(StatusSensor(hass, entry, player) for player in players),
            *(WatchTimeSensor(hass, entry, player) for player in players),
            *(HistorySensor(hass, entry, player) for player in players),
            *(StatSensor(entry, stat) for stat in STATS),
        ]
    )


class ParentControlSensor(SensorEntity):
    """Updates whenever the monitor reports a change."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ParentControlConfigEntry) -> None:
        self._monitor = entry.runtime_data
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow the monitor."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._monitor.signal, self.async_write_ha_state
            )
        )


class StatusSensor(ParentControlSensor):
    """Shows what the check found on one player."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_translation_key = "status"
    _unrecorded_attributes = frozenset({"entitaeten", "freigegeben", "gesperrt"})

    def __init__(
        self, hass: HomeAssistant, entry: ParentControlConfigEntry, player: str
    ) -> None:
        super().__init__(entry)
        self._entry = entry
        self._player = player
        self._attr_unique_id = f"{entry.entry_id}_{player}"
        self._attr_device_info = player_device_info(hass, entry, player)

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
            "sperrgrund": status.block_reason,
            "sperrtext": status.block_text,
            "liste": status.list_state,
            "short": status.short,
            "name": player_name(self.hass, self._player),
            "entitaeten": entity_ids(self.hass, self._entry, self._player),
            **self._monitor.channel_lists(self._player),
        }
        if status.rating:
            attributes |= {
                "mindestalter": status.rating.min_age,
                "grund": status.rating.reason,
                "paedagogisch_wertvoll": status.rating.valuable,
                "paedagogik_grund": status.rating.pedagogy_reason,
                "schimpfwoerter": status.rating.profanity,
                "schimpfwoerter_liste": status.rating.profanity_words,
                "quelle": status.rating.source,
                "video_id": status.rating.video_id,
            }
        return attributes


class WatchTimeSensor(ParentControlSensor):
    """Today's playing time of one player, counted for every app."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "watch_time"

    def __init__(
        self, hass: HomeAssistant, entry: ParentControlConfigEntry, player: str
    ) -> None:
        super().__init__(entry)
        self._player = player
        self._attr_unique_id = f"{entry.entry_id}_{player}_watch_time"
        self._attr_device_info = player_device_info(hass, entry, player)

    @property
    def native_value(self) -> int:
        """Return the minutes."""
        return self._monitor.watch_minutes(self._player)


class HistorySensor(ParentControlSensor):
    """The latest videos of one player; the state is the newest title."""

    _attr_translation_key = "history"
    # Twenty entries with reasons would bloat the database on every change.
    _unrecorded_attributes = frozenset({"videos"})

    def __init__(
        self, hass: HomeAssistant, entry: ParentControlConfigEntry, player: str
    ) -> None:
        super().__init__(entry)
        self._player = player
        self._attr_unique_id = f"{entry.entry_id}_{player}_history"
        self._attr_device_info = player_device_info(hass, entry, player)

    @property
    def native_value(self) -> str | None:
        """Return the newest title, shortened to the state limit."""
        history = self._monitor.history(self._player)
        return history[0]["titel"][:255] if history else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the videos, newest first."""
        return {"videos": self._monitor.history(self._player)}


class StatSensor(ParentControlSensor):
    """Number of videos today; the attribute holds the count since installation."""

    _attr_native_unit_of_measurement = "Videos"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, entry: ParentControlConfigEntry, stat: str) -> None:
        super().__init__(entry)
        self._stat = stat
        self._attr_translation_key = stat
        self._attr_unique_id = f"{entry.entry_id}_{stat}"

    @property
    def native_value(self) -> int:
        """Return today's count."""
        return self._monitor.stat_today(self._stat)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the overall count."""
        return {"gesamt": self._monitor.stat_total(self._stat)}
