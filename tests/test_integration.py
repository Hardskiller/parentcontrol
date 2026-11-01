"""Tests against a real Home Assistant core."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.parentcontrol import engine
from custom_components.parentcontrol.const import (
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
    SETTING_BLOCK_PROFANITY,
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_SEEK_TO_START,
    SETTING_SKIP_CHECKS,
    SETTING_STRICT,
)

WATCH = "sensor.parentcontrol_tv_watch_time_today"
TV = "media_player.tv"
KIDS = "media_player.kids"
SENSOR = "sensor.parentcontrol_tv_youtube_check"
STRICT_SWITCH = "switch.parentcontrol_tv_strict_rating_block_without_subtitles_or_result"
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


async def setup(hass, min_age=16, age=8, device_ages=None, side_effect=None, valuable=False, profanity=False, source="untertitel", settings=(), **options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_OLLAMA_URL: "http://ollama", CONF_AGE: age},
        options={
            CONF_MODEL: "m",
            CONF_PLAYERS: [TV, KIDS],
            CONF_DEVICE_AGES: device_ages or {},
            **options,
        },
    )
    entry.add_to_hass(hass)
    rating = engine.Rating(min_age, "Grund", source, "id", valuable, "Lehrreich", profanity)
    patcher = patch.object(
        engine, "rate", side_effect=side_effect, return_value=rating
    )
    mock = patcher.start()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for setting in settings:
        entry.runtime_data.async_set_setting(TV, setting, True)
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


async def test_blocked_video_only_pauses_by_default(hass, pauses):
    seeks = async_mock_service(hass, "media_player", "media_seek")
    _, _, patcher = await setup(hass)
    await play(hass)
    assert len(pauses) == 1
    assert not seeks
    patcher.stop()


async def test_seek_option_jumps_to_the_start_after_pausing(hass):
    calls = []
    for service in ("media_pause", "media_seek"):
        async def record(call):
            calls.append(call.service)
        hass.services.async_register("media_player", service, record)
    _, _, patcher = await setup(hass, settings=[SETTING_SEEK_TO_START])
    await play(hass)
    assert calls == ["media_pause", "media_seek"]
    patcher.stop()


async def test_pedagogy_option_blocks_videos_without_value(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, settings=[SETTING_REQUIRE_PEDAGOGY])
    await play(hass)
    assert len(pauses) == 1
    state = hass.states.get(SENSOR)
    assert state.state == "blockiert"
    assert state.attributes["sperrgrund"] == "paedagogik"
    patcher.stop()


async def test_pedagogy_option_allows_valuable_videos(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, valuable=True, settings=[SETTING_REQUIRE_PEDAGOGY])
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).attributes["paedagogisch_wertvoll"] is True
    patcher.stop()


async def test_without_option_pedagogy_is_only_reported(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4)
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).state == "frei"
    assert hass.states.get(SENSOR).attributes["paedagogisch_wertvoll"] is False
    patcher.stop()


async def test_profanity_option_blocks_otherwise_allowed_video(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, profanity=True, settings=[SETTING_BLOCK_PROFANITY])
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "schimpfwoerter"
    patcher.stop()


async def test_without_option_profanity_is_only_reported(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, profanity=True)
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).attributes["schimpfwoerter"] is True
    patcher.stop()


async def test_strict_rating_blocks_video_without_subtitles(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, source="metadaten", settings=[SETTING_STRICT])
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "keine_untertitel"
    patcher.stop()


async def test_strict_rating_allows_video_with_subtitles(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, settings=[SETTING_STRICT])
    await play(hass)
    assert not pauses
    patcher.stop()


async def test_without_strict_rating_video_without_subtitles_keeps_playing(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, source="metadaten")
    await play(hass)
    assert not pauses
    patcher.stop()


async def test_strict_rating_blocks_when_the_check_fails(hass, pauses):
    _, _, patcher = await setup(hass, side_effect=OSError("weg"), settings=[SETTING_STRICT])
    await play(hass)
    assert len(pauses) == 1
    state = hass.states.get(SENSOR)
    assert state.state == "blockiert"
    assert state.attributes["sperrgrund"] == "nicht_geprueft"
    patcher.stop()


async def test_settings_apply_only_to_their_player(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, source="metadaten", settings=[SETTING_STRICT])
    await play(hass, entity=KIDS)
    assert not pauses
    await play(hass)
    assert len(pauses) == 1
    assert pauses[0].data[ATTR_ENTITY_ID] == TV
    patcher.stop()


async def test_player_switch_applies_immediately_and_survives_reload(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4, source="metadaten")
    await play(hass)
    assert not pauses
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: STRICT_SWITCH}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(pauses) == 1
    await hass.async_block_till_done()
    await entry.runtime_data._store.async_save(entry.runtime_data._data())
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(STRICT_SWITCH).state == "on"
    patcher.stop()


async def test_each_player_is_its_own_device(hass, pauses):
    entry, _, patcher = await setup(hass)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(device.name for device in devices) == [
        "ParentControl",
        "ParentControl kids",
        "ParentControl tv",
    ]
    patcher.stop()


async def test_default_list_applies_until_it_is_edited(hass, pauses):
    _, mock, patcher = await setup(
        hass, age=8, settings=[SETTING_SKIP_CHECKS]
    )
    await play(hass, attributes={**VIDEO, "media_artist": "Die Maus"})
    assert not mock.called
    assert hass.states.get(SENSOR).attributes["liste"] == "freigegeben"
    patcher.stop()


async def test_emptied_list_stays_empty(hass, pauses):
    _, mock, patcher = await setup(
        hass, age=8, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: ""}
    )
    await play(hass, attributes={**VIDEO, "media_artist": "Die Maus"})
    assert mock.called
    patcher.stop()


async def test_blocked_channel_pauses_without_the_model(hass, pauses):
    _, mock, patcher = await setup(hass, min_age=4, **{CONF_BLOCKED: "kanal"})
    await play(hass)
    assert len(pauses) == 1
    assert not mock.called
    state = hass.states.get(SENSOR)
    assert state.attributes["sperrgrund"] == "kanal_gesperrt"
    assert state.attributes["liste"] == "gesperrt"
    assert hass.states.get("sensor.parentcontrol_skipped_today").state == "1"
    patcher.stop()


async def test_block_beats_allow(hass, pauses):
    _, _, patcher = await setup(
        hass,
        settings=[SETTING_SKIP_CHECKS],
        **{CONF_ALLOWED: "Kanal; 0", CONF_DEVICE_BLOCKED: {TV: "Kanal"}},
    )
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_skip_switch_allows_channel_without_the_model(hass, pauses):
    _, mock, patcher = await setup(
        hass, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: "Kanal; 6"}
    )
    await play(hass)
    assert not pauses
    assert not mock.called
    state = hass.states.get(SENSOR)
    assert state.state == "frei"
    assert state.attributes["quelle"] == "freigabeliste"
    assert hass.states.get("sensor.parentcontrol_approved_today").state == "1"
    patcher.stop()


async def test_allowed_channel_below_its_age_gets_the_normal_check(hass, pauses):
    _, mock, patcher = await setup(
        hass, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: "Kanal; 12"}
    )
    await play(hass)
    assert mock.called
    assert len(pauses) == 1
    patcher.stop()


async def test_device_entry_beats_global_entry(hass, pauses):
    _, mock, patcher = await setup(
        hass,
        settings=[SETTING_SKIP_CHECKS],
        **{CONF_ALLOWED: "Kanal; 12", CONF_DEVICE_ALLOWED: {TV: "Kanal; 6"}},
    )
    await play(hass)
    assert not mock.called
    assert not pauses
    patcher.stop()


async def test_without_skip_switch_listed_channel_ignores_only_the_gaps(hass, pauses):
    _, _, patcher = await setup(
        hass,
        min_age=4,
        source="metadaten",
        settings=[SETTING_STRICT, SETTING_REQUIRE_PEDAGOGY],
        **{CONF_ALLOWED: "Kanal"},
    )
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).attributes["liste"] == "freigegeben"
    patcher.stop()


async def test_without_skip_switch_listed_channel_still_fails_on_age(hass, pauses):
    _, _, patcher = await setup(hass, **{CONF_ALLOWED: "Kanal"})
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_without_skip_switch_listed_channel_still_fails_on_swear_words(hass, pauses):
    _, _, patcher = await setup(
        hass,
        min_age=4,
        profanity=True,
        settings=[SETTING_BLOCK_PROFANITY],
        **{CONF_ALLOWED: "Kanal"},
    )
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "schimpfwoerter"
    patcher.stop()


async def test_failed_check_does_not_block_a_listed_channel(hass, pauses):
    _, _, patcher = await setup(
        hass, side_effect=OSError("weg"), settings=[SETTING_STRICT], **{CONF_ALLOWED: "Kanal"}
    )
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).state == "nicht_geprueft"
    patcher.stop()


async def test_allow_action_uses_running_channel_and_clears_the_block(hass, pauses):
    entry, _, patcher = await setup(hass, **{CONF_BLOCKED: "Kanal"})
    await play(hass)
    await hass.services.async_call(
        DOMAIN, "allow_channel", {"player": TV, "age": 6}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_ALLOWED].endswith("Kanal; 6")
    assert "Die Maus; 5" in entry.options[CONF_ALLOWED]
    assert entry.options[CONF_BLOCKED] == ""
    patcher.stop()


async def test_block_action_can_target_one_device(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4)
    await hass.services.async_call(
        DOMAIN,
        "block_channel",
        {"channel": "Neu", "player": KIDS, "only_this_device": True},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_DEVICE_BLOCKED] == {KIDS: "Neu"}
    assert entry.options.get(CONF_BLOCKED, "") == ""
    patcher.stop()


async def test_action_without_channel_is_rejected(hass, pauses):
    _, _, patcher = await setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "allow_channel", {}, blocking=True)
    patcher.stop()


async def test_statistics_count_each_video_once_per_day(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, valuable=True)
    await play(hass)
    await play(hass, "paused")
    await play(hass, entity=KIDS)
    assert hass.states.get("sensor.parentcontrol_videos_today").state == "1"
    assert hass.states.get("sensor.parentcontrol_approved_today").state == "1"
    assert hass.states.get("sensor.parentcontrol_educational_today").state == "1"
    assert hass.states.get("sensor.parentcontrol_skipped_today").state == "0"
    patcher.stop()


async def test_skipped_video_is_counted(hass, pauses):
    _, _, patcher = await setup(hass)
    await play(hass)
    assert hass.states.get("sensor.parentcontrol_skipped_today").state == "1"
    assert hass.states.get("sensor.parentcontrol_approved_today").state == "0"
    patcher.stop()


async def test_statistics_reset_on_a_new_day_but_keep_the_total(hass, pauses, freezer):
    _, _, patcher = await setup(hass)
    await play(hass)
    await play(hass, "off")
    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.parentcontrol_skipped_today")
    assert state.state == "0"
    assert state.attributes["gesamt"] == 1
    patcher.stop()


async def test_watch_time_counts_only_while_playing(hass, pauses, freezer):
    _, _, patcher = await setup(hass, min_age=4)
    await play(hass)
    for _ in range(25):
        freezer.tick(5)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(WATCH).state == "2"
    await play(hass, "paused")
    for _ in range(25):
        freezer.tick(5)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(WATCH).state == "2"
    patcher.stop()


async def test_edited_prompt_rates_the_video_again(hass, pauses):
    entry, mock, patcher = await setup(hass, min_age=4)
    await play(hass)
    assert mock.call_count == 1
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_AGE_PROMPT: "Neuer Prompt"}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock.call_count == 2
    assert "Neuer Prompt" in mock.call_args.args[3]
    patcher.stop()


async def test_timer_pauses_when_the_last_play_report_was_debounced(hass, pauses, freezer):
    _, _, patcher = await setup(hass)
    await play(hass)
    await play(hass, "paused")
    await play(hass)
    assert len(pauses) == 1
    freezer.tick(5)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
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
        result["flow_id"],
        {
            CONF_MODEL: "m",
            CONF_PLAYERS: [TV, KIDS],
        },
    )
    assert result["step_id"] == "ages"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {KIDS: 7})
    assert result["step_id"] == "lists"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOWED: "Kanal; abc"}
    )
    assert result["errors"] == {CONF_ALLOWED: "invalid_age"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOWED: "Kanal; 6", CONF_BLOCKED: "Andere"}
    )
    assert result["step_id"] == "device_lists"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_BLOCKED: "Nur TV"}
    )
    assert result["step_id"] == "device_lists"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["step_id"] == "prompts"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_AGE_PROMPT: "Mein Prompt"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DEVICE_AGES] == {KIDS: 7}
    assert entry.options[CONF_ALLOWED] == "Kanal; 6"
    assert entry.options[CONF_DEVICE_BLOCKED] == {TV: "Nur TV", KIDS: ""}
    assert entry.options[CONF_AGE_PROMPT] == "Mein Prompt"
    assert entry.options[CONF_PEDAGOGY_PROMPT] == engine.DEFAULT_PEDAGOGY_PROMPT
    await hass.async_block_till_done()
    patcher.stop()
