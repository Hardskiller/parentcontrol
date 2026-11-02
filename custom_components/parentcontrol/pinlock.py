"""PIN lock that guards every change weakening the protection."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError, UnknownUser
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN,
    EVENT_PIN_FAILED,
    PIN_ATTEMPTS,
    PIN_LOCKOUT_SECONDS,
    PIN_PATTERN,
    UNLOCK_SECONDS,
)

HASH_ITERATIONS = 200_000


def valid_pin(pin: str) -> bool:
    """Return whether a PIN has 4 to 8 digits."""
    return re.fullmatch(PIN_PATTERN, pin) is not None


def hash_pin(pin: str) -> str:
    """Hash a PIN with a random salt; runs in the executor."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), HASH_ITERATIONS)
    return f"{salt}${digest.hex()}"


def check_pin(pin: str, stored: str) -> bool:
    """Compare a PIN with a stored hash; runs in the executor."""
    salt, _, expected = stored.partition("$")
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), HASH_ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected)


class PinLock:
    """Open for a few minutes after the right PIN.

    It lives in hass.data, because changing a list reloads the config entry
    and must not lock the integration again.
    """

    def __init__(self, hass: HomeAssistant, signal: str) -> None:
        self.hass = hass
        self.signal = signal
        self.pin_hash: str | None = None
        self._open_until = 0.0
        self._relock: CALLBACK_TYPE | None = None
        self._failures = 0
        self._lockouts = 0
        self._blocked_until = 0.0

    @property
    def is_open(self) -> bool:
        """Return whether a PIN was entered recently."""
        return time.monotonic() < self._open_until

    @property
    def open_seconds(self) -> int:
        """Return how long the lock stays open."""
        return max(0, int(self._open_until - time.monotonic()))

    @property
    def blocked_seconds(self) -> int:
        """Return how long no PIN can be entered."""
        return max(0, int(self._blocked_until - time.monotonic()))

    async def async_unlock(self, code: str | None, context: Context | None) -> None:
        """Open the lock or count a failed attempt."""
        if self.blocked_seconds:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="pin_blocked",
                translation_placeholders={"minutes": str(self.blocked_seconds // 60 + 1)},
            )
        if not self.pin_hash:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_pin")
        if code and await self.hass.async_add_executor_job(check_pin, code, self.pin_hash):
            self._failures = 0
            self._lockouts = 0
            self._extend()
            return
        self._failures += 1
        self.hass.bus.async_fire(EVENT_PIN_FAILED, {"attempt": self._failures}, context=context)
        if self._failures >= PIN_ATTEMPTS:
            # 15 minutes, then twice as long after every further lockout.
            self._blocked_until = time.monotonic() + PIN_LOCKOUT_SECONDS * 2**self._lockouts
            self._lockouts += 1
            self._failures = 0
        async_dispatcher_send(self.hass, self.signal)
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="wrong_pin")

    @callback
    def async_lock(self) -> None:
        """Close the lock at once."""
        self._open_until = 0.0
        self._cancel()
        async_dispatcher_send(self.hass, self.signal)

    async def async_authorize(self, context: Context | None, loosens: bool) -> None:
        """Reject a change by a non-admin user while locked."""
        if not loosens or context is None or context.user_id is None:
            # Stricter changes are always fine, automations have no user.
            return
        user = await self.hass.auth.async_get_user(context.user_id)
        if user is None:
            raise UnknownUser(context=context, user_id=context.user_id)
        if user.is_admin:
            return
        if not self.is_open:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="locked")
        self._extend()

    @callback
    def async_unload(self) -> None:
        """Stop the timer."""
        self._cancel()

    @callback
    def _extend(self) -> None:
        self._open_until = time.monotonic() + UNLOCK_SECONDS
        self._cancel()
        self._relock = async_call_later(self.hass, UNLOCK_SECONDS, self._expired)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _expired(self, _now: datetime) -> None:
        self._relock = None
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _cancel(self) -> None:
        if self._relock:
            self._relock()
            self._relock = None
