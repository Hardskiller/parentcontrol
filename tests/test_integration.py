"""Tests against a real Home Assistant core."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.parentcontrol import engine
from custom_components.parentcontrol.const import (
    CONF_AGE,
    CONF_DEVICE_AGES,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_PLAYERS,
    DOMAIN,
)

TV = "media_player.tv"
KIDS = "media_player.kids"
SENSOR = "sensor.parentcontrol_youtube_prufung_tv"
SWITCH = "switch.parentcontrol_check"
NUMBER = "number.parentcontrol_default_age"
VIDEO = {
    "app_name": "YouTube",
    "media_title": "Titel",
    "media_artist": "Kanal",
    "media_duration": 100.0,
}


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow loading the integration."""


@pytest.fixture
def pauses(hass: HomeAssistant):
    """Record pause calls."""
    return async_mock_service(hass, "media_player", "media_pause")


async def setup(hass, min_age=16, age=8, device_ages=None, side_effect=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_OLLAMA_URL: "http://ollama", CONF_AGE: age},
        options={
            CONF_MODEL: "m",
            CONF_PLAYERS: [TV, KIDS],
            CONF_DEVICE_AGES: device_ages or {},
        },
    )
    entry.add_to_hass(hass)
    rating = engine.Rating(min_age, "Grund", "titel", "id")
    patcher = patch.object(
        engine, "rate", side_effect=side_effect, return_value=rating
    )
    mock = patcher.start()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, mock, patcher


async def play(hass, state="playing", entity=TV, attributes=None):
    hass.states.async_set(entity, state, VIDEO if attributes is None else attributes)
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_blocked_video_is_paused_again_after_every_play(hass, pauses, freezer):
    _, _, patcher = await setup(hass)
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).state == "blockiert"
    assert hass.states.get(SENSOR).attributes["mindestalter"] == 16
    await play(hass, "paused")
    assert len(pauses) == 1
    freezer.tick(5)
    await play(hass)
    assert len(pauses) == 2
    patcher.stop()


async def test_allowed_video_keeps_playing(hass, pauses):
    _, _, patcher = await setup(hass, min_age=7)
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).state == "frei"
    patcher.stop()


async def test_device_age_overrides_the_default(hass, pauses):
    _, _, patcher = await setup(hass, min_age=10, age=8, device_ages={TV: 12})
    await play(hass)
    assert not pauses
    await play(hass, entity=KIDS)
    assert len(pauses) == 1
    assert pauses[0].data[ATTR_ENTITY_ID] == KIDS
    patcher.stop()


async def test_rating_is_shared_between_players(hass, pauses):
    _, mock, patcher = await setup(hass)
    await play(hass)
    await play(hass, entity=KIDS)
    assert mock.call_count == 1
    patcher.stop()


async def test_switch_off_never_pauses_and_skips_the_model(hass, pauses):
    _, mock, patcher = await setup(hass)
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    await play(hass)
    assert not pauses
    assert not mock.called
    assert hass.states.get(SENSOR).state == "aus"
    patcher.stop()


async def test_changing_the_age_applies_immediately(hass, pauses):
    _, _, patcher = await setup(hass, min_age=10, age=12)
    await play(hass)
    assert not pauses
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: NUMBER, "value": 8}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(pauses) == 1
    patcher.stop()


async def test_ollama_failure_keeps_playing_and_does_not_retry_at_once(hass, pauses):
    _, mock, patcher = await setup(hass, side_effect=OSError("weg"))
    await play(hass)
    await play(hass, "paused")
    await play(hass)
    assert not pauses
    assert mock.call_count == 1
    assert hass.states.get(SENSOR).state == "nicht_geprueft"
    patcher.stop()


async def test_youtube_without_title_reports_no_data(hass, pauses):
    _, mock, patcher = await setup(hass)
    await play(hass, attributes={"app_name": "com.google.android.youtube.tv"})
    assert not mock.called
    assert hass.states.get(SENSOR).state == "keine_daten"
    patcher.stop()


async def test_other_apps_are_ignored(hass, pauses):
    _, mock, patcher = await setup(hass)
    await play(hass, attributes={**VIDEO, "app_name": "Netflix"})
    assert not mock.called
    assert hass.states.get(SENSOR).state == "inaktiv"
    patcher.stop()


async def test_setup_flow_creates_entry(hass, aioclient_mock):
    aioclient_mock.get("http://ollama:11434/api/tags", json={"models": [{"name": "m"}]})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_OLLAMA_URL: "http://ollama:11434"}
    )
    assert result["step_id"] == "settings"
    with patch("custom_components.parentcontrol.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MODEL: "m", CONF_PLAYERS: [TV], CONF_AGE: 8}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_OLLAMA_URL: "http://ollama:11434", CONF_AGE: 8}
    assert result["options"] == {CONF_MODEL: "m", CONF_PLAYERS: [TV]}


async def test_setup_flow_reports_unreachable_server(hass, aioclient_mock):
    aioclient_mock.get("http://ollama:11434/api/tags", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_OLLAMA_URL: "http://ollama:11434"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_stores_device_age(hass, aioclient_mock):
    aioclient_mock.get("http://ollama/api/tags", json={"models": [{"name": "m"}]})
    entry, _, patcher = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MODEL: "m", CONF_PLAYERS: [TV, KIDS]}
    )
    assert result["step_id"] == "ages"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {KIDS: 7})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DEVICE_AGES] == {KIDS: 7}
    await hass.async_block_till_done()
    patcher.stop()
