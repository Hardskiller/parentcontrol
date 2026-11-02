"""Rules of one or more child profiles; on a shared device the strictest wins."""
from __future__ import annotations

from dataclasses import dataclass

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
