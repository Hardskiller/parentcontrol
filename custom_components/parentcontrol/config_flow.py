"""Setup and options for ParentControl."""
from __future__ import annotations

import secrets
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import engine, player_name
from .const import (
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
    CONF_PERSON,
    CONF_PIN,
    CONF_PIN_HASH,
    CONF_PLAYERS,
    CONF_PROFILE,
    CONF_PROFILE_ALLOWED,
    CONF_PROFILE_BLOCKED,
    CONF_PROFILE_WORDS,
    CONF_PROFILES,
    CONF_WARN_MINUTES,
    DEFAULT_OLLAMA_URL,
    DOMAIN,
    HISTORY_SIZE,
    MAX_AGE,
    MAX_HISTORY_SIZE,
    WARN_MINUTES,
)
from .pinlock import hash_pin, valid_pin

TIMEOUT = aiohttp.ClientTimeout(total=10)
TEXT_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
PIN_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)
PERSON_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="person"))
AGE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=MAX_AGE, step=1, mode=selector.NumberSelectorMode.SLIDER
    )
)
DEFAULT_PROFILE_NAME = "Kind"


async def _async_models(hass: HomeAssistant, url: str) -> list[str]:
    """Return the models installed on the Ollama server."""
    session = async_get_clientsession(hass)
    async with session.get(f"{url.rstrip('/')}/api/tags", timeout=TIMEOUT) as response:
        response.raise_for_status()
        data = await response.json()
    return sorted(model["name"] for model in data.get("models", []))


def _new_profile_id() -> str:
    return secrets.token_hex(4)


def _profile_fields(name: str | None, person: str | None) -> dict:
    return {
        vol.Required(CONF_NAME, default=name or vol.UNDEFINED): str,
        vol.Optional(CONF_PERSON, description={"suggested_value": person}): PERSON_SELECTOR,
    }


def _profile(user_input: dict[str, Any], age: int) -> dict[str, Any]:
    return {
        CONF_NAME: user_input[CONF_NAME].strip(),
        CONF_PERSON: user_input.get(CONF_PERSON) or None,
        CONF_AGE: age,
    }


def _list_form(allowed: str, blocked: str, words: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_ALLOWED, description={"suggested_value": allowed}): TEXT_SELECTOR,
            vol.Optional(CONF_BLOCKED, description={"suggested_value": blocked}): TEXT_SELECTOR,
            vol.Optional(CONF_ALLOWED_WORDS, description={"suggested_value": words}): TEXT_SELECTOR,
        }
    )


def _list_errors(user_input: dict[str, Any]) -> dict[str, str]:
    try:
        engine.parse_allowed(user_input.get(CONF_ALLOWED, ""))
    except ValueError:
        return {CONF_ALLOWED: "invalid_age"}
    return {}


def _player_fields(models: list[str], model: str | None, players: list[str]) -> dict:
    return {
        vol.Required(CONF_MODEL, default=model or vol.UNDEFINED): selector.SelectSelector(
            selector.SelectSelectorConfig(options=models, custom_value=True)
        ),
        vol.Required(CONF_PLAYERS, default=players): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="media_player", multiple=True)
        ),
    }


def _profile_choice(profiles: dict[str, dict], multiple: bool) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=pid, label=profile[CONF_NAME])
                for pid, profile in profiles.items()
            ],
            multiple=multiple,
        )
    )


class ParentControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Asks for the Ollama server, model, players, PIN and the first child."""

    VERSION = 1

    def __init__(self) -> None:
        self._url = DEFAULT_OLLAMA_URL
        self._models: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the Ollama server."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._url = user_input[CONF_OLLAMA_URL]
            try:
                self._models = await _async_models(self.hass, self._url)
            except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
                errors["base"] = "cannot_connect"
            else:
                if self._models:
                    return await self.async_step_settings()
                errors["base"] = "no_models"
        schema = vol.Schema({vol.Required(CONF_OLLAMA_URL, default=self._url): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for model, players, PIN and the first child, who watches on every player."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_PLAYERS]:
                errors["base"] = "no_players"
            elif not valid_pin(user_input[CONF_PIN]):
                errors[CONF_PIN] = "invalid_pin"
            else:
                pin_hash = await self.hass.async_add_executor_job(hash_pin, user_input[CONF_PIN])
                profile = _new_profile_id()
                return self.async_create_entry(
                    title="ParentControl",
                    data={CONF_OLLAMA_URL: self._url},
                    options={
                        CONF_MODEL: user_input[CONF_MODEL],
                        CONF_PLAYERS: user_input[CONF_PLAYERS],
                        CONF_PIN_HASH: pin_hash,
                        CONF_PROFILES: {profile: _profile(user_input, int(user_input[CONF_AGE]))},
                        CONF_DEVICE_PROFILES: {
                            player: [profile] for player in user_input[CONF_PLAYERS]
                        },
                    },
                )
        fields = _player_fields(self._models, None, [])
        fields[vol.Required(CONF_PIN)] = PIN_SELECTOR
        fields |= _profile_fields(DEFAULT_PROFILE_NAME, None)
        fields[vol.Required(CONF_AGE, default=6)] = AGE_SELECTOR
        return self.async_show_form(
            step_id="settings", data_schema=vol.Schema(fields), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ParentControlOptionsFlow:
        """Return the options flow."""
        return ParentControlOptionsFlow()


class ParentControlOptionsFlow(OptionsFlow):
    """Changes model, players, PIN, profiles, lists and prompts."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._editing: str | None = None
        self._open_profiles: list[str] = []
        self._open_players: list[str] = []

    @property
    def _profiles(self) -> dict[str, dict]:
        return self._options[CONF_PROFILES]

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for model, players, history size and optionally a new PIN."""
        errors: dict[str, str] = {}
        current = self.config_entry.options
        if user_input is not None:
            pin = user_input.pop(CONF_PIN, "")
            if not user_input[CONF_PLAYERS]:
                errors["base"] = "no_players"
            elif pin and not valid_pin(pin):
                errors[CONF_PIN] = "invalid_pin"
            else:
                self._options = {
                    **current,
                    **user_input,
                    CONF_HISTORY_SIZE: int(user_input[CONF_HISTORY_SIZE]),
                    CONF_WARN_MINUTES: int(user_input[CONF_WARN_MINUTES]),
                    CONF_PIN_HASH: (
                        await self.hass.async_add_executor_job(hash_pin, pin)
                        if pin
                        else current.get(CONF_PIN_HASH)
                    ),
                    CONF_PROFILES: {pid: dict(p) for pid, p in current[CONF_PROFILES].items()},
                    CONF_DEVICE_PROFILES: dict(current[CONF_DEVICE_PROFILES]),
                }
                return await self.async_step_profiles()
        try:
            models = await _async_models(self.hass, self.config_entry.data[CONF_OLLAMA_URL])
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
            models = [current[CONF_MODEL]]
        fields = _player_fields(models, current[CONF_MODEL], current[CONF_PLAYERS])
        # Empty keeps the PIN; an entry without one needs it now.
        fields[vol.Optional(CONF_PIN) if current.get(CONF_PIN_HASH) else vol.Required(CONF_PIN)] = (
            PIN_SELECTOR
        )
        fields[
            vol.Required(CONF_HISTORY_SIZE, default=current.get(CONF_HISTORY_SIZE, HISTORY_SIZE))
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5, max=MAX_HISTORY_SIZE, step=5, mode=selector.NumberSelectorMode.BOX
            )
        )
        fields[
            vol.Required(CONF_WARN_MINUTES, default=current.get(CONF_WARN_MINUTES, WARN_MINUTES))
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=30, step=1, mode=selector.NumberSelectorMode.BOX)
        )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_profiles(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the children, then assign them to the players."""
        return self.async_show_menu(
            step_id="profiles",
            menu_options=["profile_add", "profile_edit", "profile_remove", "assign"],
            description_placeholders={
                "profiles": ", ".join(p[CONF_NAME] for p in self._profiles.values())
            },
        )

    async def async_step_profile_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a child; the age can be changed later in the card."""
        if user_input is not None:
            self._profiles[_new_profile_id()] = _profile(user_input, int(user_input[CONF_AGE]))
            return await self.async_step_profiles()
        fields = _profile_fields(None, None)
        fields[vol.Required(CONF_AGE, default=6)] = AGE_SELECTOR
        return self.async_show_form(step_id="profile_add", data_schema=vol.Schema(fields))

    async def async_step_profile_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the child to rename."""
        if user_input is not None:
            self._editing = user_input[CONF_PROFILE]
            return await self.async_step_profile_details()
        schema = vol.Schema({vol.Required(CONF_PROFILE): _profile_choice(self._profiles, False)})
        return self.async_show_form(step_id="profile_edit", data_schema=schema)

    async def async_step_profile_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change name and person of a child."""
        profile = self._profiles[self._editing]
        if user_input is not None:
            self._profiles[self._editing] = _profile(user_input, profile[CONF_AGE])
            return await self.async_step_profiles()
        return self.async_show_form(
            step_id="profile_details",
            data_schema=vol.Schema(_profile_fields(profile[CONF_NAME], profile.get(CONF_PERSON))),
        )

    async def async_step_profile_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a child; at least one stays."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if len(self._profiles) == 1:
                errors["base"] = "last_profile"
            else:
                removed = user_input[CONF_PROFILE]
                self._profiles.pop(removed)
                self._options[CONF_DEVICE_PROFILES] = {
                    player: [pid for pid in profiles if pid != removed]
                    for player, profiles in self._options[CONF_DEVICE_PROFILES].items()
                }
                return await self.async_step_profiles()
        schema = vol.Schema({vol.Required(CONF_PROFILE): _profile_choice(self._profiles, False)})
        return self.async_show_form(step_id="profile_remove", data_schema=schema, errors=errors)

    async def async_step_assign(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the assignment, one step per player."""
        self._open_players = list(self._options[CONF_PLAYERS])
        self._assigned: dict[str, list[str]] = {}
        return await self.async_step_assign_player()

    async def async_step_assign_player(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the children watching on one player; every player needs one."""
        player = self._open_players[0]
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_PROFILES):
                self._assigned[player] = list(user_input[CONF_PROFILES])
                self._open_players.pop(0)
                if self._open_players:
                    return await self.async_step_assign_player()
                self._options[CONF_DEVICE_PROFILES] = self._assigned
                return await self.async_step_lists()
            errors["base"] = "no_profile"
        current = self._options[CONF_DEVICE_PROFILES].get(player, list(self._profiles))
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PROFILES, default=[pid for pid in current if pid in self._profiles]
                ): _profile_choice(self._profiles, True)
            }
        )
        return self.async_show_form(
            step_id="assign_player",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device": player_name(self.hass, player)},
        )

    async def async_step_lists(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the lists for all children."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _list_errors(user_input)
            if not errors:
                for key in (CONF_ALLOWED, CONF_BLOCKED, CONF_ALLOWED_WORDS):
                    self._options[key] = user_input.get(key, "")
                for key in (CONF_PROFILE_ALLOWED, CONF_PROFILE_BLOCKED, CONF_PROFILE_WORDS):
                    self._options[key] = {
                        pid: text
                        for pid, text in self._options.get(key, {}).items()
                        if pid in self._profiles
                    }
                self._open_profiles = list(self._profiles)
                return await self.async_step_profile_lists()
        current = user_input or self._options
        return self.async_show_form(
            step_id="lists",
            data_schema=_list_form(
                current.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS),
                current.get(CONF_BLOCKED, ""),
                current.get(CONF_ALLOWED_WORDS, ""),
            ),
            errors=errors,
        )

    async def async_step_profile_lists(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the lists of one child, one step per child."""
        profile = self._open_profiles[0]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _list_errors(user_input)
            if not errors:
                for key, field in (
                    (CONF_PROFILE_ALLOWED, CONF_ALLOWED),
                    (CONF_PROFILE_BLOCKED, CONF_BLOCKED),
                    (CONF_PROFILE_WORDS, CONF_ALLOWED_WORDS),
                ):
                    self._options[key] = {
                        **self._options.get(key, {}),
                        profile: user_input.get(field, ""),
                    }
                self._open_profiles.pop(0)
                if self._open_profiles:
                    return await self.async_step_profile_lists()
                return await self.async_step_prompts()
        current = {
            field: self._options.get(key, {}).get(profile, "")
            for key, field in (
                (CONF_PROFILE_ALLOWED, CONF_ALLOWED),
                (CONF_PROFILE_BLOCKED, CONF_BLOCKED),
                (CONF_PROFILE_WORDS, CONF_ALLOWED_WORDS),
            )
        } | (user_input or {})
        return self.async_show_form(
            step_id="profile_lists",
            data_schema=_list_form(
                current.get(CONF_ALLOWED, ""),
                current.get(CONF_BLOCKED, ""),
                current.get(CONF_ALLOWED_WORDS, ""),
            ),
            errors=errors,
            description_placeholders={"profile": self._profiles[profile][CONF_NAME]},
        )

    async def async_step_prompts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the prompts. An empty field restores the default text."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self._options,
                    CONF_AGE_PROMPT: user_input.get(CONF_AGE_PROMPT)
                    or engine.DEFAULT_AGE_PROMPT,
                    CONF_PEDAGOGY_PROMPT: user_input.get(CONF_PEDAGOGY_PROMPT)
                    or engine.DEFAULT_PEDAGOGY_PROMPT,
                }
            )
        current = self._options
        fields = {
            vol.Optional(
                CONF_AGE_PROMPT,
                description={
                    "suggested_value": current.get(CONF_AGE_PROMPT, engine.DEFAULT_AGE_PROMPT)
                },
            ): TEXT_SELECTOR,
            vol.Optional(
                CONF_PEDAGOGY_PROMPT,
                description={
                    "suggested_value": current.get(
                        CONF_PEDAGOGY_PROMPT, engine.DEFAULT_PEDAGOGY_PROMPT
                    )
                },
            ): TEXT_SELECTOR,
        }
        return self.async_show_form(step_id="prompts", data_schema=vol.Schema(fields))
