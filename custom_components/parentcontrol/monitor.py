"""Watches media players and pauses videos that fail the check."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
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
    BLOCK_NO_DATA,
    BLOCK_NO_SUBTITLES,
    BLOCK_PEDAGOGY,
    BLOCK_PROFANITY,
    BLOCK_SHORT,
    BLOCK_UNCHECKED,
    CONF_AGE,
    CONF_AGE_PROMPT,
    CONF_ALLOWED,
    CONF_ALLOWED_WORDS,
    CONF_BLOCKED,
    CONF_DEVICE_PROFILES,
    CONF_HISTORY_SIZE,
    CONF_MODEL,
    CONF_NAME,
    CONF_OLLAMA_URL,
    CONF_PEDAGOGY_PROMPT,
    CONF_PLAYERS,
    CONF_PROFILE_ALLOWED,
    CONF_PROFILE_BLOCKED,
    CONF_PROFILE_WORDS,
    CONF_PROFILES,
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
    NO_DATA_GRACE_SECONDS,
    PAUSE_DEBOUNCE_SECONDS,
    PROFILE_SETTINGS,
    REPAIR_AFTER_SECONDS,
    RETRY_SECONDS,
    SELECT_AUTO,
    SELECT_UNRESTRICTED,
    SETTING_DEFAULTS,
    SETTING_INHERIT_CHANNELS,
    SETTING_INHERIT_WORDS,
    SETTING_SEEK_TO_START,
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
    STATUS_UNRESTRICTED,
    STORAGE_VERSION,
)
from .pinlock import PinLock
from .profiles import Rules, profile_rules

_LOGGER = logging.getLogger(__name__)

INACTIVE_STATES = {STATE_OFF, STATE_STANDBY, STATE_UNAVAILABLE, STATE_UNKNOWN}
# Fire TV and Android TV over ADB only report the app id or the source.
APP_ATTRIBUTES = ("app_name", "app_id", "source")
SAVE_DELAY_SECONDS = 5
ENFORCE_INTERVAL = timedelta(seconds=3)
MAX_TICK_SECONDS = 30
HEALTH_TIMEOUT = 10
LIST_WORDS = "words"


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
    block_text: str | None = None
    profiles: tuple[str, ...] = ()


def block_text(reason: str | None, age: int | None, rating: engine.Rating | None) -> str | None:
    """Explain a block in one sentence; for swear words with the words found."""
    if reason is None:
        return None
    if reason == BLOCK_AGE and rating:
        text = f"Mindestalter {rating.min_age} liegt über dem Alter {age}."
        return f"{text} {rating.reason}".strip()
    if reason == BLOCK_PROFANITY:
        words = rating.profanity_words if rating else []
        if words:
            return f"Schimpfwörter erkannt: {', '.join(words)}."
        return "Schimpfwörter erkannt, vom Modell ohne einzelne Wörter gemeldet."
    if reason == BLOCK_PEDAGOGY:
        return f"Nicht pädagogisch wertvoll. {rating.pedagogy_reason if rating else ''}".strip()
    return BLOCK_TEXTS.get(reason, reason)


BLOCK_TEXTS = {
    BLOCK_CHANNEL: "Der Kanal steht auf der Sperrliste.",
    BLOCK_SHORT: "Shorts sind für dieses Profil gesperrt.",
    BLOCK_NO_SUBTITLES: "Strenge Bewertung: Ohne Untertitel ist keine sichere Einstufung möglich.",
    BLOCK_UNCHECKED: "Strenge Bewertung: Die Prüfung ist fehlgeschlagen.",
    BLOCK_NO_DATA: "Strenge Bewertung: Das Gerät meldet keinen Videotitel.",
}


def filter_words(rating: dict, rules: Rules) -> dict:
    """Drop allowed swear words; a report without words stays a report."""
    words = rating.get("profanity_words") or []
    if not words:
        return rating
    remaining = rules.offending_words(words)
    return {**rating, "profanity_words": remaining, "profanity": bool(remaining)}


class Monitor:
    """Rates what the configured players show and enforces the result."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, lock: PinLock) -> None:
        self.hass = hass
        self.entry = entry
        self.lock = lock
        options = entry.options
        self.players: list[str] = options[CONF_PLAYERS]
        self.profiles: dict[str, dict] = options[CONF_PROFILES]
        self.device_profiles: dict[str, list[str]] = options[CONF_DEVICE_PROFILES]
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.enabled = True
        self._device_settings: dict[str, dict[str, bool]] = {}
        self._profile_settings: dict[str, dict] = {}
        self._selection: dict[str, str] = {}
        self._system_prompt = engine.build_system_prompt(
            options.get(CONF_AGE_PROMPT, engine.DEFAULT_AGE_PROMPT),
            options.get(CONF_PEDAGOGY_PROMPT, engine.DEFAULT_PEDAGOGY_PROMPT),
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
        self._no_data_since: dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(1)
        self._unsubscribe: list[Callable[[], None]] = []
        self._day = dt_util.now().date().isoformat()
        self._seen: list[str] = []
        self._today = dict.fromkeys(STATS, 0)
        self._totals = dict.fromkeys(STATS, 0)
        self._watch_seconds: dict[str, float] = {}
        self._profile_seconds: dict[str, float] = {}
        self._last_tick = time.monotonic()
        self._shorts: dict[str, bool] = {}
        self._history: dict[str, list[dict]] = {}
        self._history_size = int(options.get(CONF_HISTORY_SIZE, HISTORY_SIZE))
        self.health: dict[str, bool | None] = dict.fromkeys(HEALTH)
        self._down_since: dict[str, float] = {}
        self._last_health_check = -HEALTH_INTERVAL_SECONDS

    async def async_load(self) -> None:
        """Restore switches, profiles, ratings, statistics and the protocol."""
        data = await self._store.async_load() or {}
        self.enabled = data.get("enabled", True)
        self._device_settings = data.get("device_settings", {})
        self._profile_settings = data.get("profile_settings", {})
        self._selection = {
            player: value
            for player, value in data.get("selection", {}).items()
            if value in (SELECT_AUTO, SELECT_UNRESTRICTED) or value in self.profiles
        }
        self._ratings = data.get("ratings", {})
        self._events = data.get("events", [])
        self._totals |= data.get("totals", {})
        self._shorts = data.get("shorts", {})
        # A smaller size in the options also shortens the stored lists.
        self._history = {
            player: videos[: self._history_size]
            for player, videos in data.get("history", {}).items()
        }
        if data.get("day") == self._day:
            self._seen = data.get("seen", [])
            self._today |= data.get("today", {})
            self._watch_seconds = data.get("watch_seconds", {})
            self._profile_seconds = data.get("profile_seconds", {})

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

    # Settings of devices and profiles

    def device_setting(self, player: str, setting: str) -> bool:
        """Return a checkbox of a player."""
        return self._device_settings.get(player, {}).get(setting, False)

    @callback
    def async_set_device_setting(self, player: str, setting: str, value: bool) -> None:
        """Change a checkbox of a player."""
        self._device_settings.setdefault(player, {})[setting] = value
        self._save()

    def profile_age(self, profile: str) -> int:
        """Return the age of a child; the options hold only the start value."""
        stored = self._profile_settings.get(profile, {}).get(CONF_AGE)
        return stored if stored is not None else self.profiles[profile][CONF_AGE]

    def profile_setting(self, profile: str, setting: str) -> bool:
        """Return a rule switch of a child."""
        return self._profile_settings.get(profile, {}).get(
            setting, SETTING_DEFAULTS.get(setting, False)
        )

    @staticmethod
    def loosens_setting(setting: str, value: bool) -> bool:
        """Return whether a checkbox change weakens the protection."""
        return value == LOOSENING_VALUES.get(setting, False)

    @callback
    def async_set_profile_age(self, profile: str, age: int) -> None:
        """Change the age of a child."""
        self._profile_settings.setdefault(profile, {})[CONF_AGE] = age
        self._save()
        self.async_evaluate_all()

    @callback
    def async_set_profile_setting(self, profile: str, setting: str, value: bool) -> None:
        """Change a rule switch of a child."""
        self._profile_settings.setdefault(profile, {})[setting] = value
        self._save()
        self.async_evaluate_all()

    def profile_name(self, profile: str) -> str:
        """Return the name of a profile."""
        return self.profiles[profile][CONF_NAME]

    def find_profile(self, value: str) -> str | None:
        """Return a profile by its id or its name, ignoring case."""
        if value in self.profiles:
            return value
        wanted = value.casefold()
        return next(
            (pid for pid, profile in self.profiles.items() if profile[CONF_NAME].casefold() == wanted),
            None,
        )

    # Who is watching

    def selection(self, player: str) -> str:
        """Return the selection of a player: auto, a profile id or unrestricted."""
        return self._selection.get(player, SELECT_AUTO)

    @callback
    def async_select(self, player: str, value: str) -> None:
        """Choose who is watching; it falls back to auto when the device turns off."""
        if value == SELECT_AUTO:
            self._selection.pop(player, None)
        else:
            self._selection[player] = value
        self._save()
        self._evaluate(player)
        async_dispatcher_send(self.hass, self.signal)

    def active_profiles(self, player: str) -> list[str]:
        """Return the profiles whose rules apply; none while unrestricted."""
        selection = self.selection(player)
        if selection == SELECT_UNRESTRICTED:
            return []
        if selection != SELECT_AUTO:
            return [selection]
        return [pid for pid in self.device_profiles.get(player, []) if pid in self.profiles]

    def rules(self, player: str) -> Rules | None:
        """Return the combined rules of a player, or None while unrestricted."""
        active = self.active_profiles(player)
        if not active:
            return None
        options = self.entry.options
        global_allowed = options.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS)
        global_blocked = options.get(CONF_BLOCKED, "")
        global_words = options.get(CONF_ALLOWED_WORDS, "")
        members = tuple(
            profile_rules(
                self.profile_age(pid),
                {setting: self.profile_setting(pid, setting) for setting in PROFILE_SETTINGS},
                options.get(CONF_PROFILE_ALLOWED, {}).get(pid, ""),
                options.get(CONF_PROFILE_BLOCKED, {}).get(pid, ""),
                options.get(CONF_PROFILE_WORDS, {}).get(pid, ""),
                global_allowed,
                global_blocked,
                global_words,
                self.profile_setting(pid, SETTING_INHERIT_CHANNELS),
                self.profile_setting(pid, SETTING_INHERIT_WORDS),
            )
            for pid in active
        )
        return Rules(tuple(active), members)

    # Lists

    def lists(self, profile: str | None = None) -> dict[str, list]:
        """Return the allowed and blocked channels and the allowed words."""
        options = self.entry.options
        if profile:
            allowed = options.get(CONF_PROFILE_ALLOWED, {}).get(profile, "")
            blocked = options.get(CONF_PROFILE_BLOCKED, {}).get(profile, "")
            words = options.get(CONF_PROFILE_WORDS, {}).get(profile, "")
        else:
            allowed = options.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS)
            blocked = options.get(CONF_BLOCKED, "")
            words = options.get(CONF_ALLOWED_WORDS, "")
        return {
            "freigegeben": engine.list_entries(allowed, with_age=True),
            "gesperrt": engine.list_entries(blocked, with_age=False),
            "erlaubte_woerter": [line.strip() for line in words.splitlines() if line.strip()],
        }

    def _list_texts(self, profile: str | None) -> tuple[dict, dict[str, str]]:
        """Return the options and the editable texts of one scope."""
        options = {**self.entry.options}
        if profile:
            texts = {
                LIST_ALLOWED: options.get(CONF_PROFILE_ALLOWED, {}).get(profile, ""),
                LIST_BLOCKED: options.get(CONF_PROFILE_BLOCKED, {}).get(profile, ""),
                LIST_WORDS: options.get(CONF_PROFILE_WORDS, {}).get(profile, ""),
            }
        else:
            texts = {
                LIST_ALLOWED: options.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS),
                LIST_BLOCKED: options.get(CONF_BLOCKED, ""),
                LIST_WORDS: options.get(CONF_ALLOWED_WORDS, ""),
            }
        return options, texts

    @callback
    def _store_list_texts(self, options: dict, texts: dict[str, str], profile: str | None) -> None:
        """Write the texts back; this reloads the entry."""
        if profile:
            for key, name in (
                (CONF_PROFILE_ALLOWED, LIST_ALLOWED),
                (CONF_PROFILE_BLOCKED, LIST_BLOCKED),
                (CONF_PROFILE_WORDS, LIST_WORDS),
            ):
                options[key] = {**options.get(key, {}), profile: texts[name]}
        else:
            options[CONF_ALLOWED] = texts[LIST_ALLOWED]
            options[CONF_BLOCKED] = texts[LIST_BLOCKED]
            options[CONF_ALLOWED_WORDS] = texts[LIST_WORDS]
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    @callback
    def async_list_channel(
        self, allow: bool, channel: str, age: int | None, profile: str | None
    ) -> None:
        """Add a channel to one list and remove it from the opposite one."""
        options, texts = self._list_texts(profile)
        target, opposite = (LIST_ALLOWED, LIST_BLOCKED) if allow else (LIST_BLOCKED, LIST_ALLOWED)
        texts[target] = engine.add_channel(texts[target], channel, age if allow else None)
        texts[opposite] = engine.remove_channel(texts[opposite], channel)
        self._store_list_texts(options, texts, profile)

    @callback
    def async_remove_channel(self, allow: bool, channel: str, profile: str | None) -> None:
        """Remove a channel from the allowed or the blocked list."""
        options, texts = self._list_texts(profile)
        name = LIST_ALLOWED if allow else LIST_BLOCKED
        texts[name] = engine.remove_channel(texts[name], channel)
        self._store_list_texts(options, texts, profile)

    @callback
    def async_set_word(self, allow: bool, word: str, profile: str | None) -> None:
        """Add or remove an allowed swear word."""
        options, texts = self._list_texts(profile)
        change = engine.add_word if allow else engine.remove_word
        texts[LIST_WORDS] = change(texts[LIST_WORDS], word)
        self._store_list_texts(options, texts, profile)

    # Results

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

    def profile_watch_minutes(self, profile: str) -> int:
        """Return today's watch time of a child."""
        return int(self._profile_seconds.get(profile, 0) // 60)

    def history(self, player: str) -> list[dict]:
        """Return the latest videos of a player, newest first."""
        return self._history.get(player, [])

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
        player = event.data["entity_id"]
        old, new = event.data["old_state"], event.data["new_state"]
        turned_off = (
            old is not None
            and old.state not in INACTIVE_STATES
            and (new is None or new.state in INACTIVE_STATES)
        )
        if turned_off and self._selection.pop(player, None):
            # The choice of who is watching ends when the device turns off.
            self._save()
            async_dispatcher_send(self.hass, self.signal)
        self._evaluate(player)

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
        self._profile_seconds = {}
        # A choice of who is watching lasts one day at most.
        self._selection = {}
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
            # On a shared device the time counts for every child that may watch.
            for profile in self.active_profiles(player):
                before = self.profile_watch_minutes(profile)
                self._profile_seconds[profile] = self._profile_seconds.get(profile, 0) + elapsed
                changed |= self.profile_watch_minutes(profile) != before
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
            "enabled": self.enabled,
            "device_settings": self._device_settings,
            "profile_settings": self._profile_settings,
            "selection": self._selection,
            "ratings": self._ratings,
            "events": self._events,
            "day": self._day,
            "seen": self._seen,
            "today": self._today,
            "totals": self._totals,
            "watch_seconds": self._watch_seconds,
            "profile_seconds": self._profile_seconds,
            "shorts": self._shorts,
            "history": self._history,
        }

    @callback
    def _log_event(
        self, event: str, video: engine.Video, rating: dict | None, text: str | None = None
    ) -> None:
        self._events.append(
            {
                "at": time.time(),
                "event": event,
                "title": video.title,
                "channel": video.channel,
                "min_age": rating["min_age"] if rating else None,
                "reason": rating["reason"] if rating else None,
                "block_text": text,
                "swear_words": rating.get("profanity_words", []) if rating else [],
            }
        )
        del self._events[:-MAX_EVENTS]
        self._save()

    @callback
    def _publish(self, player: str, status: PlayerStatus) -> None:
        status = replace(
            status,
            block_text=block_text(status.block_reason, status.age, status.rating),
            profiles=tuple(self.active_profiles(player)),
        )
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
            "sperrtext": status.block_text,
            "mindestalter": rating.min_age if rating else None,
            "grund": rating.reason if rating else None,
            "paedagogisch_wertvoll": rating.valuable if rating else None,
            "schimpfwoerter": rating.profanity if rating else None,
            "schimpfwoerter_liste": rating.profanity_words if rating else [],
            "short": status.short,
            "profile": list(status.profiles),
            "profil_namen": [self.profile_name(pid) for pid in status.profiles],
        }
        if history and (history[0]["titel"], history[0]["kanal"]) == (status.title, status.channel):
            history[0] = {**entry, "zeit": history[0]["zeit"]}
        else:
            history.insert(0, entry)
            del history[self._history_size :]
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
        if self.device_setting(player, SETTING_SEEK_TO_START):
            calls.append(("media_seek", {"seek_position": 0}))
        for service, data in calls:
            try:
                await self.hass.services.async_call(
                    "media_player", service, {"entity_id": player, **data}, blocking=True
                )
            except HomeAssistantError as err:
                _LOGGER.debug("%s auf %s fehlgeschlagen: %s", service, player, err)

    @callback
    def _pause(
        self,
        player: str,
        video: engine.Video,
        rating: dict | None,
        reason: str,
        age: int,
    ) -> None:
        # A player reports several updates per play, each must not count twice.
        now = time.monotonic()
        if now - self._last_pause.get(player, -PAUSE_DEBOUNCE_SECONDS) < PAUSE_DEBOUNCE_SECONDS:
            return
        self._last_pause[player] = now
        self.hass.async_create_task(self._async_stop_video(player))
        text = block_text(reason, age, engine.Rating(**rating) if rating else None)
        self._log_event("pausiert", video, rating, text)
        profiles = self.active_profiles(player)
        self.hass.bus.async_fire(
            EVENT_PAUSED,
            {
                "entity_id": player,
                "title": video.title,
                "channel": video.channel,
                "min_age": rating["min_age"] if rating else None,
                "block_reason": reason,
                "block_text": text,
                "swear_words": rating.get("profanity_words", []) if rating else [],
                "profiles": [self.profile_name(pid) for pid in profiles],
            },
        )
        _LOGGER.info("Pausiert auf %s: %r (%s)", player, video.title, text)

    @callback
    def _handle_no_data(self, player: str, playing: bool, rules: Rules) -> None:
        """Strict rating pauses YouTube that never reports a title."""
        age = rules.age
        if not playing:
            self._no_data_since.pop(player, None)
        elif self.enabled and rules.strict:
            since = self._no_data_since.setdefault(player, time.monotonic())
            if time.monotonic() - since >= NO_DATA_GRACE_SECONDS:
                self._pause(player, engine.Video("YouTube ohne Titel"), None, BLOCK_NO_DATA, age)
                self._publish(
                    player, PlayerStatus(STATUS_NO_DATA, age=age, block_reason=BLOCK_NO_DATA)
                )
                return
        self._publish(player, PlayerStatus(STATUS_NO_DATA, age=age))

    @staticmethod
    def _block_reason(rules: Rules, rating: dict, listed: bool) -> str | None:
        """Listed channels only fail on age and swear words."""
        if not engine.is_allowed(rating["min_age"], rules.age):
            return BLOCK_AGE
        if listed and not rules.block_profanity:
            return None
        if listed:
            return BLOCK_PROFANITY if rating.get("profanity") else None
        if rules.strict and rating.get("source") != engine.SOURCE_SUBTITLES:
            return BLOCK_NO_SUBTITLES
        if rules.block_profanity and rating.get("profanity"):
            return BLOCK_PROFANITY
        if rules.require_pedagogy and not rating.get("valuable"):
            return BLOCK_PEDAGOGY
        return None

    @callback
    def _evaluate(self, player: str) -> None:
        state = self.hass.states.get(player)
        if state is None or state.state in INACTIVE_STATES:
            self._publish(player, PlayerStatus())
            return
        attributes = state.attributes
        app = " ".join(str(attributes.get(name) or "") for name in APP_ATTRIBUTES)
        if "youtube" not in app.lower():
            self._no_data_since.pop(player, None)
            self._publish(player, PlayerStatus())
            return
        rules = self.rules(player)
        title = attributes.get("media_title")
        channel = attributes.get("media_artist") or ""
        if rules is None:
            # Unrestricted: no check and no statistics for the children.
            self._no_data_since.pop(player, None)
            self._publish(player, PlayerStatus(STATUS_UNRESTRICTED, title, channel or None))
            return
        if not title:
            self._handle_no_data(player, state.state == STATE_PLAYING, rules)
            return
        self._no_data_since.pop(player, None)
        age = rules.age
        if not self.enabled:
            self._publish(player, PlayerStatus(STATUS_DISABLED, title, channel, age))
            return
        duration = attributes.get("media_duration")
        video = engine.Video(title, channel, duration)
        video_key = f"{title}\n{channel}"
        key = f"{video_key}\n{self._prompt_id}"
        normalized_channel = engine.normalize(channel)
        if rules.is_blocked(normalized_channel):
            self._count_video(key, True, False)
            if state.state == STATE_PLAYING:
                self._pause(player, video, None, BLOCK_CHANNEL, age)
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
        listed = rules.is_allowed(normalized_channel)
        list_state = LIST_ALLOWED if listed else None
        # Shorts last three minutes at most and are blocked on every channel.
        maybe_short = rules.block_shorts and not (duration and duration > SHORT_MAX_SECONDS)
        if maybe_short and self._shorts.get(video_key):
            self._count_video(key, True, False)
            if state.state == STATE_PLAYING:
                self._pause(player, video, None, BLOCK_SHORT, age)
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
        skip = listed and rules.skip_checks
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
        if rating is None and (listed or not rules.strict):
            self._publish(
                player,
                PlayerStatus(STATUS_UNCHECKED, title, channel, age, list_state=list_state),
            )
            return
        if rating is None:
            self._count_video(key, True, False)
            if state.state == STATE_PLAYING:
                self._pause(player, video, None, BLOCK_UNCHECKED, age)
            self._publish(
                player,
                PlayerStatus(STATUS_BLOCKED, title, channel, age, block_reason=BLOCK_UNCHECKED),
            )
            return
        rating = filter_words(rating, rules)
        block_reason = self._block_reason(rules, rating, listed)
        self._count_video(key, block_reason is not None, rating.get("valuable", False))
        if block_reason and state.state == STATE_PLAYING:
            self._pause(player, video, rating, block_reason, age)
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
