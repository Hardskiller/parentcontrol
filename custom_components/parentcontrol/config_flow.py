"""Setup and options for ParentControl."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import engine
from .const import (
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
    DEFAULT_OLLAMA_URL,
    DOMAIN,
    MAX_AGE,
)

TIMEOUT = aiohttp.ClientTimeout(total=10)
PROMPT_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
AGE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=MAX_AGE, step=1, mode=selector.NumberSelectorMode.SLIDER
    )
)


async def _async_models(hass: HomeAssistant, url: str) -> list[str]:
    """Return the models installed on the Ollama server."""
    session = async_get_clientsession(hass)
    async with session.get(f"{url.rstrip('/')}/api/tags", timeout=TIMEOUT) as response:
        response.raise_for_status()
        data = await response.json()
    return sorted(model["name"] for model in data.get("models", []))


def _list_form(allowed: str, blocked: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_ALLOWED, description={"suggested_value": allowed}): PROMPT_SELECTOR,
            vol.Optional(CONF_BLOCKED, description={"suggested_value": blocked}): PROMPT_SELECTOR,
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


class ParentControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Asks for the Ollama server, model, players and age."""

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
        """Ask for model, players and age."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_PLAYERS]:
                return self.async_create_entry(
                    title="ParentControl",
                    data={CONF_OLLAMA_URL: self._url, CONF_AGE: int(user_input[CONF_AGE])},
                    options={
                        CONF_MODEL: user_input[CONF_MODEL],
                        CONF_PLAYERS: user_input[CONF_PLAYERS],
                    },
                )
            errors["base"] = "no_players"
        fields = _player_fields(self._models, None, [])
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
    """Changes model and players, and sets an own age per player."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._open_players: list[str] = []

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for model and players."""
        errors: dict[str, str] = {}
        current = self.config_entry.options
        if user_input is not None:
            if user_input[CONF_PLAYERS]:
                self._options = user_input
                return await self.async_step_ages()
            errors["base"] = "no_players"
        try:
            models = await _async_models(self.hass, self.config_entry.data[CONF_OLLAMA_URL])
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
            models = [current[CONF_MODEL]]
        fields = _player_fields(models, current[CONF_MODEL], current[CONF_PLAYERS])
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_ages(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for optional ages. An empty field means the default age applies."""
        if user_input is not None:
            ages = {player: int(age) for player, age in user_input.items()}
            self._options[CONF_DEVICE_AGES] = ages
            return await self.async_step_lists()
        current = self.config_entry.options.get(CONF_DEVICE_AGES, {})
        fields = {
            vol.Optional(
                player, description={"suggested_value": current.get(player)}
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=MAX_AGE, step=1, mode=selector.NumberSelectorMode.BOX
                )
            )
            for player in self._options[CONF_PLAYERS]
        }
        return self.async_show_form(step_id="ages", data_schema=vol.Schema(fields))

    async def async_step_lists(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the lists for all devices."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _list_errors(user_input)
            if not errors:
                self._options[CONF_ALLOWED] = user_input.get(CONF_ALLOWED, "")
                self._options[CONF_BLOCKED] = user_input.get(CONF_BLOCKED, "")
                self._options[CONF_DEVICE_ALLOWED] = {}
                self._options[CONF_DEVICE_BLOCKED] = {}
                self._open_players = list(self._options[CONF_PLAYERS])
                return await self.async_step_device_lists()
        current = user_input or self.config_entry.options
        return self.async_show_form(
            step_id="lists",
            data_schema=_list_form(
                current.get(CONF_ALLOWED, engine.DEFAULT_ALLOWED_CHANNELS),
                current.get(CONF_BLOCKED, ""),
            ),
            errors=errors,
        )

    async def async_step_device_lists(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the lists of one device, one step per device."""
        player = self._open_players[0]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _list_errors(user_input)
            if not errors:
                self._options[CONF_DEVICE_ALLOWED][player] = user_input.get(CONF_ALLOWED, "")
                self._options[CONF_DEVICE_BLOCKED][player] = user_input.get(CONF_BLOCKED, "")
                self._open_players.pop(0)
                if self._open_players:
                    return await self.async_step_device_lists()
                return await self.async_step_prompts()
        current = self.config_entry.options
        allowed = current.get(CONF_DEVICE_ALLOWED, {}).get(player, "")
        blocked = current.get(CONF_DEVICE_BLOCKED, {}).get(player, "")
        if user_input is not None:
            allowed = user_input.get(CONF_ALLOWED, "")
            blocked = user_input.get(CONF_BLOCKED, "")
        return self.async_show_form(
            step_id="device_lists",
            data_schema=_list_form(allowed, blocked),
            errors=errors,
            description_placeholders={"device": player},
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
        current = self.config_entry.options
        fields = {
            vol.Optional(
                CONF_AGE_PROMPT,
                description={
                    "suggested_value": current.get(CONF_AGE_PROMPT, engine.DEFAULT_AGE_PROMPT)
                },
            ): PROMPT_SELECTOR,
            vol.Optional(
                CONF_PEDAGOGY_PROMPT,
                description={
                    "suggested_value": current.get(
                        CONF_PEDAGOGY_PROMPT, engine.DEFAULT_PEDAGOGY_PROMPT
                    )
                },
            ): PROMPT_SELECTOR,
        }
        return self.async_show_form(step_id="prompts", data_schema=vol.Schema(fields))
