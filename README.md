# ParentControl

Home-Assistant-Add-on, das laufende YouTube-Videos auf einem Cast-fähigen TV per Ollama nach FSK einstuft und ungeeignete Videos pausiert.

## Installation

1. Unter **Einstellungen → Add-ons → Add-on Store → Repositories** diese URL hinzufügen: `https://github.com/Hardskiller/parentcontrol`
2. **ParentControl** installieren.
3. In Home Assistant die Helper `input_number.kind_alter` und `input_boolean.youtube_pruefung` anlegen.
4. In den Add-on-Optionen `media_player` und `ollama_url` eintragen und das Add-on starten.

## Grenzen

Die Einstufung ist eine Schätzung eines Sprachmodells, keine offizielle Altersfreigabe. Geprüft werden Titel, Beschreibung und Untertitel, nicht das Bild. Die ersten Sekunden eines Videos laufen immer ungeprüft.
