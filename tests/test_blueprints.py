"""Render the blueprint templates with Home Assistant's template engine."""
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util import yaml as yaml_util

FOLDER = Path(__file__).parent.parent / "blueprints" / "automation" / "parentcontrol"


def load(name):
    return yaml_util.load_yaml(FOLDER / name)


def render(hass, value, variables):
    if isinstance(value, str):
        return Template(value, hass).async_render(variables)
    if isinstance(value, dict):
        return {key: render(hass, item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [render(hass, item, variables) for item in value]
    return value


def run_variables(hass, data, variables):
    """Render the variables block in order, as an automation does."""
    for key, value in data["variables"].items():
        if isinstance(value, yaml_util.input.Input):
            continue
        variables[key] = render(hass, value, variables)
    return variables


PAUSED = {
    "entity_id": "media_player.tv",
    "title": "Plankton",
    "channel": "Nick",
    "block_reason": "schimpfwoerter",
    "profiles": ["Siva"],
    "profile_ids": ["kind"],
    "url": "https://www.youtube.com/watch?v=xyz",
    "min_age": 6,
}


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("schimpfwoerter", ["Video erlauben", "Kanal freigeben", "Gesperrt lassen", "Video ansehen", "Transkript"]),
        ("zeitlimit", ["Video ansehen"]),
    ],
)
async def test_block_notification_offers_buttons_only_for_video_blocks(hass: HomeAssistant, reason, expected):
    data = load("notify_on_block.yaml")
    variables = run_variables(
        hass,
        data,
        {
            "trigger": {"event": {"data": {**PAUSED, "block_reason": reason}}},
            "context": {"id": "abc"},
            "dashboard": "/lovelace/kids",
            "with_buttons": True,
        },
    )
    assert [action["title"] for action in variables["actions"]] == expected
    message = render(hass, data["action"][0]["message"], variables)
    assert message == "„Plankton“ auf media_player.tv (Siva) wurde pausiert."
    if reason == "schimpfwoerter":
        assert variables["actions"][0]["action"] == "PC_VIDEO_abc"
        assert variables["actions"][-1]["uri"] == "/lovelace/kids"


async def test_daily_report_lists_children_and_blocked_videos(hass: HomeAssistant):
    hass.states.async_set(
        "sensor.report",
        "1",
        {
            "kinder": [{"name": "Siva", "youtube_minuten": 45, "limit": 60, "bonus": 15, "videos": 4, "gesperrt": 1}],
            "gesperrte_videos": [{"zeit": "17:05", "kinder": ["Siva"], "titel": "Plankton", "art": "schimpfwoerter"}],
        },
    )
    data = load("daily_report.yaml")
    variables = run_variables(hass, data, {"report": "sensor.report"})
    message = render(hass, data["action"][0]["message"], variables)
    assert "Siva: 45 von 75 min YouTube (Bonus 15), 4 Videos, 1 gesperrt" in message
    assert "17:05 Siva: Plankton (Schimpfwörter)" in message


async def test_announcement_speaks_to_the_child_without_swear_words(hass: HomeAssistant):
    data = load("announce.yaml")
    trigger = {"id": "block", "event": {"data": PAUSED}}
    variables = run_variables(hass, data, {"trigger": trigger, "players": []})
    assert variables["message"].strip() == "In diesem Video wird geschimpft. Such dir bitte ein anderes aus."
    trigger = {"id": "warning", "event": {"data": {"reason": "zeitlimit", "minutes": 5, "entity_id": "x"}}}
    variables = run_variables(hass, data, {"trigger": trigger, "players": []})
    assert variables["message"].strip() == "Noch 5 Minuten YouTube für heute."


async def test_time_limit_notification_texts(hass: HomeAssistant):
    data = load("time_limit.yaml")
    trigger = {"id": "reached", "event": {"data": {"profile": "Siva", "reason": "schauzeit", "minutes": 0}}}
    variables = run_variables(hass, data, {"trigger": trigger})
    assert render(hass, data["action"][0]["message"], variables).strip() == "Die Schauzeit ist vorbei."
