"""Setup and options for ParentControl."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AGE,
    CONF_DEVICE_AGES,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_PLAYERS,
    DEFAULT_OLLAMA_URL,
    DOMAIN,
    MAX_AGE,
)

TIMEOUT = aiohttp.ClientTimeout(total=10)
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
            return self.async_create_entry(data={**self._options, CONF_DEVICE_AGES: ages})
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
