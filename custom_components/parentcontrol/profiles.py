"""Rules of one or more child profiles; on a shared device the strictest wins."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dt_time

from . import engine
from .const import (
    RULES,
    SETTING_BLOCK_PROFANITY,
    SETTING_BLOCK_SHORTS,
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_SKIP_CHECKS,
    SETTING_STRICT,
)


@dataclass(frozen=True)
class ProfileRules:
    """What one child may watch."""

    age: int
    settings: dict[str, bool]
    # Profile entries before global ones, global ones only when inherited.
    allowed: dict[str, int]
    blocked: frozenset[str]
    words: tuple[str, ...]


@dataclass(frozen=True)
class Rules:
    """The combined rules of the profiles active on a device."""

    profiles: tuple[str, ...]
    members: tuple[ProfileRules, ...]

    @property
    def age(self) -> int:
        """The youngest child counts."""
        return min(member.age for member in self.members)

    def _any(self, setting: str) -> bool:
        return any(member.settings[setting] for member in self.members)

    @property
    def require_pedagogy(self) -> bool:
        return self._any(SETTING_REQUIRE_PEDAGOGY)

    @property
    def block_profanity(self) -> bool:
        return self._any(SETTING_BLOCK_PROFANITY)

    @property
    def strict(self) -> bool:
        return self._any(SETTING_STRICT)

    @property
    def block_shorts(self) -> bool:
        return self._any(SETTING_BLOCK_SHORTS)

    @property
    def skip_checks(self) -> bool:
        """Skipping weakens the check, so every child must allow it."""
        return all(member.settings[SETTING_SKIP_CHECKS] for member in self.members)

    def is_blocked(self, channel: str) -> bool:
        """A block of any child counts."""
        return any(channel in member.blocked for member in self.members)

    def is_allowed(self, channel: str) -> bool:
        """Allowed only if every child may watch the channel at its age."""
        return all(
            channel in member.allowed and member.age >= member.allowed[channel]
            for member in self.members
        )

    def offending_words(self, words: list[str]) -> list[str]:
        """Words that are not allowed for every child."""
        return [
            word
            for word in words
            if not all(engine.word_allowed(word, list(member.words)) for member in self.members)
        ]


def profile_rules(
    age: int,
    settings: dict[str, bool],
    allowed: str,
    blocked: str,
    words: str,
    global_allowed: str,
    global_blocked: str,
    global_words: str,
    inherit_channels: bool,
    inherit_words: bool,
) -> ProfileRules:
    """Combine the lists of one profile with the global lists."""
    allowed_map = engine.parse_allowed(global_allowed) if inherit_channels else {}
    allowed_map |= engine.parse_allowed(allowed)
    patterns = engine.parse_words(words)
    if inherit_words:
        patterns += engine.parse_words(global_words)
    return ProfileRules(
        age,
        {setting: settings[setting] for setting in RULES},
        allowed_map,
        frozenset(engine.parse_blocked(global_blocked) | engine.parse_blocked(blocked)),
        tuple(patterns),
    )


MINUTES_PER_DAY = 24 * 60


def parse_time(value: str) -> int:
    """Return the minute of the day of "HH:MM"."""
    hours, _, minutes = value.partition(":")
    return int(hours) * 60 + int(minutes or 0)


def format_time(value: dt_time) -> str:
    """Store a time as "HH:MM"."""
    return f"{value.hour:02d}:{value.minute:02d}"


def window_minutes(start: str, end: str) -> set[int]:
    """Return the minutes of a day inside a window; it may cross midnight."""
    first, last = parse_time(start), parse_time(end)
    if first == last:
        return set(range(MINUTES_PER_DAY))
    if first < last:
        return set(range(first, last))
    return set(range(first, MINUTES_PER_DAY)) | set(range(last))


def in_window(start: str, end: str, minute: int) -> bool:
    """Return whether a minute of the day lies inside a window."""
    return minute in window_minutes(start, end)


def minutes_to_end(start: str, end: str, minute: int) -> int | None:
    """Minutes until the window closes; None for all day or outside."""
    if start == end or not in_window(start, end, minute):
        return None
    return (parse_time(end) - minute) % MINUTES_PER_DAY


def limit_loosens(old: int, new: int) -> bool:
    """A higher limit, or no limit instead of one, weakens the protection."""
    return old > 0 and (new == 0 or new > old)
