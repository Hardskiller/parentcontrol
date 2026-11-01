"""Watches media players and pauses videos that fail the check."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_OFF,
    STATE_PLAYING,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import engine
from .const import (
    BLOCK_AGE,
    BLOCK_NO_SUBTITLES,
    BLOCK_PEDAGOGY,
    BLOCK_PROFANITY,
    BLOCK_UNCHECKED,
    CONF_AGE,
    CONF_AGE_PROMPT,
    CONF_DEVICE_AGES,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_PEDAGOGY_PROMPT,
    CONF_PLAYERS,
    DOMAIN,
    EVENT_PAUSED,
    MAX_EVENTS,
    PAUSE_DEBOUNCE_SECONDS,
    RETRY_SECONDS,
    SETTING_BLOCK_PROFANITY,
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_SEEK_TO_START,
    SETTING_STRICT,
    STAT_APPROVED,
    STAT_SKIPPED,
    STAT_VALUABLE,
    STAT_VIDEOS,
    STATS,
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
ENFORCE_INTERVAL = timedelta(seconds=3)
MAX_TICK_SECONDS = 30


@dataclass(frozen=True)
class PlayerStatus:
    """Current result for one media player."""

    status: str = STATUS_IDLE
    title: str | None = None
    channel: str | None = None
    age: int | None = None
    rating: engine.Rating | None = None
    block_reason: str | None = None


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
        self._settings: dict[str, dict[str, bool]] = {}
        self._system_prompt = engine.build_system_prompt(
            entry.options.get(CONF_AGE_PROMPT, engine.DEFAULT_AGE_PROMPT),
            entry.options.get(CONF_PEDAGOGY_PROMPT, engine.DEFAULT_PEDAGOGY_PROMPT),
        )
        # Part of the cache key, so edited prompts lead to new ratings.
        self._prompt_id = hashlib.sha256(self._system_prompt.encode()).hexdigest()[:8]
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._ratings: dict[str, dict] = {}
        self._events: list[dict] = []
        self._statuses: dict[str, PlayerStatus] = {}
        self._pending: set[str] = set()
        self._failed: dict[str, float] = {}
        self._last_pause: dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(1)
        self._unsubscribe: list[Callable[[], None]] = []
        self._day = dt_util.now().date().isoformat()
        self._seen: list[str] = []
        self._today = dict.fromkeys(STATS, 0)
        self._totals = dict.fromkeys(STATS, 0)
        self._watch_seconds: dict[str, float] = {}
        self._last_tick = time.monotonic()

    async def async_load(self) -> None:
        """Restore age, switch, ratings, statistics and the protocol."""
        data = await self._store.async_load() or {}
        self.age = data.get("age", self.age)
        self.enabled = data.get("enabled", True)
        self._settings = data.get("settings", {})
        self._ratings = data.get("ratings", {})
        self._events = data.get("events", [])
        self._totals |= data.get("totals", {})
        if data.get("day") == self._day:
            self._seen = data.get("seen", [])
            self._today |= data.get("today", {})
            self._watch_seconds = data.get("watch_seconds", {})

    @callback
    def async_start(self) -> None:
        """Start following the players."""
        self._unsubscribe = [
            async_track_state_change_event(self.hass, self.players, self._state_changed),
            # Cast reports play and pause within a second. Without its own timer
            # a blocked video keeps running when the last report gets debounced.
            async_track_time_interval(self.hass, self._interval, ENFORCE_INTERVAL),
        ]
        self.async_evaluate_all()

    @callback
    def async_stop(self) -> None:
        """Stop following the players."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []

    def setting(self, player: str, setting: str) -> bool:
        """Return a checkbox of a player; all start switched off."""
        return self._settings.get(player, {}).get(setting, False)

    @callback
    def async_set_setting(self, player: str, setting: str, value: bool) -> None:
        """Change a checkbox of a player."""
        self._settings.setdefault(player, {})[setting] = value
        self._save()
        self._evaluate(player)

    def status(self, player: str) -> PlayerStatus:
        """Return the current result for a player."""
        return self._statuses.get(player, PlayerStatus())

    def stat_today(self, stat: str) -> int:
        """Return a video count for today."""
        return self._today[stat]

    def stat_total(self, stat: str) -> int:
        """Return a video count since installation."""
        return self._totals[stat]

    def watch_minutes(self, player: str) -> int:
        """Return today's watch time of a player."""
        return int(self._watch_seconds.get(player, 0) // 60)

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
    def _interval(self, _now: datetime) -> None:
        self._roll_over_day()
        self._count_watch_time()
        self.async_evaluate_all()

    @callback
    def _roll_over_day(self) -> None:
        today = dt_util.now().date().isoformat()
        if today == self._day:
            return
        self._day = today
        self._seen = []
        self._today = dict.fromkeys(STATS, 0)
        self._watch_seconds = {}
        self._save()
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _count_watch_time(self) -> None:
        now = time.monotonic()
        elapsed = min(now - self._last_tick, MAX_TICK_SECONDS)
        self._last_tick = now
        changed = False
        for player in self.players:
            state = self.hass.states.get(player)
            if state is None or state.state != STATE_PLAYING:
                continue
            before = self.watch_minutes(player)
            self._watch_seconds[player] = self._watch_seconds.get(player, 0) + elapsed
            changed |= self.watch_minutes(player) != before
        if changed:
            self._save()
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def _count_video(self, key: str, blocked: bool, valuable: bool) -> None:
        """Count each video once per day, with the result it first had."""
        if key in self._seen:
            return
        self._seen.append(key)
        counted = [STAT_VIDEOS, STAT_SKIPPED if blocked else STAT_APPROVED]
        if valuable:
            counted.append(STAT_VALUABLE)
        for stat in counted:
            self._today[stat] += 1
            self._totals[stat] += 1
        self._save()
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY_SECONDS)

    @callback
    def _data(self) -> dict:
        return {
            "age": self.age,
            "enabled": self.enabled,
            "settings": self._settings,
            "ratings": self._ratings,
            "events": self._events,
            "day": self._day,
            "seen": self._seen,
            "today": self._today,
            "totals": self._totals,
            "watch_seconds": self._watch_seconds,
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
                    self._system_prompt,
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

    async def _async_stop_video(self, player: str) -> None:
        """Pause and optionally go back to the start; not every player can seek."""
        calls = [("media_pause", {})]
        if self.setting(player, SETTING_SEEK_TO_START):
            calls.append(("media_seek", {"seek_position": 0}))
        for service, data in calls:
            try:
                await self.hass.services.async_call(
                    "media_player", service, {"entity_id": player, **data}, blocking=True
                )
            except HomeAssistantError as err:
                _LOGGER.debug("%s auf %s fehlgeschlagen: %s", service, player, err)

    @callback
    def _pause(self, player: str, video: engine.Video, rating: dict | None) -> None:
        # A player reports several updates per play, each must not count twice.
        now = time.monotonic()
        if now - self._last_pause.get(player, -PAUSE_DEBOUNCE_SECONDS) < PAUSE_DEBOUNCE_SECONDS:
            return
        self._last_pause[player] = now
        self.hass.async_create_task(self._async_stop_video(player))
        self._log_event("pausiert", video, rating)
        self.hass.bus.async_fire(
            EVENT_PAUSED,
            {
                "entity_id": player,
                "title": video.title,
                "min_age": rating["min_age"] if rating else None,
            },
        )
        _LOGGER.info("Pausiert auf %s: %r", player, video.title)

    def _block_reason(self, player: str, rating: dict, age: int) -> str | None:
        if not engine.is_allowed(rating["min_age"], age):
            return BLOCK_AGE
        if self.setting(player, SETTING_STRICT) and rating.get("source") != engine.SOURCE_SUBTITLES:
            return BLOCK_NO_SUBTITLES
        if self.setting(player, SETTING_BLOCK_PROFANITY) and rating.get("profanity"):
            return BLOCK_PROFANITY
        if self.setting(player, SETTING_REQUIRE_PEDAGOGY) and not rating.get("valuable"):
            return BLOCK_PEDAGOGY
        return None

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
        key = f"{title}\n{channel}\n{self._prompt_id}"
        self._ensure_rated(key, video)
        # Background tasks start eagerly, so the rating may exist by now.
        rating = self._ratings.get(key)
        if rating is None and key in self._pending:
            self._publish(player, PlayerStatus(STATUS_CHECKING, title, channel, age))
            return
        if rating is None and not self.setting(player, SETTING_STRICT):
            self._publish(player, PlayerStatus(STATUS_UNCHECKED, title, channel, age))
            return
        if rating is None:
            self._count_video(key, True, False)
            if state.state == STATE_PLAYING:
                self._pause(player, video, None)
            self._publish(
                player,
                PlayerStatus(STATUS_BLOCKED, title, channel, age, block_reason=BLOCK_UNCHECKED),
            )
            return
        block_reason = self._block_reason(player, rating, age)
        self._count_video(key, block_reason is not None, rating.get("valuable", False))
        if block_reason and state.state == STATE_PLAYING:
            self._pause(player, video, rating)
        self._publish(
            player,
            PlayerStatus(
                STATUS_BLOCKED if block_reason else STATUS_FREE,
                title,
                channel,
                age,
                engine.Rating(**rating),
                block_reason,
            ),
        )
