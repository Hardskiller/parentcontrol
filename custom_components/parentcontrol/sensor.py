"""Status, watch time, latest videos, child profiles and video statistics."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    ParentControlConfigEntry,
    device_info,
    entity_ids,
    player_device_info,
    player_name,
    profile_device_info,
)
from .const import CONF_PERSON, STATS, STATUSES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors per player and the shared statistics."""
    players = entry.runtime_data.players
    async_add_entities(
        [
            *(ProfileSensor(entry, profile) for profile in entry.runtime_data.profiles),
            *(RemainingSensor(entry, profile) for profile in entry.runtime_data.profiles),
            DailyReportSensor(entry),
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
    _unrecorded_attributes = frozenset({"entitaeten", "profile", "profil_namen"})

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
            "auswahl": self._monitor.selection(self._player),
            "profile": list(status.profiles),
            "profil_namen": [self._monitor.profile_name(pid) for pid in status.profiles],
            "zugeordnet": self._monitor.device_profiles.get(self._player, []),
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


class ProfileSensor(ParentControlSensor):
    """One child: today's watch time as state, the profile for the card as attributes."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "profile_watch_time"
    _unrecorded_attributes = frozenset(
        {
            "entitaeten",
            "freigegeben",
            "gesperrt",
            "erlaubte_woerter",
            "bild",
            "woche",
            "erlaubte_videos",
        }
    )

    def __init__(self, entry: ParentControlConfigEntry, profile: str) -> None:
        super().__init__(entry)
        self._entry = entry
        self._profile = profile
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile}"
        self._attr_device_info = profile_device_info(entry, profile)

    @property
    def native_value(self) -> int:
        """Return today's minutes of this child."""
        return self._monitor.profile_watch_minutes(self._profile)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return name, picture, entities and lists of the child."""
        person = self._monitor.profiles[self._profile].get(CONF_PERSON)
        person_state = self.hass.states.get(person) if person else None
        return {
            "profil": self._profile,
            "name": self._monitor.profile_name(self._profile),
            "person": person,
            "bild": person_state.attributes.get("entity_picture") if person_state else None,
            "entitaeten": entity_ids(self.hass, self._entry, profile=self._profile),
            "youtube_heute": self._monitor.youtube_minutes(self._profile),
            "limit_heute": self._monitor.limit_today(self._profile),
            "bonus_heute": self._monitor.bonus_minutes(self._profile),
            "restzeit": self._monitor.remaining_minutes(self._profile),
            "zeitfenster_heute": list(self._monitor.window(self._profile)),
            "im_zeitfenster": self._monitor.in_viewing_time(self._profile),
            "woche": self._monitor.week(self._profile),
            "erlaubte_videos": self._monitor.allowed_videos(self._profile),
            **self._monitor.lists(self._profile),
        }


class RemainingSensor(ParentControlSensor):
    """YouTube minutes left today for one child; unknown without a limit."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "remaining"

    def __init__(self, entry: ParentControlConfigEntry, profile: str) -> None:
        super().__init__(entry)
        self._profile = profile
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile}_remaining"
        self._attr_device_info = profile_device_info(entry, profile)

    @property
    def native_value(self) -> int | None:
        """Return the minutes left."""
        return self._monitor.remaining_minutes(self._profile)


class DailyReportSensor(ParentControlSensor):
    """Today per child and the blocked videos, for the daily report blueprint."""

    _attr_translation_key = "daily_report"
    _unrecorded_attributes = frozenset({"kinder", "gesperrte_videos"})

    def __init__(self, entry: ParentControlConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_daily_report"

    @property
    def native_value(self) -> int:
        """Return the number of blocked videos today."""
        return len(self._monitor.daily_report()["gesperrte_videos"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the report."""
        return self._monitor.daily_report()


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
