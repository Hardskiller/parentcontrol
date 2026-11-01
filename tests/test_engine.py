"""Tests for the rating logic."""
from unittest.mock import patch

import pytest

from custom_components.parentcontrol import engine
from custom_components.parentcontrol.engine import Metadata, Video


def test_find_match_needs_same_title_and_duration():
    entries = [
        {"id": "a", "title": "Andere Folge", "duration": 100},
        {"id": "b", "title": "Folge 1 🧽", "duration": 500},
        {"id": "c", "title": "folge 1", "duration": 102},
    ]
    assert engine.find_match(entries, Video("Folge 1", "", 100.4)) == "c"
    assert engine.find_match(entries, Video("Folge 2", "", 100)) is None


def test_pick_caption_prefers_manual_then_original():
    track = lambda url: [{"ext": "vtt", "url": url}]
    info = {
        "subtitles": {"de": track("manual")},
        "automatic_captions": {"de-orig": track("auto")},
    }
    assert engine.pick_caption(info) == "manual"
    info["subtitles"] = {}
    assert engine.pick_caption(info) == "auto"
    assert engine.pick_caption({}) is None


def test_clean_vtt_removes_markup_and_repeats():
    vtt = "WEBVTT\nKind: captions\n\n00:01 --> 00:02\n<c>Hallo</c> Welt\nHallo Welt\nTschüss\n"
    assert engine.clean_vtt(vtt) == "Hallo Welt Tschüss"


def test_excerpts_cover_start_and_end():
    parts = engine.excerpts("a" * 5000 + "z" * 5000, count=3, size=1000)
    assert len(parts) == 3
    assert parts[0].startswith("a")
    assert parts[-1].endswith("z")
    assert engine.excerpts("kurz") == ["kurz"]
    assert engine.excerpts("") == []


def test_profanity_count_includes_censored_captions():
    assert engine.profanity_count("Scheiße [ __ ] Schein") == 2


@pytest.mark.parametrize("content", ['{"mindestalter": 19}', '{"mindestalter": "8"}', '{"mindestalter": true}', "{}"])
def test_parse_rating_rejects_invalid_age(content):
    with pytest.raises(ValueError):
        engine.parse_rating(content)


def test_parse_rating_accepts_any_age_in_range():
    assert engine.parse_rating('{"mindestalter": 9, "grund": "ok"}') == (9, "ok")


def test_is_allowed_includes_the_exact_age():
    assert engine.is_allowed(8, 8)
    assert not engine.is_allowed(9, 8)


def test_age_restricted_video_is_always_18():
    with (
        patch.object(engine, "fetch_metadata", return_value=Metadata(video_id="x", age_limit=18)),
        patch.object(engine, "ask_ollama", return_value='{"mindestalter": 0, "grund": "harmlos"}'),
    ):
        assert engine.rate(Video("T"), "u", "m").min_age == 18


def test_source_names_the_best_available_data():
    with patch.object(engine, "ask_ollama", return_value='{"mindestalter": 4, "grund": "ok"}'):
        for meta, source in (
            (Metadata(transcript="text"), "untertitel"),
            (Metadata(description="text"), "metadaten"),
            (Metadata(), "titel"),
        ):
            with patch.object(engine, "fetch_metadata", return_value=meta):
                assert engine.rate(Video("T"), "u", "m").source == source


def test_yt_dlp_failure_falls_back_to_empty_metadata():
    with patch.object(engine, "_extract", side_effect=RuntimeError("kaputt")):
        assert engine.fetch_metadata(Video("T")) == Metadata()
