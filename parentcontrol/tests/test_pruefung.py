import os
import sys
import unittest
from concurrent.futures import Future

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import main
import pruefung
from pruefung import Metadata, Rating, Video

OPTIONS = {
    "media_player": "media_player.tv",
    "age_entity": "input_number.kind_alter",
    "enabled_entity": "input_boolean.youtube_pruefung",
}


class ImmediateExecutor:
    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as err:
            future.set_exception(err)
        return future


class FakeHa:
    def __init__(self, age="8", enabled="on"):
        self.player = {
            "state": "playing",
            "attributes": {
                "app_name": "YouTube",
                "media_title": "Titel",
                "media_artist": "Kanal",
                "media_duration": 100.0,
            },
        }
        self.age = age
        self.enabled = enabled
        self.pauses = 0
        self.published = []

    def state(self, entity_id):
        if entity_id == OPTIONS["media_player"]:
            return self.player
        value = self.age if entity_id == OPTIONS["age_entity"] else self.enabled
        return None if value is None else {"state": value}

    def pause(self, entity_id):
        self.pauses += 1

    def publish(self, state, attributes):
        self.published.append(state)


def monitor(ha, rate_fn):
    return main.Monitor(ha, main.Store(":memory:"), OPTIONS, rate_fn, ImmediateExecutor())


class ParsingTests(unittest.TestCase):
    def test_find_match_needs_same_title_and_duration(self):
        entries = [
            {"id": "a", "title": "Andere Folge", "duration": 100},
            {"id": "b", "title": "Folge 1 🧽", "duration": 500},
            {"id": "c", "title": "folge 1", "duration": 102},
        ]
        self.assertEqual(pruefung.find_match(entries, Video("Folge 1", "", 100.4)), "c")
        self.assertIsNone(pruefung.find_match(entries, Video("Folge 2", "", 100)))

    def test_pick_caption_prefers_manual_then_original(self):
        track = lambda url: [{"ext": "vtt", "url": url}]
        info = {"subtitles": {"de": track("manual")}, "automatic_captions": {"de-orig": track("auto")}}
        self.assertEqual(pruefung.pick_caption(info), "manual")
        info["subtitles"] = {}
        self.assertEqual(pruefung.pick_caption(info), "auto")
        self.assertIsNone(pruefung.pick_caption({}))

    def test_clean_vtt_removes_markup_and_repeats(self):
        vtt = "WEBVTT\nKind: captions\n\n00:01 --> 00:02\n<c>Hallo</c> Welt\nHallo Welt\nTschüss\n"
        self.assertEqual(pruefung.clean_vtt(vtt), "Hallo Welt Tschüss")

    def test_excerpts_cover_start_and_end(self):
        text = "a" * 5000 + "z" * 5000
        parts = pruefung.excerpts(text, count=3, size=1000)
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].startswith("a"))
        self.assertTrue(parts[-1].endswith("z"))
        self.assertEqual(pruefung.excerpts("kurz"), ["kurz"])
        self.assertEqual(pruefung.excerpts(""), [])

    def test_profanity_count_includes_censored_captions(self):
        self.assertEqual(pruefung.profanity_count("Scheiße [ __ ] Schein"), 2)

    def test_parse_rating_rejects_unknown_level(self):
        self.assertEqual(pruefung.parse_rating('{"fsk": 6, "grund": "ok"}'), (6, "ok"))
        with self.assertRaises(ValueError):
            pruefung.parse_rating('{"fsk": 7, "grund": "x"}')

    def test_decide(self):
        self.assertEqual(pruefung.decide(6, 6, True), "frei")
        self.assertEqual(pruefung.decide(12, 8, True), "blockiert")
        self.assertEqual(pruefung.decide(12, 8, False), "aus")
        self.assertEqual(pruefung.decide(None, 8, True), "nicht_geprueft")
        self.assertEqual(pruefung.decide(12, None, True), "nicht_geprueft")

    def test_age_restricted_video_is_always_18(self):
        meta = Metadata(video_id="x", age_limit=18)
        original_fetch, original_ask = pruefung.fetch_metadata, pruefung.ask_ollama
        pruefung.fetch_metadata = lambda video: meta
        pruefung.ask_ollama = lambda *args: '{"fsk": 0, "grund": "harmlos"}'
        try:
            self.assertEqual(pruefung.rate(Video("T"), "u", "m").fsk, 18)
        finally:
            pruefung.fetch_metadata, pruefung.ask_ollama = original_fetch, original_ask


class MonitorTests(unittest.TestCase):
    def test_blocked_video_is_paused_again_after_every_play(self):
        ha = FakeHa()
        m = monitor(ha, lambda video: Rating(16, "hart", "untertitel"))
        m.tick()
        self.assertEqual(ha.pauses, 1)
        ha.player["state"] = "paused"
        m.tick()
        self.assertEqual(ha.pauses, 1)
        ha.player["state"] = "playing"
        m.tick()
        self.assertEqual(ha.pauses, 2)

    def test_allowed_video_keeps_playing(self):
        ha = FakeHa()
        m = monitor(ha, lambda video: Rating(6, "ok", "titel"))
        m.tick()
        self.assertEqual(ha.pauses, 0)
        self.assertEqual(ha.published[-1], "frei")

    def test_switch_off_never_pauses(self):
        ha = FakeHa(enabled="off")
        m = monitor(ha, lambda video: Rating(18, "hart", "titel"))
        m.tick()
        self.assertEqual(ha.pauses, 0)
        self.assertEqual(ha.published[-1], "aus")

    def test_missing_age_keeps_playing_unchecked(self):
        ha = FakeHa(age=None)
        m = monitor(ha, lambda video: Rating(18, "hart", "titel"))
        m.tick()
        self.assertEqual(ha.pauses, 0)
        self.assertEqual(ha.published[-1], "nicht_geprueft")

    def test_ollama_failure_keeps_playing_and_waits_before_retry(self):
        ha = FakeHa()
        calls = []

        def fail(video):
            calls.append(video)
            raise OSError("Ollama weg")

        m = monitor(ha, fail)
        m.tick()
        m.tick()
        self.assertEqual(ha.pauses, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(ha.published[-1], "nicht_geprueft")

    def test_rating_comes_from_cache_on_second_view(self):
        ha = FakeHa()
        calls = []

        def rate(video):
            calls.append(video)
            return Rating(6, "ok", "titel")

        m = monitor(ha, rate)
        m.tick()
        m.tick()
        self.assertEqual(len(calls), 1)

    def test_other_apps_are_ignored(self):
        ha = FakeHa()
        ha.player["attributes"]["app_name"] = "Netflix"
        m = monitor(ha, lambda video: Rating(18, "hart", "titel"))
        m.tick()
        self.assertEqual(ha.pauses, 0)
        self.assertEqual(ha.published[-1], "inaktiv")


if __name__ == "__main__":
    unittest.main()
