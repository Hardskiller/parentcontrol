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
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    BLOCK_CHANNEL,
    BLOCK_NO_SUBTITLES,
    BLOCK_PEDAGOGY,
    BLOCK_PROFANITY,
    BLOCK_SHORT,
    BLOCK_UNCHECKED,
    CONF_AGE,
    CONF_AGE_PROMPT,
    CONF_ALLOWED,
    CONF_BLOCKED,
    CONF_DEVICE_AGES,
    CONF_DEVICE_ALLOWED,
    CONF_DEVICE_BLOCKED,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_PEDAGOGY_PROMPT,
    CONF_PLAYERS,
    DOMAIN,
    EVENT_PAUSED,
    HEALTH,
    HEALTH_INTERVAL_SECONDS,
    HEALTH_OLLAMA,
    HEALTH_YTDLP,
    HISTORY_SIZE,
    LIST_ALLOWED,
    LIST_BLOCKED,
    LOOSENING_VALUES,
    MAX_EVENTS,
    PAUSE_DEBOUNCE_SECONDS,
    REPAIR_AFTER_SECONDS,
    RETRY_SECONDS,
    SETTING_BLOCK_PROFANITY,
    SETTING_BLOCK_SHORTS,
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_SEEK_TO_START,
    SETTING_SKIP_CHECKS,
    SETTING_STRICT,
    SETTING_DEFAULTS,
    SHORT_MAX_SECONDS,
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
from .pinlock import PinLock

_LOGGER = logging.getLogger(__name__)

INACTIVE_STATES = {STATE_OFF, STATE_STANDBY, STATE_UNAVAILABLE, STATE_UNKNOWN}
SAVE_DELAY_SECONDS = 5
ENFORCE_INTERVAL = timedelta(seconds=3)
MAX_TICK_SECONDS = 30
HEALTH_TIMEOUT = 10


@dataclass(frozen=True)
class PlayerStatus:
    """Current result for one media player."""

    status: str = STATUS_IDLE
    title: str | None = None
    channel: str | None = None
    age: int | None = None
    rating: engine.Rating | None = None
    block_reason: str | None = None
    list_state: str | None = None
    short: bool = False


class Monitor:
    """Rates what the configured players show and enforces the result."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, lock: PinLock) -> None:
        self.hass = hass
        self.entry = entry
        self.lock = lock
        self.players: list[str] = entry.options[CONF_PLAYERS]
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.age: int = entry.data[CONF_AGE]
        self.enabled = True
        self._device_ages: dict[str, int] = entry.options.get(CONF_DEVICE_AGES, {})
        self._settings: dict[str, dict[str, bool]] = {}
        self._allowed = engine.parse_allowed(
            entry.options.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS)
        )
        self._blocked = engine.parse_blocked(entry.options.get(CONF_BLOCKED, ""))
        self._device_allowed = {
            player: engine.parse_allowed(text)
            for player, text in entry.options.get(CONF_DEVICE_ALLOWED, {}).items()
        }
        self._device_blocked = {
            player: engine.parse_blocked(text)
            for player, text in entry.options.get(CONF_DEVICE_BLOCKED, {}).items()
        }
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
        self._shorts: dict[str, bool] = {}
        self._history: dict[str, list[dict]] = {}
        self.health: dict[str, bool | None] = dict.fromkeys(HEALTH)
        self._down_since: dict[str, float] = {}
        self._last_health_check = -HEALTH_INTERVAL_SECONDS

    async def async_load(self) -> None:
        """Restore age, switch, ratings, statistics and the protocol."""
        data = await self._store.async_load() or {}
        self.age = data.get("age", self.age)
        self.enabled = data.get("enabled", True)
        self._settings = data.get("settings", {})
        self._ratings = data.get("ratings", {})
        self._events = data.get("events", [])
        self._totals |= data.get("totals", {})
        self._shorts = data.get("shorts", {})
        self._history = data.get("history", {})
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
        """Return a checkbox of a player; most start switched off."""
        return self._settings.get(player, {}).get(setting, SETTING_DEFAULTS.get(setting, False))

    @staticmethod
    def loosens_setting(setting: str, value: bool) -> bool:
        """Return whether a checkbox change weakens the protection."""
        return value == LOOSENING_VALUES.get(setting, False)

    def device_age(self, player: str) -> int:
        """Return the age that applies to a player."""
        return self._device_ages.get(player, self.age)

    def history(self, player: str) -> list[dict]:
        """Return the latest videos of a player, newest first."""
        return self._history.get(player, [])

    @callback
    def async_set_setting(self, player: str, setting: str, value: bool) -> None:
        """Change a checkbox of a player."""
        self._settings.setdefault(player, {})[setting] = value
        self._save()
        self._evaluate(player)

    @callback
    def async_set_device_age(self, player: str, age: int) -> None:
        """Give a player its own age; reloads the entry."""
        ages = {**self._device_ages, player: age}
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_DEVICE_AGES: ages}
        )

    @callback
    def async_remove_channel(self, allow: bool, channel: str, player: str | None) -> None:
        """Remove a channel from the allowed or the blocked list."""
        options = {**self.entry.options}
        if player:
            key = CONF_DEVICE_ALLOWED if allow else CONF_DEVICE_BLOCKED
            lists = dict(options.get(key, {}))
            lists[player] = engine.remove_channel(lists.get(player, ""), channel)
            options[key] = lists
        elif allow:
            options[CONF_ALLOWED] = engine.remove_channel(
                options.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS), channel
            )
        else:
            options[CONF_BLOCKED] = engine.remove_channel(options.get(CONF_BLOCKED, ""), channel)
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    @callback
    def async_list_channel(
        self, allow: bool, channel: str, age: int | None, player: str | None
    ) -> None:
        """Add a channel to one list and remove it from the opposite one."""
        options = {**self.entry.options}
        if player:
            allowed = dict(options.get(CONF_DEVICE_ALLOWED, {}))
            blocked = dict(options.get(CONF_DEVICE_BLOCKED, {}))
            target, opposite = (allowed, blocked) if allow else (blocked, allowed)
            target[player] = engine.add_channel(
                target.get(player, ""), channel, age if allow else None
            )
            opposite[player] = engine.remove_channel(opposite.get(player, ""), channel)
            options[CONF_DEVICE_ALLOWED] = allowed
            options[CONF_DEVICE_BLOCKED] = blocked
        else:
            target_key, opposite_key = (
                (CONF_ALLOWED, CONF_BLOCKED) if allow else (CONF_BLOCKED, CONF_ALLOWED)
            )
            lists = {
                CONF_ALLOWED: options.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS),
                CONF_BLOCKED: options.get(CONF_BLOCKED, ""),
            }
            options[target_key] = engine.add_channel(
                lists[target_key], channel, age if allow else None
            )
            options[opposite_key] = engine.remove_channel(lists[opposite_key], channel)
        self.hass.config_entries.async_update_entry(self.entry, options=options)

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
        self._check_health()
        self.async_evaluate_all()

    @callback
    def _check_health(self) -> None:
        now = time.monotonic()
        if now - self._last_health_check >= HEALTH_INTERVAL_SECONDS:
            self._last_health_check = now
            self.entry.async_create_background_task(
                self.hass, self._async_check_ollama(), f"{DOMAIN} ollama check"
            )
        for name, since in self._down_since.items():
            if now - since >= REPAIR_AFTER_SECONDS:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"{name}_down",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=f"{name}_down",
                )

    async def _async_check_ollama(self) -> None:
        url = f"{self.entry.data[CONF_OLLAMA_URL].rstrip('/')}/api/tags"
        try:
            async with async_get_clientsession(self.hass).get(
                url, timeout=HEALTH_TIMEOUT
            ) as response:
                response.raise_for_status()
        except (OSError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Ollama nicht erreichbar: %s", err)
            self._set_health(HEALTH_OLLAMA, False)
        else:
            self._set_health(HEALTH_OLLAMA, True)

    @callback
    def _set_health(self, name: str, healthy: bool) -> None:
        if healthy:
            self._down_since.pop(name, None)
            ir.async_delete_issue(self.hass, DOMAIN, f"{name}_down")
        else:
            self._down_since.setdefault(name, time.monotonic())
        if self.health[name] != healthy:
            self.health[name] = healthy
            async_dispatcher_send(self.hass, self.signal)

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

    async def async_save_now(self) -> None:
        """Write pending changes at once."""
        await self._store.async_save(self._data())

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
            "shorts": self._shorts,
            "history": self._history,
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
            self._record(player, status)
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def _record(self, player: str, status: PlayerStatus) -> None:
        """Keep the latest videos; a new result updates the newest entry."""
        if not status.title:
            return
        history = self._history.setdefault(player, [])
        rating = status.rating
        entry = {
            "zeit": dt_util.now().isoformat(timespec="seconds"),
            "titel": status.title,
            "kanal": status.channel,
            "status": status.status,
            "sperrgrund": status.block_reason,
            "mindestalter": rating.min_age if rating else None,
            "grund": rating.reason if rating else None,
            "paedagogisch_wertvoll": rating.valuable if rating else None,
            "schimpfwoerter": rating.profanity if rating else None,
            "short": status.short,
        }
        if history and (history[0]["titel"], history[0]["kanal"]) == (status.title, status.channel):
            history[0] = {**entry, "zeit": history[0]["zeit"]}
        else:
            history.insert(0, entry)
            del history[HISTORY_SIZE:]
        self._save()

    def _may_start(self, key: str) -> bool:
        if key in self._pending:
            return False
        failed_at = self._failed.get(key)
        return not failed_at or time.monotonic() - failed_at >= RETRY_SECONDS

    @callback
    def _ensure_rated(self, key: str, video_key: str, video: engine.Video) -> None:
        """Start a check unless there is a rating or a recent failure."""
        if key in self._ratings or not self._may_start(key):
            return
        self._pending.add(key)
        self.entry.async_create_background_task(
            self.hass, self._async_rate(key, video_key, video), f"{DOMAIN} rate {video.title}"
        )

    @callback
    def _ensure_format(self, video_key: str, video: engine.Video) -> None:
        """Only ask YouTube whether a video is a Short."""
        if video_key in self._shorts or not self._may_start(video_key):
            return
        self._pending.add(video_key)
        self.entry.async_create_background_task(
            self.hass, self._async_lookup(video_key, video), f"{DOMAIN} lookup {video.title}"
        )

    async def _async_fetch(self, video_key: str, video: engine.Video) -> engine.Metadata:
        """Look the video up and pause a Short before the model answers."""
        meta = await self.hass.async_add_executor_job(engine.fetch_metadata, video)
        self._set_health(HEALTH_YTDLP, not meta.failed)
        if meta.failed:
            self._failed[video_key] = time.monotonic()
        elif meta.video_id:
            self._shorts[video_key] = meta.short
            self._save()
        self.async_evaluate_all()
        return meta

    async def _async_lookup(self, video_key: str, video: engine.Video) -> None:
        try:
            async with self._semaphore:
                await self._async_fetch(video_key, video)
        finally:
            self._pending.discard(video_key)
        self.async_evaluate_all()

    async def _async_rate(self, key: str, video_key: str, video: engine.Video) -> None:
        try:
            async with self._semaphore:
                meta = await self._async_fetch(video_key, video)
                rating = await self.hass.async_add_executor_job(
                    engine.rate,
                    video,
                    self.entry.data[CONF_OLLAMA_URL],
                    self.entry.options[CONF_MODEL],
                    self._system_prompt,
                    meta,
                )
        except (OSError, ValueError, KeyError) as err:
            _LOGGER.warning("Einstufung fehlgeschlagen für %r: %s", video.title, err)
            self._failed[key] = time.monotonic()
            self._set_health(HEALTH_OLLAMA, False)
            self._log_event("nicht_geprueft", video, None)
        else:
            self._failed.pop(key, None)
            self._set_health(HEALTH_OLLAMA, True)
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

    def _is_blocked_channel(self, player: str, channel: str) -> bool:
        return channel in self._blocked or channel in self._device_blocked.get(player, set())

    def _is_allowed_channel(self, player: str, channel: str, age: int) -> bool:
        device = self._device_allowed.get(player, {})
        min_age = device[channel] if channel in device else self._allowed.get(channel)
        return min_age is not None and age >= min_age

    def _block_reason(
        self, player: str, rating: dict, age: int, listed: bool
    ) -> str | None:
        """Listed channels only fail on age and swear words."""
        if not engine.is_allowed(rating["min_age"], age):
            return BLOCK_AGE
        if listed and not self.setting(player, SETTING_BLOCK_PROFANITY):
            return None
        if listed:
            return BLOCK_PROFANITY if rating.get("profanity") else None
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
        age = self.device_age(player)
        if not self.enabled:
            self._publish(player, PlayerStatus(STATUS_DISABLED, title, channel, age))
            return
        duration = attributes.get("media_duration")
        video = engine.Video(title, channel, duration)
        video_key = f"{title}\n{channel}"
        key = f"{video_key}\n{self._prompt_id}"
        normalized_channel = engine.normalize(channel)
        if self._is_blocked_channel(player, normalized_channel):
            self._count_video(key, True, False)
            if state.state == STATE_PLAYING:
                self._pause(player, video, None)
            self._publish(
                player,
                PlayerStatus(
                    STATUS_BLOCKED,
                    title,
                    channel,
                    age,
                    block_reason=BLOCK_CHANNEL,
                    list_state=LIST_BLOCKED,
                ),
            )
            return
        listed = self._is_allowed_channel(player, normalized_channel, age)
        list_state = LIST_ALLOWED if listed else None
        # Shorts last three minutes at most and are blocked on every channel.
        maybe_short = self.setting(player, SETTING_BLOCK_SHORTS) and not (
            duration and duration > SHORT_MAX_SECONDS
        )
        if maybe_short and self._shorts.get(video_key):
            self._count_video(key, True, False)
            if state.state == STATE_PLAYING:
                self._pause(player, video, None)
            self._publish(
                player,
                PlayerStatus(
                    STATUS_BLOCKED,
                    title,
                    channel,
                    age,
                    block_reason=BLOCK_SHORT,
                    list_state=list_state,
                    short=True,
                ),
            )
            return
        skip = listed and self.setting(player, SETTING_SKIP_CHECKS)
        if maybe_short:
            if skip or key in self._ratings:
                # Rated before Shorts were recognized, or no rating needed.
                self._ensure_format(video_key, video)
            else:
                self._ensure_rated(key, video_key, video)
            if self._shorts.get(video_key):
                # The eagerly started lookup already found a Short.
                self._evaluate(player)
                return
        if skip:
            self._count_video(key, False, False)
            self._publish(
                player,
                PlayerStatus(
                    STATUS_FREE,
                    title,
                    channel,
                    age,
                    engine.Rating(0, "Kanal ist freigegeben.", engine.SOURCE_ALLOWLIST),
                    list_state=list_state,
                ),
            )
            return
        self._ensure_rated(key, video_key, video)
        # Background tasks start eagerly, so the rating may exist by now.
        rating = self._ratings.get(key)
        if rating is None and key in self._pending:
            self._publish(player, PlayerStatus(STATUS_CHECKING, title, channel, age))
            return
        if rating is None and (listed or not self.setting(player, SETTING_STRICT)):
            self._publish(
                player,
                PlayerStatus(STATUS_UNCHECKED, title, channel, age, list_state=list_state),
            )
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
        block_reason = self._block_reason(player, rating, age, listed)
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
                list_state,
            ),
        )
