"""Watches the TV in Home Assistant and pauses videos above the child's age."""
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pruefung

log = logging.getLogger("parentcontrol")

STATUS_SENSOR = "sensor.youtube_pruefung"
RETRY_SECONDS = 600
YOUTUBE_APP = "YouTube"


class HomeAssistant:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.token = token

    def _request(self, path, payload=None):
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    def state(self, entity_id):
        try:
            return self._request(f"/states/{entity_id}")
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise

    def pause(self, entity_id):
        self._request("/services/media_player/media_pause", {"entity_id": entity_id})

    def publish(self, state, attributes):
        self._request(f"/states/{STATUS_SENSOR}", {"state": state, "attributes": attributes})


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                title TEXT, channel TEXT, fsk INTEGER, reason TEXT,
                source TEXT, video_id TEXT, checked_at REAL,
                PRIMARY KEY (title, channel));
            CREATE TABLE IF NOT EXISTS events (
                at REAL, event TEXT, title TEXT, channel TEXT,
                fsk INTEGER, reason TEXT);
            """
        )

    def rating(self, video):
        row = self.db.execute(
            "SELECT fsk, reason, source, video_id FROM ratings WHERE title=? AND channel=?",
            (video.title, video.channel),
        ).fetchone()
        return pruefung.Rating(*row) if row else None

    def save(self, video, rating):
        self.db.execute(
            "INSERT OR REPLACE INTO ratings VALUES (?,?,?,?,?,?,?)",
            (video.title, video.channel, rating.fsk, rating.reason,
             rating.source, rating.video_id, time.time()),
        )
        self.db.commit()

    def log_event(self, event, video, rating=None):
        self.db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?)",
            (time.time(), event, video.title, video.channel,
             rating.fsk if rating else None, rating.reason if rating else None),
        )
        self.db.commit()


class Monitor:
    def __init__(self, ha, store, options, rate_fn, executor):
        self.ha = ha
        self.store = store
        self.options = options
        self.rate_fn = rate_fn
        self.executor = executor
        self.pending = {}
        self.failed = {}
        self.last_status = None

    def _age(self):
        state = self.ha.state(self.options["age_entity"])
        try:
            return int(float(state["state"]))
        except (TypeError, ValueError, KeyError):
            return None

    def _enabled(self):
        state = self.ha.state(self.options["enabled_entity"])
        return state is None or state["state"] != "off"

    def _collect(self):
        for video, future in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[video]
            try:
                rating = future.result()
            except Exception as err:
                log.warning("Einstufung fehlgeschlagen für %r: %s", video.title, err)
                self.failed[video] = (time.monotonic(), str(err))
                self.store.log_event("nicht_geprueft", video)
                continue
            self.failed.pop(video, None)
            self.store.save(video, rating)
            self.store.log_event("eingestuft", video, rating)

    def _rating(self, video):
        rating = self.store.rating(video)
        if rating or video in self.pending:
            return rating
        failed = self.failed.get(video)
        if failed and time.monotonic() - failed[0] < RETRY_SECONDS:
            return None
        self.pending[video] = self.executor.submit(self.rate_fn, video)
        return None

    def _publish(self, status, video=None, rating=None):
        attributes = {"friendly_name": "YouTube-Prüfung"}
        if video:
            attributes |= {"titel": video.title, "kanal": video.channel}
        if rating:
            attributes |= {
                "fsk": rating.fsk,
                "grund": rating.reason,
                "quelle": rating.source,
                "video_id": rating.video_id,
            }
        current = (status, attributes.get("titel"), attributes.get("fsk"))
        if current != self.last_status:
            self.ha.publish(status, attributes)
            self.last_status = current

    def tick(self):
        self._collect()
        player = self.ha.state(self.options["media_player"]) or {}
        attributes = player.get("attributes", {})
        title = attributes.get("media_title")
        if attributes.get("app_name") != YOUTUBE_APP or not title:
            self._publish("inaktiv")
            return
        video = pruefung.Video(
            title, attributes.get("media_artist") or "", attributes.get("media_duration")
        )
        rating = self._rating(video)
        self._collect()
        rating = rating or self.store.rating(video)
        status = pruefung.decide(rating.fsk if rating else None, self._age(), self._enabled())
        if video in self.pending:
            status = "wird_geprueft"
        if status == "blockiert" and player.get("state") == "playing":
            self.ha.pause(self.options["media_player"])
            self.store.log_event("pausiert", video, rating)
            log.info("Pausiert: %r (FSK %s)", video.title, rating.fsk)
        self._publish(status, video, rating)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with open(os.environ.get("OPTIONS_FILE", "/data/options.json"), encoding="utf-8") as file:
        options = json.load(file)
    ha = HomeAssistant(
        os.environ.get("HA_URL", "http://supervisor/core/api"),
        os.environ.get("HA_TOKEN") or os.environ["SUPERVISOR_TOKEN"],
    )
    store = Store(os.environ.get("DB_FILE", "/data/parentcontrol.db"))

    def rate(video):
        return pruefung.rate(video, options["ollama_url"], options["ollama_model"])

    monitor = Monitor(ha, store, options, rate, ThreadPoolExecutor(max_workers=1))
    log.info("ParentControl läuft, beobachte %s", options["media_player"])
    while True:
        try:
            monitor.tick()
        except Exception:
            log.exception("Fehler im Prüfzyklus")
        time.sleep(options["poll_seconds"])


if __name__ == "__main__":
    main()
