"""Tests for the rating logic."""
from unittest.mock import patch

import pytest

from custom_components.parentcontrol import engine
from custom_components.parentcontrol.engine import Metadata, Video

ANSWER = (
    '{"mindestalter": 4, "grund": "ok", "paedagogisch_wertvoll": false, '
    '"paedagogik_grund": "x", "enthaelt_schimpfwoerter": false}'
)


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


@pytest.mark.parametrize(
    "content",
    [
        '{"mindestalter": 19, "paedagogisch_wertvoll": true, "enthaelt_schimpfwoerter": false}',
        '{"mindestalter": "8", "paedagogisch_wertvoll": true, "enthaelt_schimpfwoerter": false}',
        '{"mindestalter": true, "paedagogisch_wertvoll": true, "enthaelt_schimpfwoerter": false}',
        '{"mindestalter": 8, "paedagogisch_wertvoll": "ja", "enthaelt_schimpfwoerter": false}',
        '{"mindestalter": 8, "paedagogisch_wertvoll": true, "enthaelt_schimpfwoerter": "ja"}',
        "{}",
    ],
)
def test_parse_rating_rejects_invalid_age(content):
    with pytest.raises(ValueError):
        engine.parse_rating(content)


def test_parse_rating_accepts_any_age_in_range():
    content = (
        '{"mindestalter": 9, "grund": "ok", "paedagogisch_wertvoll": true, '
        '"paedagogik_grund": "lehrreich", "enthaelt_schimpfwoerter": true}'
    )
    assert engine.parse_rating(content) == (9, "ok", True, "lehrreich", True, [])


def test_word_list_finds_swear_words_the_model_missed():
    meta = Metadata(transcript="ein Lied mit Scheiße im Text")
    with (
        patch.object(engine, "fetch_metadata", return_value=meta),
        patch.object(engine, "ask_ollama", return_value=ANSWER),
    ):
        assert engine.rate(Video("T"), "u", "m", "s").profanity is True


def test_model_finds_swear_words_the_word_list_missed():
    answer = ANSWER.replace('"enthaelt_schimpfwoerter": false', '"enthaelt_schimpfwoerter": true')
    with (
        patch.object(engine, "fetch_metadata", return_value=Metadata()),
        patch.object(engine, "ask_ollama", return_value=answer),
    ):
        assert engine.rate(Video("T"), "u", "m", "s").profanity is True


def test_system_prompt_keeps_fixed_rules_after_editing():
    prompt = engine.build_system_prompt("Alter", "Wert")
    assert prompt.startswith("Alter\n\nWert")
    assert engine.FIXED_PROMPT in prompt


def test_parse_allowed_reads_channels_with_and_without_age():
    text = "Die Maus; 0\n\nBobby & Max;8\nOhne Zahl\nName; mit Semikolon; 12"
    assert engine.parse_allowed(text) == {
        "diemaus": 0,
        "bobbymax": 8,
        "ohnezahl": 0,
        "namemitsemikolon": 12,
    }


@pytest.mark.parametrize("line", ["Kanal; abc", "Kanal; 19", "Kanal; -1"])
def test_parse_allowed_rejects_invalid_age(line):
    with pytest.raises(ValueError):
        engine.parse_allowed(line)


def test_default_allowed_channels_are_valid():
    channels = engine.parse_allowed(engine.DEFAULT_ALLOWED_CHANNELS)
    assert channels["diemaus"] == 5
    assert len(channels) == 13


def test_parse_blocked_ignores_case_and_empty_lines():
    assert engine.parse_blocked("Kanal XY\n\n  kanal xy  \n🧽") == {"kanalxy"}


def test_add_channel_replaces_an_existing_line():
    assert engine.add_channel("Die Maus; 0\nAnders", "die maus", 6) == "Anders\ndie maus; 6"
    assert engine.add_channel("", "Neu") == "Neu"


def test_remove_channel_keeps_other_lines():
    assert engine.remove_channel("Die Maus; 0\nAnders", "DIE MAUS") == "Anders"


def test_is_allowed_includes_the_exact_age():
    assert engine.is_allowed(8, 8)
    assert not engine.is_allowed(9, 8)


def test_age_restricted_video_is_always_18():
    with (
        patch.object(engine, "fetch_metadata", return_value=Metadata(video_id="x", age_limit=18)),
        patch.object(engine, "ask_ollama", return_value=ANSWER.replace("4", "0")),
    ):
        assert engine.rate(Video("T"), "u", "m", "s").min_age == 18


def test_source_names_the_best_available_data():
    with patch.object(engine, "ask_ollama", return_value=ANSWER):
        for meta, source in (
            (Metadata(transcript="text"), "untertitel"),
            (Metadata(description="text"), "metadaten"),
            (Metadata(), "titel"),
        ):
            with patch.object(engine, "fetch_metadata", return_value=meta):
                assert engine.rate(Video("T"), "u", "m", "s").source == source


def test_yt_dlp_failure_falls_back_to_empty_metadata():
    with patch.object(engine, "_extract", side_effect=RuntimeError("kaputt")):
        assert engine.fetch_metadata(Video("T")) == Metadata(failed=True)


def test_shorts_are_recognized_by_their_media_type():
    search = {"entries": [{"id": "abc", "title": "T", "duration": 30}]}
    info = {"media_type": "short", "description": "d"}
    with patch.object(engine, "_extract", side_effect=[search, info]):
        meta = engine.fetch_metadata(Video("T", duration=30))
    assert meta.short
    assert meta.video_id == "abc"


def test_list_entries_keep_the_written_names():
    assert engine.list_entries("Die Maus; 5\n\nlogo!", with_age=True) == [
        {"kanal": "Die Maus", "alter": 5},
        {"kanal": "logo!", "alter": 0},
    ]
    assert engine.list_entries("Böser Kanal", with_age=False) == [{"kanal": "Böser Kanal"}]


def test_found_swear_words_come_from_the_transcript_and_the_model():
    answer = ANSWER.replace(
        '"enthaelt_schimpfwoerter": false',
        '"enthaelt_schimpfwoerter": true, "gefundene_schimpfwoerter": ["Mist", "scheiße"]',
    )
    meta = Metadata(transcript="So eine Scheiße [ __ ] und nochmal scheiße")
    with (
        patch.object(engine, "fetch_metadata", return_value=meta),
        patch.object(engine, "ask_ollama", return_value=answer),
    ):
        rating = engine.rate(Video("T"), "u", "m", "s")
    assert rating.profanity
    assert rating.profanity_words == ["Scheiße", "[ __ ]", "Mist"]


def test_model_words_are_ignored_when_it_finds_no_swearing():
    answer = ANSWER.replace(
        '"enthaelt_schimpfwoerter": false',
        '"enthaelt_schimpfwoerter": false, "gefundene_schimpfwoerter": ["Mist"]',
    )
    with (
        patch.object(engine, "fetch_metadata", return_value=Metadata()),
        patch.object(engine, "ask_ollama", return_value=answer),
    ):
        rating = engine.rate(Video("T"), "u", "m", "s")
    assert not rating.profanity
    assert rating.profanity_words == []


def test_allowed_words_match_whole_words_or_a_prefix():
    patterns = engine.parse_words("Mist\nblöd*\n\n")
    assert patterns == ["mist", "blöd*"]
    assert engine.word_allowed("MIST", patterns)
    assert not engine.word_allowed("Mistkerl", patterns)
    assert engine.word_allowed("Blödmann", patterns)
    assert not engine.word_allowed("[ __ ]", ["*"])


def test_words_are_added_once_and_removed_ignoring_case():
    text = engine.add_word("Mist", "mist")
    assert text == "mist"
    assert engine.remove_word("Mist\nblöd", "MIST") == "blöd"
