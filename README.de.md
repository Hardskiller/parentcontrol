# ParentControl

[English version](README.md)

Home-Assistant-Integration, die laufende YouTube-Videos mit einem lokalen Ollama-Modell auf ein Mindestalter einschätzt und ungeeignete Videos automatisch pausiert.

## Funktionen

- Überwacht beliebig viele Media Player
- Mindestalter von 0 bis 18, mit Standardalter und optional eigenem Alter pro Gerät
- Optional pro Gerät: an den Anfang springen, nur pädagogisch wertvolle Videos, Schimpfwörter blockieren, strenge Bewertung, Shorts sperren
- PIN-Schloss: Ohne PIN können Benutzer ohne Adminrechte den Schutz nicht lockern
- Dashboard-Karte mit Geräteliste, PIN-Feld, Einstellungen, Kanallisten und Verlauf
- Freigegebene und gesperrte Kanäle, global und pro Gerät, optional mit Mindestalter
- Editierbare Prompts für Alterseinstufung und pädagogische Bewertung
- Schauzeit pro Gerät, die letzten Videos pro Gerät (standardmäßig 20, einstellbar) und tägliche Videostatistik
- Warnungen, wenn Ollama oder die YouTube-Abfrage nicht mehr funktionieren
- Läuft auf jeder Home-Assistant-Installation, die HACS unterstützt

## Voraussetzungen

- Home Assistant mit [HACS](https://www.hacs.xyz)
- Ein erreichbarer [Ollama](https://ollama.com)-Server mit mindestens einem Modell
- Media Player, die App, Titel und Status melden. Getestet ist bisher nur Google Cast.

## Installation

1. In HACS unter **⋮ → Benutzerdefinierte Repositories** `https://github.com/Hardskiller/parentcontrol` als Typ **Integration** hinzufügen.
2. **ParentControl** herunterladen und Home Assistant neu starten. `yt-dlp` installiert Home Assistant dabei automatisch.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** **ParentControl** wählen.
4. Ollama-Adresse, Modell, Media Player, Standardalter und einen PIN mit 4 bis 8 Ziffern eintragen.

## Bedienung

Für alle Geräte gelten:

- **Standardalter:** gilt, solange ein Gerät kein eigenes Alter hat.
- **Prüfung:** Schalter, der die Prüfung für alle Geräte abschaltet.
- **Videos, Genehmigt, Pädagogisch wertvoll und Geskippt heute:** zählen jedes Video einmal pro Tag. Das Attribut `gesamt` enthält den Wert seit der Installation.
- **Optionen der Integration:** Modell, Geräteauswahl, PIN, gespeicherte Videos pro Gerät (5 bis 100, standardmäßig 20), eigenes Alter pro Gerät und die editierbaren Prompts. Nach einer Prompt-Änderung werden Videos neu geprüft. Nur Admins können sie öffnen.
- **Einstellungen:** Schloss, das die Einstellungen schützt, siehe [PIN-Schloss](#pin-schloss).
- **Ollama und YouTube-Abfrage:** zeigen, ob beide Dienste funktionieren. Nach 10 Minuten Ausfall zeigt Home Assistant eine Warnung unter **Einstellungen → Reparaturen**.

Jedes überwachte Gerät erscheint als eigenes Gerät unter ParentControl. Dort liegen:

- **An den Anfang springen:** springt nach dem Pausieren auf den Videoanfang. Standard ist nur Pausieren.
- **Nur pädagogisch wertvoll:** blockiert auch altersgerechte Videos ohne Lernwert. Ohne Schalter wird die Bewertung nur angezeigt.
- **Schimpfwörter blockieren:** blockiert auch altersgerechte Videos, zum Beispiel Musikvideos. Erkannt wird das über eine Wortliste im gesamten Transkript und über das Modell. Ohne Untertitel beurteilt das Modell nur Titel und Beschreibung, und Liedtexte können dann unerkannt bleiben.
- **Strenge Bewertung:** blockiert Videos ohne Untertitel und Videos, deren Prüfung fehlgeschlagen ist, etwa wenn Ollama nicht erreichbar ist. Das trifft auch viele harmlose Videos, vor allem Musik.
- **Shorts sperren:** pausiert jeden YouTube-Short, auch von freigegebenen Kanälen. Standardmäßig an.
- **Freigegebene Kanäle überspringen alle Prüfungen:** Mit Schalter läuft ein freigegebener Kanal ohne Prüfung. Ohne Schalter greifen Alter und Schimpfwörter weiter, nur fehlende Untertitel und fehlender pädagogischer Wert blockieren nicht.
- **YouTube-Prüfung:** zeigt Status, Titel, Mindestalter, Bewertungen und Begründungen.
- **Alter:** das Alter dieses Geräts. Es zeigt das Standardalter, bis du es änderst.
- **Schauzeit heute:** zählt die Minuten, in denen das Gerät abspielt, mit jeder App.
- **Letzte Videos:** der neueste Titel als Zustand, die letzten Videos im Attribut `videos` mit Uhrzeit, Kanal, Entscheidung, Begründungen und Kennzeichen für pädagogischen Wert, Schimpfwörter und Shorts. Jedes gesperrte Video hat einen `sperrtext`, der den Auslöser nennt. Bei Schimpfwörtern stehen dort die gefundenen Wörter, zusätzlich in `schimpfwoerter_liste`.

## PIN-Schloss

Das Schloss **Einstellungen** entscheidet, wer den Schutz lockern darf. Solange es zu ist, können Benutzer ohne Adminrechte keine Prüfung abschalten, kein Alter erhöhen, keinen Kanal freigeben und keinen Kanal aus der Sperrliste nehmen. Strenger machen geht immer: eine Prüfung einschalten, ein Alter senken oder einen Kanal sperren.

Geöffnet wird es mit dem PIN am Schloss. Es bleibt 5 Minuten offen, und jede Änderung startet die 5 Minuten neu. Zum Schließen braucht es keinen PIN. Nach 5 falschen PINs wird 15 Minuten lang kein PIN angenommen, und jede weitere Sperre dauert doppelt so lang. Jeder falsche PIN steht im Logbuch und löst das Event `parentcontrol_pin_failed` aus, zum Beispiel für eine Benachrichtigung.

Admins und Automationen betrifft das Schloss nicht. Der PIN wird nur als Hash gespeichert; wer ihn vergisst, legt in den Optionen der Integration einen neuen fest.

Zustände kann Home Assistant vor Benutzern nicht verbergen. Jeder Angemeldete kann Status und die letzten Videos lesen.

Fällt ein Video durch die Prüfung, wird es pausiert. Die Integration prüft das alle 3 Sekunden, solange das Video weiterläuft, und löst das Event `parentcontrol_paused` mit `block_reason`, `block_text` und `swear_words` aus. Im Logbuch steht derselbe Text. Die Schimpfwörter stammen aus der Wortliste über das ganze Transkript und vom Modell, das die gefundenen Wörter nennt.

## Dashboard-Karte

Die Integration bringt eine eigene Karte mit und lädt sie auf jedem Dashboard, ein zusätzlicher Download ist nicht nötig. Du fügst sie im Dashboard-Editor unter **ParentControl** hinzu oder per YAML:

```yaml
type: custom:parentcontrol-card
```

Ohne PIN zeigt die Karte nur die Geräteliste: Status, Alter, Schauzeit, den laufenden Titel und Symbole für pädagogisch wertvolle Videos und Schimpfwörter. Ein Tipp auf ein Gerät, auf **Verlauf** oder **Allgemein** fragt zuerst nach dem PIN. Danach siehst du:

- **Gerät:** das laufende Video mit Begründungen, das Alter, alle Schalter, die Kanallisten dieses Geräts und seine letzten Videos
- **Verlauf:** die letzten Videos aller Geräte, jeweils mit Knöpfen, um den Kanal freizugeben oder zu sperren. Bei jedem gesperrten Eintrag steht der Sperrgrund in Rot; ein Tipp auf den Eintrag zeigt die Einstufung des Modells. **Mehr anzeigen** lädt weitere Einträge.
- **Allgemein:** den Schalter „Prüfung“, das Standardalter, die Listen für alle Geräte, die Statistik von heute und den Zustand von Ollama und der YouTube-Abfrage

Schließt das Schloss wieder, springt die Karte zur Geräteliste zurück. Admins sehen alles ohne PIN.

Die Karte hat einen visuellen Editor mit diesen Einstellungen:

| Option | Bedeutung |
|---|---|
| `title` | Titel der Karte |
| `entity` | Schloss-Entität, falls sie nicht automatisch gefunden wird |
| `show_valuable`, `show_profanity`, `show_shorts` | Symbole für pädagogisch wertvoll, Schimpfwörter und Shorts, standardmäßig an |
| `show_age`, `show_watch_time` | Alter und Schauzeit in der Geräteliste, standardmäßig an |
| `history_limit` | Einträge im Verlauf vor **Mehr anzeigen**, standardmäßig 10 |
| `names` | Anzeigenamen pro Gerät, zugeordnet über seinen Statussensor |

## Kanallisten

Die Listen bearbeitest du in den Optionen der Integration, global und pro Gerät, mit einem Kanal pro Zeile. Freigegebene Kanäle können nach einem Semikolon ein Mindestalter haben. Ohne Zahl gilt 0.

```text
Die Maus; 0
Checker Tobi; 6
```

Namen müssen vollständig passen, ohne Rücksicht auf Groß- und Kleinschreibung, Leerzeichen und Zeichen. Für ein Gerät zählen beide Listen zusammen. Eine Sperre gewinnt immer, und bei Freigaben geht der Geräteeintrag vor dem globalen. Ist ein Kind jünger als das eingetragene Alter, wird das Video normal geprüft. Ein freigegebener Kanal gilt als Ganzes, auch für Videos, die niemand gesehen hat.

Die Freigabeliste startet mit bekannten deutschen Kinderkanälen. Die Alterswerte sind Schätzungen, keine offiziellen Freigaben, und du kannst jede Zeile ändern oder löschen.

Drei Aktionen ändern die Listen ohne die Optionen: `parentcontrol.allow_channel` und `parentcontrol.block_channel` holen einen Kanal aus der jeweils anderen Liste heraus, und `parentcontrol.remove_channel` entfernt ihn aus der Liste in `list` (`allowed` oder `blocked`). Freigeben und aus der Sperrliste entfernen brauchen den PIN. Ohne `channel` nehmen sie den laufenden Kanal von `player`, das ergibt einen einfachen Dashboard-Knopf:

```yaml
type: button
name: Kanal freigeben
tap_action:
  action: perform-action
  perform_action: parentcontrol.allow_channel
  data:
    player: media_player.tv
    age: 6
```

## So wird geprüft

Die Integration sucht das Video über Titel, Kanal und Dauer, lädt Beschreibung und Untertitel und schickt Auszüge an Ollama. Titel und Kanal gehen dafür an YouTube, die Bewertung selbst bleibt lokal.

## Grenzen

- Das Mindestalter ist die Schätzung eines Sprachmodells, keine offizielle Altersfreigabe. Es kann falsch sein.
- Geprüft wird nur Text, nicht das Bild.
- Der Anfang eines Videos läuft immer ungeprüft, bis Titel und Einschätzung vorliegen. Das gilt auch für Shorts: Jeder Short läuft an, bevor er erkannt ist, und nach dem Wischen startet der nächste. Ganz ausblenden kann Shorts nur YouTube selbst, zum Beispiel mit einem beaufsichtigten Konto.
- Ohne strenge Bewertung läuft ein Video weiter, wenn Ollama ausfällt oder es keine Daten gibt.
- Erfasst werden nur überwachte Media Player. Browser auf Laptops, Handys, Tablets und Spielkonsolen können die Prüfung umgehen. Die Home-Assistant-App auf dem iPhone meldet nicht, was andere Apps abspielen.
- Das Abrufen über `yt-dlp` ist von YouTube nicht vorgesehen und kann jederzeit aufhören zu funktionieren.

Die Integration ersetzt keine Aufsicht.

## Lizenz

MIT
