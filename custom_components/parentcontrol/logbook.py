"""Logbook entries for paused videos and wrong PINs."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_PAUSED, EVENT_PIN_FAILED


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe the events of ParentControl."""

    @callback
    def describe_paused(event: Event) -> dict[str, str]:
        age = event.data.get("min_age")
        suffix = f" (ab {age})" if age is not None else ""
        text = event.data.get("block_text")
        reason = f": {text}" if text else ""
        return {
            LOGBOOK_ENTRY_NAME: "ParentControl",
            LOGBOOK_ENTRY_MESSAGE: f"hat „{event.data.get('title')}“ pausiert{suffix}{reason}",
        }

    @callback
    def describe_pin_failed(event: Event) -> dict[str, str]:
        return {
            LOGBOOK_ENTRY_NAME: "ParentControl",
            LOGBOOK_ENTRY_MESSAGE: f"falscher PIN, Versuch {event.data.get('attempt')}",
        }

    async_describe_event(DOMAIN, EVENT_PAUSED, describe_paused)
    async_describe_event(DOMAIN, EVENT_PIN_FAILED, describe_pin_failed)
