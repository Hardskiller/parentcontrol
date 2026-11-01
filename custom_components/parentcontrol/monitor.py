"""Watches media players and pauses videos above the child's age."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_STANDBY, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from . import engine
from .const import (
    CONF_AGE,
    CONF_DEVICE_AGES,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_PLAYERS,
    DOMAIN,
    EVENT_PAUSED,
    MAX_EVENTS,
    PAUSE_DEBOUNCE_SECONDS,
    RETRY_SECONDS,
    STATUS_BLOCKED,
    STATUS_CHECKING,
    STATUS_DISABLED,
    STATUS_FREE,
    STATUS_IDLE,
    STATUS_NO_DATA,
    STATUS_UNCHECKED,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

INACTIVE_STATES = {STATE_OFF, STATE_STANDBY, STATE_UNAVAILABLE, STATE_UNKNOWN}
SAVE_DELAY_SECONDS = 5


@dataclass(frozen=True)
class PlayerStatus:
    """Current result for one media player."""

    status: str = STATUS_IDLE
    title: str | None = None
    channel: str | None = None
    age: int | None = None
    rating: engine.Rating | None = None


class Monitor:
    """Rates what the configured players show and enforces the result."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.players: list[str] = entry.options[CONF_PLAYERS]
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.age: int = entry.data[CONF_AGE]
        self.enabled = True
        self._device_ages: dict[str, int] = entry.options.get(CONF_DEVICE_AGES, {})
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._ratings: dict[str, dict] = {}
        self._events: list[dict] = []
        self._statuses: dict[str, PlayerStatus] = {}
        self._pending: set[str] = set()
        self._failed: dict[str, float] = {}
        self._last_pause: dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(1)
        self._unsubscribe = None

    async def async_load(self) -> None:
        """Restore age, switch, ratings and the protocol."""
        data = await self._store.async_load() or {}
        self.age = data.get("age", self.age)
        self.enabled = data.get("enabled", True)
        self._ratings = data.get("ratings", {})
        self._events = data.get("events", [])

    @callback
    def async_start(self) -> None:
        """Start following the players."""
        self._unsubscribe = async_track_state_change_event(
            self.hass, self.players, self._state_changed
        )
        self.async_evaluate_all()

    @callback
    def async_stop(self) -> None:
        """Stop following the players."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def status(self, player: str) -> PlayerStatus:
        """Return the current result for a player."""
        return self._statuses.get(player, PlayerStatus())

    @callback
    def async_set_age(self, age: int) -> None:
        """Change the default age."""
        self.age = age
        self._save()
        self.async_evaluate_all()

    @callback
    def async_set_enabled(self, enabled: bool) -> None:
        """Switch the check on or off."""
        self.enabled = enabled
        self._save()
        self.async_evaluate_all()

    @callback
    def async_evaluate_all(self) -> None:
        """Evaluate every player."""
        for player in self.players:
            self._evaluate(player)

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        self._evaluate(event.data["entity_id"])

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY_SECONDS)

    @callback
    def _data(self) -> dict:
        return {
            "age": self.age,
            "enabled": self.enabled,
            "ratings": self._ratings,
            "events": self._events,
        }

    @callback
    def _log_event(self, event: str, video: engine.Video, rating: dict | None) -> None:
        self._events.append(
            {
                "at": time.time(),
                "event": event,
                "title": video.title,
                "channel": video.channel,
                "min_age": rating["min_age"] if rating else None,
                "reason": rating["reason"] if rating else None,
            }
        )
        del self._events[:-MAX_EVENTS]
        self._save()

    @callback
    def _publish(self, player: str, status: PlayerStatus) -> None:
        if self._statuses.get(player) != status:
            self._statuses[player] = status
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def _ensure_rated(self, key: str, video: engine.Video) -> None:
        """Start a check unless there is a rating or a recent failure."""
        if key in self._ratings or key in self._pending:
            return
        failed_at = self._failed.get(key)
        if failed_at and time.monotonic() - failed_at < RETRY_SECONDS:
            return
        self._pending.add(key)
        self.entry.async_create_background_task(
            self.hass, self._async_rate(key, video), f"{DOMAIN} rate {video.title}"
        )

    async def _async_rate(self, key: str, video: engine.Video) -> None:
        try:
            async with self._semaphore:
                rating = await self.hass.async_add_executor_job(
                    engine.rate,
                    video,
                    self.entry.data[CONF_OLLAMA_URL],
                    self.entry.options[CONF_MODEL],
                )
        except (OSError, ValueError, KeyError) as err:
            _LOGGER.warning("Einstufung fehlgeschlagen für %r: %s", video.title, err)
            self._failed[key] = time.monotonic()
            self._log_event("nicht_geprueft", video, None)
        else:
            self._failed.pop(key, None)
            self._ratings[key] = asdict(rating)
            self._log_event("eingestuft", video, self._ratings[key])
        finally:
            self._pending.discard(key)
        self.async_evaluate_all()

    @callback
    def _pause(self, player: str, video: engine.Video, rating: dict) -> None:
        # A player reports several updates per play, each must not count twice.
        now = time.monotonic()
        if now - self._last_pause.get(player, -PAUSE_DEBOUNCE_SECONDS) < PAUSE_DEBOUNCE_SECONDS:
            return
        self._last_pause[player] = now
        self.hass.async_create_task(
            self.hass.services.async_call(
                "media_player", "media_pause", {"entity_id": player}
            )
        )
        self._log_event("pausiert", video, rating)
        self.hass.bus.async_fire(
            EVENT_PAUSED,
            {"entity_id": player, "title": video.title, "min_age": rating["min_age"]},
        )
        _LOGGER.info("Pausiert auf %s: %r", player, video.title)

    @callback
    def _evaluate(self, player: str) -> None:
        state = self.hass.states.get(player)
        if state is None or state.state in INACTIVE_STATES:
            self._publish(player, PlayerStatus())
            return
        attributes = state.attributes
        if "youtube" not in str(attributes.get("app_name") or "").lower():
            self._publish(player, PlayerStatus())
            return
        title = attributes.get("media_title")
        if not title:
            self._publish(player, PlayerStatus(STATUS_NO_DATA))
            return
        channel = attributes.get("media_artist") or ""
        age = self._device_ages.get(player, self.age)
        if not self.enabled:
            self._publish(player, PlayerStatus(STATUS_DISABLED, title, channel, age))
            return
        video = engine.Video(title, channel, attributes.get("media_duration"))
        key = f"{title}\n{channel}"
        self._ensure_rated(key, video)
        # Background tasks start eagerly, so the rating may exist by now.
        rating = self._ratings.get(key)
        if rating is None:
            status = STATUS_CHECKING if key in self._pending else STATUS_UNCHECKED
            self._publish(player, PlayerStatus(status, title, channel, age))
            return
        allowed = engine.is_allowed(rating["min_age"], age)
        if not allowed and state.state == "playing":
            self._pause(player, video, rating)
        self._publish(
            player,
            PlayerStatus(
                STATUS_FREE if allowed else STATUS_BLOCKED,
                title,
                channel,
                age,
                engine.Rating(**rating),
            ),
        )
