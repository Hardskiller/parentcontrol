"""Tests against a real Home Assistant core."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.parentcontrol import engine, pinlock
from custom_components.parentcontrol.const import (
    CONF_AGE,
    CONF_AGE_PROMPT,
    CONF_ALLOWED,
    CONF_ALLOWED_WORDS,
    CONF_BLOCKED,
    CONF_DEVICE_PROFILES,
    CONF_HISTORY_SIZE,
    CONF_MODEL,
    CONF_OLLAMA_URL,
    CONF_PEDAGOGY_PROMPT,
    CONF_PIN,
    CONF_PIN_HASH,
    CONF_PLAYERS,
    CONF_PROFILE_ALLOWED,
    CONF_PROFILE_BLOCKED,
    CONF_PROFILE_WORDS,
    CONF_PROFILES,
    DOMAIN,
    SETTING_BLOCK_PROFANITY,
    SETTING_BLOCK_SHORTS,
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_SEEK_TO_START,
    SETTING_SKIP_CHECKS,
    SETTING_STRICT,
)

WATCH = "sensor.parentcontrol_tv_watch_time_today"
TV = "media_player.tv"
KIDS = "media_player.kids"
SENSOR = "sensor.parentcontrol_tv_youtube_check"
STRICT_SWITCH = "switch.parentcontrol_kind_strict_rating_block_without_subtitles_or_result"
SWITCH = "switch.parentcontrol_check"
NUMBER = "number.parentcontrol_kind_age"
LOCK = "lock.parentcontrol_settings"
HISTORY = "sensor.parentcontrol_tv_latest_videos"
SHORTS_SWITCH = "switch.parentcontrol_kind_block_shorts"
WHO = "select.parentcontrol_tv_who_is_watching"
PROFILE_WATCH = "sensor.parentcontrol_kind_watch_time_today"
KIND = "kind"
GROSS = "gross"
OLLAMA = "binary_sensor.parentcontrol_ollama"
PIN = "1234"
PIN_HASH = pinlock.hash_pin(PIN)
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


class Patches:
    """Stops the engine patches together."""

    def __init__(self, *patchers):
        self.patchers = patchers

    def stop(self):
        for patcher in self.patchers:
            patcher.stop()


@pytest.fixture(autouse=True)
def quiet_health_check(aioclient_mock):
    """Answer the periodic Ollama check."""
    aioclient_mock.get("http://ollama.local/api/tags", json={"models": [{"name": "m"}]})


def profiles(age=8, big_age=None):
    """One child on both players, or a second, older child on the kids player."""
    result = {KIND: {"name": "Kind", "person": None, "age": age}}
    if big_age is not None:
        result[GROSS] = {"name": "Gross", "person": None, "age": big_age}
    return result


async def setup(hass, min_age=16, age=8, big_age=None, side_effect=None, valuable=False, profanity=False, source="untertitel", settings=(), short=False, meta_failed=False, words=(), transcript="", **options):
    assign = {TV: [KIND], KIDS: [GROSS if big_age is not None else KIND]}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_OLLAMA_URL: "http://ollama.local"},
        options={
            CONF_MODEL: "m",
            CONF_PLAYERS: [TV, KIDS],
            CONF_PIN_HASH: PIN_HASH,
            CONF_PROFILES: profiles(age, big_age),
            CONF_DEVICE_PROFILES: assign,
            **options,
        },
    )
    entry.add_to_hass(hass)
    rating = engine.Rating(
        min_age, "Grund", source, "id", valuable, "Lehrreich", profanity, list(words)
    )
    rate_patcher = patch.object(
        engine, "rate", side_effect=side_effect, return_value=rating
    )
    meta = (
        engine.Metadata(failed=True)
        if meta_failed
        else engine.Metadata("id", short=short, transcript=transcript)
    )
    meta_patcher = patch.object(engine, "fetch_metadata", return_value=meta)
    mock = rate_patcher.start()
    meta_patcher.start()
    patcher = Patches(rate_patcher, meta_patcher)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for setting in settings:
        if setting == SETTING_SEEK_TO_START:
            entry.runtime_data.async_set_device_setting(TV, setting, True)
        else:
            entry.runtime_data.async_set_profile_setting(KIND, setting, True)
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


async def test_rules_apply_only_to_the_profiles_of_a_player(hass, pauses):
    _, _, patcher = await setup(
        hass, min_age=4, big_age=10, source="metadaten", settings=[SETTING_STRICT]
    )
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


async def test_each_player_and_profile_is_its_own_device(hass, pauses):
    entry, _, patcher = await setup(hass)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(device.name for device in devices) == [
        "ParentControl",
        "ParentControl Kind",
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
        **{CONF_ALLOWED: "Kanal; 0", CONF_PROFILE_BLOCKED: {KIND: "Kanal"}},
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


async def test_profile_entry_beats_global_entry(hass, pauses):
    _, mock, patcher = await setup(
        hass,
        settings=[SETTING_SKIP_CHECKS],
        **{CONF_ALLOWED: "Kanal; 12", CONF_PROFILE_ALLOWED: {KIND: "Kanal; 6"}},
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


async def test_block_action_can_target_one_profile(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4)
    await hass.services.async_call(
        DOMAIN, "block_channel", {"channel": "Neu", "profile": "kind"}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_PROFILE_BLOCKED] == {KIND: "Neu"}
    assert entry.options.get(CONF_BLOCKED, "") == ""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "block_channel", {"channel": "Neu", "profile": "Niemand"}, blocking=True
        )
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


async def test_each_profile_has_its_own_age(hass, pauses):
    _, _, patcher = await setup(hass, min_age=10, age=12, big_age=8)
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


async def test_setup_flow_creates_entry_with_the_first_child(hass, aioclient_mock):
    aioclient_mock.get("http://ollama:11434/api/tags", json={"models": [{"name": "m"}]})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_OLLAMA_URL: "http://ollama:11434"}
    )
    assert result["step_id"] == "settings"
    answers = {CONF_MODEL: "m", CONF_PLAYERS: [TV, KIDS], CONF_AGE: 8, "name": "Siva"}
    with patch("custom_components.parentcontrol.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**answers, CONF_PIN: "12a4"}
        )
        assert result["errors"] == {CONF_PIN: "invalid_pin"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**answers, CONF_PIN: "4711", "person": "person.siva"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_OLLAMA_URL: "http://ollama:11434"}
    options = result["options"]
    pin_hash = options.pop(CONF_PIN_HASH)
    assert "4711" not in pin_hash
    assert pinlock.check_pin("4711", pin_hash)
    [profile] = options[CONF_PROFILES]
    assert options[CONF_PROFILES][profile] == {"name": "Siva", "person": "person.siva", "age": 8}
    assert options[CONF_DEVICE_PROFILES] == {TV: [profile], KIDS: [profile]}


async def test_setup_flow_reports_unreachable_server(hass, aioclient_mock):
    aioclient_mock.get("http://ollama:11434/api/tags", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_OLLAMA_URL: "http://ollama:11434"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


def profile_choices(result):
    """Return the profile ids offered in a form."""
    for key, field in result["data_schema"].schema.items():
        if str(key) == "profile":
            return [option["value"] for option in field.config["options"]]
    raise AssertionError("no profile field")


async def start_options(hass, entry):
    flow = hass.config_entries.options
    result = await flow.async_init(entry.entry_id)
    result = await flow.async_configure(result["flow_id"], {CONF_MODEL: "m", CONF_PLAYERS: [TV, KIDS]})
    assert result["step_id"] == "profiles"
    return flow, result


async def test_options_flow_adds_and_removes_profiles(hass, aioclient_mock):
    entry, _, patcher = await setup(hass)
    flow, result = await start_options(hass, entry)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "profile_add"})
    result = await flow.async_configure(result["flow_id"], {"name": "Gross", CONF_AGE: 12})
    assert result["step_id"] == "profiles"
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "profile_remove"})
    [new] = [pid for pid in profile_choices(result) if pid != KIND]
    result = await flow.async_configure(result["flow_id"], {"profile": KIND})
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "assign"})
    result = await flow.async_configure(result["flow_id"], {"profiles": [new]})
    result = await flow.async_configure(result["flow_id"], {"profiles": [new]})
    result = await flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "profile_lists"
    result = await flow.async_configure(result["flow_id"], {})
    result = await flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_PROFILES] == {new: {"name": "Gross", "person": None, "age": 12}}
    assert entry.options[CONF_DEVICE_PROFILES] == {TV: [new], KIDS: [new]}
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert "ParentControl Kind" not in [device.name for device in devices]
    assert "ParentControl Gross" in [device.name for device in devices]
    patcher.stop()


async def test_options_flow_keeps_the_last_profile(hass, aioclient_mock):
    entry, _, patcher = await setup(hass)
    flow, result = await start_options(hass, entry)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "profile_remove"})
    result = await flow.async_configure(result["flow_id"], {"profile": KIND})
    assert result["errors"] == {"base": "last_profile"}
    patcher.stop()


async def test_options_flow_assigns_profiles_and_edits_their_lists(hass, aioclient_mock):
    entry, _, patcher = await setup(hass, big_age=12)
    flow, result = await start_options(hass, entry)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "profile_edit"})
    result = await flow.async_configure(result["flow_id"], {"profile": GROSS})
    result = await flow.async_configure(result["flow_id"], {"name": "Groß", "person": "person.siva"})
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "assign"})
    assert result["step_id"] == "assign_player"
    assert result["description_placeholders"] == {"device": "tv"}
    result = await flow.async_configure(result["flow_id"], {"profiles": [KIND, GROSS]})
    assert result["description_placeholders"] == {"device": "kids"}
    result = await flow.async_configure(result["flow_id"], {"profiles": []})
    assert result["errors"] == {"base": "no_profile"}
    result = await flow.async_configure(result["flow_id"], {"profiles": [GROSS]})
    assert result["step_id"] == "lists"
    result = await flow.async_configure(result["flow_id"], {CONF_ALLOWED: "Kanal; abc"})
    assert result["errors"] == {CONF_ALLOWED: "invalid_age"}
    result = await flow.async_configure(
        result["flow_id"], {CONF_ALLOWED: "Kanal; 6", CONF_BLOCKED: "Andere", CONF_ALLOWED_WORDS: "Mist"}
    )
    assert result["step_id"] == "profile_lists"
    result = await flow.async_configure(result["flow_id"], {CONF_BLOCKED: "Nur Kind"})
    assert result["step_id"] == "profile_lists"
    result = await flow.async_configure(result["flow_id"], {CONF_ALLOWED_WORDS: "blöd"})
    assert result["step_id"] == "prompts"
    result = await flow.async_configure(result["flow_id"], {CONF_AGE_PROMPT: "Mein Prompt"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    options = entry.options
    assert options[CONF_PROFILES][GROSS] == {"name": "Groß", "person": "person.siva", "age": 12}
    assert options[CONF_DEVICE_PROFILES] == {TV: [KIND, GROSS], KIDS: [GROSS]}
    assert options[CONF_ALLOWED] == "Kanal; 6"
    assert options[CONF_ALLOWED_WORDS] == "Mist"
    assert options[CONF_PROFILE_BLOCKED] == {KIND: "Nur Kind", GROSS: ""}
    assert options[CONF_PROFILE_WORDS] == {KIND: "", GROSS: "blöd"}
    assert options[CONF_AGE_PROMPT] == "Mein Prompt"
    assert options[CONF_PEDAGOGY_PROMPT] == engine.DEFAULT_PEDAGOGY_PROMPT
    assert options[CONF_PIN_HASH] == PIN_HASH
    assert options[CONF_HISTORY_SIZE] == 20
    patcher.stop()


async def child_context(hass):
    # The first user becomes the owner, who is always an admin.
    await hass.auth.async_create_user("Eltern", group_ids=["system-admin"])
    user = await hass.auth.async_create_user("Kind", group_ids=["system-users"])
    return Context(user_id=user.id)


async def unlock(hass, code=PIN):
    await hass.services.async_call(
        "lock", "unlock", {ATTR_ENTITY_ID: LOCK, "code": code}, blocking=True
    )


async def test_locked_integration_rejects_loosening_by_non_admins(hass, pauses):
    _, _, patcher = await setup(hass)
    context = await child_context(hass)
    assert hass.states.get(LOCK).state == "locked"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True, context=context
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {ATTR_ENTITY_ID: NUMBER, "value": 12}, blocking=True, context=context
        )
    assert hass.states.get(SWITCH).state == "on"
    assert hass.states.get(NUMBER).state == "8"
    patcher.stop()


async def test_stricter_changes_need_no_pin(hass, pauses):
    _, _, patcher = await setup(hass)
    context = await child_context(hass)
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: NUMBER, "value": 6}, blocking=True, context=context
    )
    await hass.services.async_call(
        DOMAIN, "block_channel", {"channel": "Neu"}, blocking=True, context=context
    )
    assert hass.states.get(NUMBER).state == "6"
    patcher.stop()


async def test_admins_and_automations_change_without_pin(hass, pauses, hass_admin_user):
    _, _, patcher = await setup(hass)
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    assert hass.states.get(SWITCH).state == "off"
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert hass.states.get(SWITCH).state == "off"
    patcher.stop()


async def test_pin_opens_for_five_minutes_and_every_change_extends(hass, pauses, freezer):
    _, _, patcher = await setup(hass)
    context = await child_context(hass)
    await unlock(hass)
    assert hass.states.get(LOCK).state == "unlocked"
    freezer.tick(240)
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True, context=context
    )
    freezer.tick(240)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(LOCK).state == "unlocked"
    freezer.tick(70)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(LOCK).state == "locked"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "switch", "turn_on", {ATTR_ENTITY_ID: STRICT_SWITCH}, blocking=True, context=context
        )
        await hass.services.async_call(
            "switch", "turn_off", {ATTR_ENTITY_ID: STRICT_SWITCH}, blocking=True, context=context
        )
    patcher.stop()


async def test_lock_button_closes_at_once(hass, pauses):
    _, _, patcher = await setup(hass)
    await unlock(hass)
    await hass.services.async_call("lock", "lock", {ATTR_ENTITY_ID: LOCK}, blocking=True)
    assert hass.states.get(LOCK).state == "locked"
    patcher.stop()


async def test_wrong_pins_block_entry_with_growing_wait(hass, pauses, freezer):
    _, _, patcher = await setup(hass)
    failures = []
    hass.bus.async_listen("parentcontrol_pin_failed", failures.append)
    for _ in range(5):
        with pytest.raises(ServiceValidationError, match="Wrong PIN|wrong_pin|Falscher"):
            await unlock(hass, "0000")
    await hass.async_block_till_done()
    assert len(failures) == 5
    with pytest.raises(ServiceValidationError):
        await unlock(hass)
    freezer.tick(901)
    for _ in range(5):
        with pytest.raises(ServiceValidationError):
            await unlock(hass, "0000")
    freezer.tick(901)
    with pytest.raises(ServiceValidationError):
        await unlock(hass)
    freezer.tick(900)
    await unlock(hass)
    assert hass.states.get(LOCK).state == "unlocked"
    patcher.stop()


async def test_entry_without_pin_stays_locked(hass, pauses):
    _, _, patcher = await setup(hass, **{CONF_PIN_HASH: None})
    with pytest.raises(ServiceValidationError):
        await unlock(hass)
    patcher.stop()


async def test_lock_stays_open_when_a_list_change_reloads(hass, pauses):
    _, _, patcher = await setup(hass)
    context = await child_context(hass)
    await unlock(hass)
    await hass.services.async_call(
        DOMAIN, "allow_channel", {"channel": "Neu"}, blocking=True, context=context
    )
    await hass.async_block_till_done()
    assert hass.states.get(LOCK).state == "unlocked"
    patcher.stop()


async def test_removing_from_the_blocked_list_needs_the_pin(hass, pauses):
    entry, _, patcher = await setup(hass, **{CONF_BLOCKED: "Kanal\nAnderer"})
    context = await child_context(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "remove_channel", {"list": "blocked", "channel": "Kanal"},
            blocking=True, context=context,
        )
    await hass.services.async_call(
        DOMAIN, "remove_channel", {"list": "allowed", "channel": "Die Maus"},
        blocking=True, context=context,
    )
    await hass.async_block_till_done()
    assert "Die Maus" not in entry.options[CONF_ALLOWED]
    await unlock(hass)
    await hass.services.async_call(
        DOMAIN, "remove_channel", {"list": "blocked", "channel": "Kanal"},
        blocking=True, context=context,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_BLOCKED] == "Anderer"
    patcher.stop()


async def test_profile_age_entity_needs_the_pin_to_raise(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=10)
    context = await child_context(hass)
    assert hass.states.get(NUMBER).state == "8"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {ATTR_ENTITY_ID: NUMBER, "value": 12}, blocking=True, context=context
        )
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: NUMBER, "value": 7}, blocking=True, context=context
    )
    assert hass.states.get(NUMBER).state == "7"
    assert entry.runtime_data.profile_age(KIND) == 7
    patcher.stop()


async def test_shorts_are_blocked_before_the_rating(hass, pauses):
    _, mock, patcher = await setup(hass, min_age=4, short=True)
    await play(hass)
    assert len(pauses) == 1
    state = hass.states.get(SENSOR)
    assert state.attributes["sperrgrund"] == "short"
    assert state.attributes["short"] is True
    assert hass.states.get(SHORTS_SWITCH).state == "on"
    patcher.stop()


async def test_shorts_are_blocked_on_allowed_channels_without_the_model(hass, pauses):
    _, mock, patcher = await setup(
        hass, short=True, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: "Kanal; 0"}
    )
    await play(hass)
    assert len(pauses) == 1
    assert not mock.called
    patcher.stop()


async def test_shorts_play_when_the_switch_is_off(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4, short=True)
    entry.runtime_data.async_set_profile_setting(KIND, SETTING_BLOCK_SHORTS, False)
    await play(hass)
    assert not pauses
    patcher.stop()


async def test_long_videos_skip_the_shorts_lookup(hass, pauses):
    _, _, patcher = await setup(
        hass, short=True, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: "Kanal; 0"}
    )
    with patch.object(engine, "fetch_metadata") as lookup:
        await play(hass, attributes={**VIDEO, "media_duration": 600.0})
    assert not lookup.called
    assert not pauses
    patcher.stop()


async def test_history_keeps_the_latest_videos(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, valuable=True)
    await play(hass)
    await play(hass, attributes={**VIDEO, "media_title": "Zweites"})
    state = hass.states.get(HISTORY)
    assert state.state == "Zweites"
    videos = state.attributes["videos"]
    assert [video["titel"] for video in videos] == ["Zweites", "Titel"]
    assert videos[1]["status"] == "frei"
    assert videos[1]["paedagogisch_wertvoll"] is True
    patcher.stop()


async def test_ollama_failure_turns_the_sensor_off_and_raises_a_repair(hass, pauses, freezer, aioclient_mock):
    aioclient_mock.clear_requests()
    aioclient_mock.get("http://ollama.local/api/tags", exc=TimeoutError)
    _, _, patcher = await setup(hass, side_effect=OSError("weg"))
    await play(hass)
    assert hass.states.get(OLLAMA).state == "off"
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, "ollama_down") is None
    freezer.tick(601)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, "ollama_down") is not None
    patcher.stop()


async def test_failed_lookup_turns_the_yt_dlp_sensor_off(hass, pauses):
    _, _, patcher = await setup(hass, meta_failed=True)
    await play(hass)
    assert hass.states.get("binary_sensor.parentcontrol_youtube_lookup").state == "off"
    patcher.stop()


async def test_card_finds_every_entity_through_the_attributes(hass, pauses):
    _, _, patcher = await setup(hass, **{CONF_PROFILE_ALLOWED: {KIND: "Kanal; 6"}})
    lock = hass.states.get(LOCK).attributes
    assert lock["entitaeten"]["lock"] == LOCK
    assert lock["entitaeten"]["check"] == SWITCH
    assert lock["entitaeten"]["ollama"] == OLLAMA
    assert lock["geraete"] == [SENSOR, "sensor.parentcontrol_kids_youtube_check"]
    assert lock["profile"] == [PROFILE_WATCH]
    assert {"kanal": "Die Maus", "alter": 5} in lock["freigegeben"]
    device = hass.states.get(SENSOR).attributes
    assert device["entitaeten"]["select"] == WHO
    assert device["entitaeten"]["history"] == HISTORY
    assert device["entitaeten"]["seek_to_start"] == "switch.parentcontrol_tv_jump_to_start"
    assert device["zugeordnet"] == [KIND]
    assert device["name"] == "tv"
    profile = hass.states.get(PROFILE_WATCH).attributes
    assert profile["name"] == "Kind"
    assert profile["entitaeten"]["block_shorts"] == SHORTS_SWITCH
    assert profile["entitaeten"]["age"] == NUMBER
    assert profile["freigegeben"] == [{"kanal": "Kanal", "alter": 6}]
    assert profile["erlaubte_woerter"] == []
    patcher.stop()


async def test_swear_word_block_logs_the_words_that_triggered_it(hass, pauses):
    entry, _, patcher = await setup(
        hass, min_age=4, profanity=True, words=["Scheiße", "Mist"], settings=[SETTING_BLOCK_PROFANITY]
    )
    paused = []
    hass.bus.async_listen("parentcontrol_paused", paused.append)
    await play(hass)
    text = "Schimpfwörter erkannt: Scheiße, Mist."
    assert hass.states.get(SENSOR).attributes["sperrtext"] == text
    assert hass.states.get(SENSOR).attributes["schimpfwoerter_liste"] == ["Scheiße", "Mist"]
    video = hass.states.get(HISTORY).attributes["videos"][0]
    assert video["sperrtext"] == text
    assert video["schimpfwoerter_liste"] == ["Scheiße", "Mist"]
    assert paused[0].data["block_text"] == text
    assert paused[0].data["swear_words"] == ["Scheiße", "Mist"]
    assert entry.runtime_data._events[-1]["swear_words"] == ["Scheiße", "Mist"]
    patcher.stop()


async def test_every_block_reason_has_a_text(hass, pauses):
    _, _, patcher = await setup(hass, min_age=12, age=8)
    await play(hass)
    assert hass.states.get(SENSOR).attributes["sperrtext"] == (
        "Mindestalter 12 liegt über dem Alter 8. Grund"
    )
    patcher.stop()


async def test_blocked_channel_has_a_text_without_a_rating(hass, pauses):
    _, _, patcher = await setup(hass, **{CONF_BLOCKED: "Kanal"})
    await play(hass)
    video = hass.states.get(HISTORY).attributes["videos"][0]
    assert video["sperrtext"] == "Der Kanal steht auf der Sperrliste."
    patcher.stop()


async def test_allowed_video_has_no_block_text(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4, profanity=True, words=["Mist"])
    await play(hass)
    state = hass.states.get(SENSOR)
    assert state.attributes["sperrtext"] is None
    assert state.attributes["schimpfwoerter_liste"] == ["Mist"]
    patcher.stop()


async def test_history_size_comes_from_the_options(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4, **{CONF_HISTORY_SIZE: 5})
    for number in range(8):
        await play(hass, attributes={**VIDEO, "media_title": f"Video {number}"})
    videos = hass.states.get(HISTORY).attributes["videos"]
    assert [video["titel"] for video in videos] == [f"Video {n}" for n in range(7, 2, -1)]
    patcher.stop()


async def test_smaller_history_size_shortens_stored_lists(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4)
    for number in range(8):
        await play(hass, attributes={**VIDEO, "media_title": f"Video {number}"})
    await entry.runtime_data.async_save_now()
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_HISTORY_SIZE: 5})
    await hass.async_block_till_done()
    assert len(hass.states.get(HISTORY).attributes["videos"]) == 5
    patcher.stop()


FIRE_TV = {"app_id": "com.amazon.firetv.youtube", "source": "YouTube"}


async def test_youtube_is_recognized_by_app_id_and_source(hass, pauses):
    _, mock, patcher = await setup(hass)
    await play(hass, attributes=FIRE_TV)
    assert hass.states.get(SENSOR).state == "keine_daten"
    await play(hass, attributes={"source": "YouTube"})
    assert hass.states.get(SENSOR).state == "keine_daten"
    assert not mock.called
    patcher.stop()


async def test_strict_rating_pauses_youtube_without_title_after_a_grace_time(hass, pauses, freezer):
    _, _, patcher = await setup(hass, settings=[SETTING_STRICT])
    paused = []
    hass.bus.async_listen("parentcontrol_paused", paused.append)
    await play(hass, attributes=FIRE_TV)
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not pauses
    freezer.tick(40)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["sperrtext"] == (
        "Strenge Bewertung: Das Gerät meldet keinen Videotitel."
    )
    assert paused[0].data["block_reason"] == "keine_daten"
    patcher.stop()


async def test_youtube_without_title_keeps_playing_without_strict_rating(hass, pauses, freezer):
    _, _, patcher = await setup(hass)
    await play(hass, attributes=FIRE_TV)
    freezer.tick(300)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not pauses
    patcher.stop()


async def setup_shared(hass, **kwargs):
    """Both children on the TV."""
    return await setup(
        hass, big_age=12, **{CONF_DEVICE_PROFILES: {TV: [KIND, GROSS], KIDS: [GROSS]}}, **kwargs
    )


async def select(hass, option, context=None):
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: WHO, "option": option}, blocking=True, context=context
    )
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_shared_device_uses_the_youngest_age_and_any_block(hass, pauses):
    entry, _, patcher = await setup_shared(hass, min_age=10, age=8)
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["alter"] == 8
    assert hass.states.get(SENSOR).attributes["profil_namen"] == ["Kind", "Gross"]
    patcher.stop()


async def test_shared_device_blocks_shorts_if_one_child_must_not_see_them(hass, pauses):
    entry, _, patcher = await setup_shared(hass, min_age=4, short=True)
    entry.runtime_data.async_set_profile_setting(KIND, SETTING_BLOCK_SHORTS, False)
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_shared_device_skips_checks_only_if_every_child_allows_it(hass, pauses):
    entry, mock, patcher = await setup_shared(hass, min_age=16, **{CONF_ALLOWED: "Kanal; 0"})
    monitor = entry.runtime_data
    monitor.async_set_profile_setting(KIND, SETTING_SKIP_CHECKS, True)
    await play(hass)
    assert mock.called
    monitor.async_set_profile_setting(GROSS, SETTING_SKIP_CHECKS, True)
    await play(hass, attributes={**VIDEO, "media_title": "Anderes"})
    assert hass.states.get(SENSOR).attributes["quelle"] == "freigabeliste"
    patcher.stop()


async def test_choosing_one_child_needs_the_pin_and_automatic_does_not(hass, pauses):
    _, _, patcher = await setup_shared(hass, min_age=10, age=8)
    context = await child_context(hass)
    assert hass.states.get(WHO).state == "Automatic"
    assert hass.states.get(WHO).attributes["options"] == ["Automatic", "Kind", "Gross", "Unrestricted"]
    with pytest.raises(ServiceValidationError):
        await select(hass, "Gross", context)
    await unlock(hass)
    await select(hass, "Gross", context)
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).attributes["profil_namen"] == ["Gross"]
    await hass.services.async_call("lock", "lock", {ATTR_ENTITY_ID: LOCK}, blocking=True)
    await select(hass, "Automatic", context)
    assert hass.states.get(WHO).state == "Automatic"
    patcher.stop()


async def test_unrestricted_checks_nothing_and_counts_nothing(hass, pauses, freezer):
    _, mock, patcher = await setup(hass, min_age=16)
    await unlock(hass)
    await select(hass, "Unrestricted")
    await play(hass)
    assert not pauses
    assert not mock.called
    assert hass.states.get(SENSOR).state == "unbeschraenkt"
    assert hass.states.get(HISTORY).attributes["videos"][0]["status"] == "unbeschraenkt"
    for _ in range(25):
        freezer.tick(5)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(WATCH).state == "2"
    assert hass.states.get(PROFILE_WATCH).state == "0"
    assert hass.states.get("sensor.parentcontrol_videos_today").state == "0"
    patcher.stop()


async def test_choice_falls_back_to_automatic_when_the_device_turns_off(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4)
    await unlock(hass)
    await select(hass, "Unrestricted")
    await play(hass)
    await play(hass, "off")
    assert hass.states.get(WHO).state == "Automatic"
    patcher.stop()


async def test_choice_falls_back_to_automatic_at_midnight(hass, pauses, freezer):
    _, _, patcher = await setup(hass, min_age=4)
    await unlock(hass)
    await select(hass, "Unrestricted")
    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(WHO).state == "Automatic"
    patcher.stop()


async def test_watch_time_counts_for_every_child_on_a_shared_device(hass, pauses, freezer):
    _, _, patcher = await setup_shared(hass, min_age=4)
    await play(hass)
    for _ in range(25):
        freezer.tick(5)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(PROFILE_WATCH).state == "2"
    assert hass.states.get("sensor.parentcontrol_gross_watch_time_today").state == "2"
    patcher.stop()


async def test_allowed_words_do_not_block(hass, pauses):
    _, _, patcher = await setup(
        hass, min_age=4, profanity=True, words=["Mist", "Mistkerl"],
        settings=[SETTING_BLOCK_PROFANITY], **{CONF_ALLOWED_WORDS: "mist"},
    )
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["sperrtext"] == "Schimpfwörter erkannt: Mistkerl."
    patcher.stop()


async def test_allowed_prefix_covers_longer_words(hass, pauses):
    _, _, patcher = await setup(
        hass, min_age=4, profanity=True, words=["Mist", "Mistkerl"],
        settings=[SETTING_BLOCK_PROFANITY], **{CONF_PROFILE_WORDS: {KIND: "Mist*"}},
    )
    await play(hass)
    assert not pauses
    assert hass.states.get(SENSOR).attributes["schimpfwoerter"] is False
    patcher.stop()


async def test_censored_words_can_never_be_allowed(hass, pauses):
    _, _, patcher = await setup(
        hass, min_age=4, profanity=True, words=["[ __ ]"],
        settings=[SETTING_BLOCK_PROFANITY], **{CONF_ALLOWED_WORDS: "*"},
    )
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_profile_without_inherited_words_blocks_global_words(hass, pauses):
    entry, _, patcher = await setup(
        hass, min_age=4, profanity=True, words=["Mist"],
        settings=[SETTING_BLOCK_PROFANITY], **{CONF_ALLOWED_WORDS: "Mist"},
    )
    entry.runtime_data.async_set_profile_setting(KIND, "inherit_words", False)
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_word_must_be_allowed_for_every_child_on_a_shared_device(hass, pauses):
    _, _, patcher = await setup_shared(
        hass, min_age=4, profanity=True, words=["Mist"],
        settings=[SETTING_BLOCK_PROFANITY], **{CONF_PROFILE_WORDS: {GROSS: "Mist"}},
    )
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_model_report_without_words_still_blocks(hass, pauses):
    _, _, patcher = await setup(
        hass, min_age=4, profanity=True, settings=[SETTING_BLOCK_PROFANITY],
        **{CONF_ALLOWED_WORDS: "*"},
    )
    await play(hass)
    assert len(pauses) == 1
    patcher.stop()


async def test_allowing_a_word_needs_the_pin_and_taking_it_back_does_not(hass, pauses):
    entry, _, patcher = await setup(hass)
    context = await child_context(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "allow_word", {"word": "Mist"}, blocking=True, context=context
        )
    await unlock(hass)
    await hass.services.async_call(
        DOMAIN, "allow_word", {"word": "Mist", "profile": "Kind"}, blocking=True, context=context
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_PROFILE_WORDS] == {KIND: "Mist"}
    await hass.services.async_call("lock", "lock", {ATTR_ENTITY_ID: LOCK}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "remove_word", {"word": "mist", "profile": "Kind"}, blocking=True, context=context
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_PROFILE_WORDS] == {KIND: ""}
    patcher.stop()


async def test_inheriting_global_lists_again_needs_the_pin(hass, pauses):
    entry, _, patcher = await setup(hass)
    context = await child_context(hass)
    switch = "switch.parentcontrol_kind_inherit_global_allowed_channels"
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: switch}, blocking=True, context=context)
    assert hass.states.get(switch).state == "off"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: switch}, blocking=True, context=context)
    patcher.stop()


async def test_profile_without_inherited_channels_ignores_global_allowed_list(hass, pauses):
    entry, mock, patcher = await setup(
        hass, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: "Kanal; 0"}
    )
    entry.runtime_data.async_set_profile_setting(KIND, "inherit_channels", False)
    await play(hass)
    assert mock.called
    patcher.stop()


async def test_history_records_the_active_profiles(hass, pauses):
    _, _, patcher = await setup_shared(hass, min_age=4)
    await play(hass)
    video = hass.states.get(HISTORY).attributes["videos"][0]
    assert video["profile"] == [KIND, GROSS]
    assert video["profil_namen"] == ["Kind", "Gross"]
    patcher.stop()


async def test_choice_made_while_the_device_is_off_stays(hass, pauses):
    _, _, patcher = await setup(hass, min_age=4)
    await play(hass, "off")
    await unlock(hass)
    await select(hass, "Unrestricted")
    await play(hass, "off", attributes={})
    assert hass.states.get(WHO).state == "Unrestricted"
    patcher.stop()



def unique(hass, domain, suffix):
    """Find an entity by the end of its unique id."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{suffix}")


def set_limit(entry, minutes, profile=KIND):
    for key in ("limit_weekday", "limit_weekend"):
        entry.runtime_data.async_set_profile_value(profile, key, minutes)


def set_window(entry, start, end, profile=KIND):
    monitor = entry.runtime_data
    for day in ("weekday", "weekend"):
        monitor.async_set_profile_value(profile, f"window_{day}_start", start)
        monitor.async_set_profile_value(profile, f"window_{day}_end", end)


async def tick(hass, freezer, seconds, step=5):
    for _ in range(seconds // step):
        freezer.tick(step)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


def hhmm(minutes_from_now):
    moment = dt_util.now() + timedelta(minutes=minutes_from_now)
    return f"{moment.hour:02d}:{moment.minute:02d}"


async def test_limit_pauses_youtube_and_warns_before(hass, pauses, freezer):
    entry, _, patcher = await setup(hass, min_age=4)
    set_limit(entry, 10)
    events = {"warning": [], "reached": []}
    hass.bus.async_listen("parentcontrol_limit_warning", events["warning"].append)
    hass.bus.async_listen("parentcontrol_limit_reached", events["reached"].append)
    await play(hass)
    await tick(hass, freezer, 330)
    assert len(events["warning"]) == 1
    assert events["warning"][0].data["reason"] == "zeitlimit"
    assert not pauses
    await tick(hass, freezer, 300)
    assert len(pauses) >= 1
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "zeitlimit"
    assert len(events["reached"]) == 1
    assert hass.states.get(unique(hass, "sensor", "profile_kind_remaining")).state == "0"
    patcher.stop()


async def test_bonus_time_needs_the_pin_and_lets_the_child_watch_again(hass, pauses, freezer):
    entry, _, patcher = await setup(hass, min_age=4)
    set_limit(entry, 5)
    await play(hass)
    await tick(hass, freezer, 330)
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "zeitlimit"
    context = await child_context(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "add_time", {"profile": "Kind", "minutes": 15}, blocking=True, context=context
        )
    await unlock(hass)
    await hass.services.async_call(
        DOMAIN, "add_time", {"profile": "Kind", "minutes": 15}, blocking=True, context=context
    )
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state != "blockiert"
    assert entry.runtime_data.remaining_minutes(KIND) >= 14
    patcher.stop()


async def test_bonus_time_ends_at_midnight(hass, pauses, freezer):
    entry, _, patcher = await setup(hass, min_age=4)
    set_limit(entry, 5)
    entry.runtime_data.async_add_time(KIND, 15)
    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert entry.runtime_data.bonus_minutes(KIND) == 0
    patcher.stop()


async def test_raising_or_removing_the_limit_needs_the_pin(hass, pauses):
    entry, _, patcher = await setup(hass)
    set_limit(entry, 60)
    context = await child_context(hass)
    limit = unique(hass, "number", "profile_kind_limit_weekday")
    for value in (90, 0):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number", "set_value", {ATTR_ENTITY_ID: limit, "value": value}, blocking=True, context=context
            )
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: limit, "value": 30}, blocking=True, context=context
    )
    assert hass.states.get(limit).state == "30"
    patcher.stop()


async def test_outside_the_viewing_time_youtube_is_paused(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4, settings=[SETTING_SKIP_CHECKS], **{CONF_ALLOWED: "Kanal; 0"})
    set_window(entry, hhmm(60), hhmm(120))
    await play(hass)
    assert len(pauses) == 1
    assert hass.states.get(SENSOR).attributes["sperrtext"] == "Außerhalb der Schauzeit."
    patcher.stop()


async def test_inside_the_viewing_time_youtube_plays_and_warns_before_the_end(hass, pauses, freezer):
    entry, _, patcher = await setup(hass, min_age=4)
    set_window(entry, hhmm(-60), hhmm(4))
    warnings = []
    hass.bus.async_listen("parentcontrol_limit_warning", warnings.append)
    await play(hass)
    await tick(hass, freezer, 10)
    assert not pauses
    assert warnings and warnings[0].data["reason"] == "schauzeit"
    patcher.stop()


async def test_widening_the_viewing_time_needs_the_pin(hass, pauses):
    entry, _, patcher = await setup(hass)
    set_window(entry, "15:00", "19:00")
    context = await child_context(hass)
    start = unique(hass, "time", "profile_kind_window_weekday_start")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "time", "set_value", {ATTR_ENTITY_ID: start, "time": "14:00:00"}, blocking=True, context=context
        )
    await hass.services.async_call(
        "time", "set_value", {ATTR_ENTITY_ID: start, "time": "16:00:00"}, blocking=True, context=context
    )
    assert hass.states.get(start).state == "16:00:00"
    patcher.stop()


async def test_unrestricted_ignores_limit_and_viewing_time(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4)
    set_window(entry, hhmm(60), hhmm(120))
    await unlock(hass)
    await select(hass, "Unrestricted")
    await play(hass)
    assert not pauses
    patcher.stop()


async def test_shared_device_pauses_when_one_child_reached_its_limit(hass, pauses, freezer):
    entry, _, patcher = await setup_shared(hass, min_age=4)
    set_limit(entry, 5, GROSS)
    await play(hass)
    await tick(hass, freezer, 330)
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "zeitlimit"
    assert entry.runtime_data.youtube_minutes(KIND) == entry.runtime_data.youtube_minutes(GROSS)
    patcher.stop()


async def test_other_apps_do_not_count_for_the_limit(hass, pauses, freezer):
    entry, _, patcher = await setup(hass, min_age=4)
    await play(hass, attributes={**VIDEO, "app_name": "Netflix"})
    await tick(hass, freezer, 130)
    assert entry.runtime_data.youtube_minutes(KIND) == 0
    assert hass.states.get(PROFILE_WATCH).state == "2"
    patcher.stop()


async def test_allowed_video_plays_on_for_the_children_watching(hass, pauses):
    plays = async_mock_service(hass, "media_player", "media_play")
    entry, _, patcher = await setup(hass)
    await play(hass)
    assert len(pauses) == 1
    context = await child_context(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "allow_video", {"player": TV}, blocking=True, context=context)
    await hass.services.async_call(DOMAIN, "allow_video", {"player": TV}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "frei"
    assert len(plays) == 1
    videos = hass.states.get(PROFILE_WATCH).attributes["erlaubte_videos"]
    assert videos == [{"schluessel": "Titel\nKanal", "titel": "Titel", "kanal": "Kanal", "video_id": "id"}]
    await hass.services.async_call(DOMAIN, "remove_video", {"video": "Titel\nKanal"}, blocking=True, context=context)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "blockiert"
    patcher.stop()


async def test_allowed_video_still_obeys_shorts(hass, pauses):
    entry, _, patcher = await setup(hass, short=True)
    await play(hass)
    entry.runtime_data.async_allow_video(TV, [KIND])
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).attributes["sperrgrund"] == "short"
    patcher.stop()


async def test_paused_event_carries_the_video_link(hass, pauses):
    _, _, patcher = await setup(hass)
    paused = []
    hass.bus.async_listen("parentcontrol_paused", paused.append)
    await play(hass)
    assert paused[0].data["url"] == "https://www.youtube.com/watch?v=id"
    assert paused[0].data["profile_ids"] == [KIND]
    patcher.stop()


async def test_transcript_of_a_blocked_video_needs_the_pin(hass, pauses):
    _, _, patcher = await setup(hass, transcript="Ein langer Text")
    await play(hass)
    video = hass.states.get(HISTORY).attributes["videos"][0]
    assert video["schluessel"] == "Titel\nKanal"
    context = await child_context(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "get_transcript", {"video": video["schluessel"]}, blocking=True, context=context, return_response=True
        )
    response = await hass.services.async_call(
        DOMAIN, "get_transcript", {"video": video["schluessel"]}, blocking=True, return_response=True
    )
    assert response == {"transkript": "Ein langer Text"}
    patcher.stop()


async def test_transcript_of_an_allowed_video_is_not_kept(hass, pauses):
    entry, _, patcher = await setup(hass, min_age=4, transcript="Text")
    await play(hass)
    assert entry.runtime_data.transcript("Titel\nKanal") is None
    patcher.stop()


async def test_week_and_daily_report_count_per_child(hass, pauses, freezer):
    entry, _, patcher = await setup(hass)
    set_limit(entry, 30)
    await play(hass)
    await tick(hass, freezer, 130)
    week = hass.states.get(PROFILE_WATCH).attributes["woche"]
    assert week[-1]["minuten"] == 2
    assert week[-1]["limit"] == 30
    assert week[-1]["gesperrt"] == 1
    report = hass.states.get(unique(hass, "sensor", "daily_report"))
    assert report.state == "1"
    assert report.attributes["kinder"][0] | {} == {
        "name": "Kind", "youtube_minuten": 2, "limit": 30, "bonus": 0, "videos": 1, "gesperrt": 1,
    }
    assert report.attributes["gesperrte_videos"][0]["titel"] == "Titel"
    assert report.attributes["gesperrte_videos"][0]["art"] == "alter"
    patcher.stop()


async def test_week_keeps_seven_days(hass, pauses, freezer):
    entry, _, patcher = await setup(hass, min_age=4)
    await play(hass)
    for _ in range(9):
        await tick(hass, freezer, 70)
        freezer.tick(timedelta(days=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(entry.runtime_data.week(KIND)) <= 7
    patcher.stop()
