# ParentControl

[English version](README.md)

Home-Assistant-Integration, die laufende YouTube-Videos mit einem lokalen Ollama-Modell auf ein Mindestalter einschätzt und ungeeignete Videos automatisch pausiert.

## Funktionen

- Überwacht beliebig viele Media Player
- Kinderprofile mit eigenem Alter, eigenen Regeln, Listen und erlaubten Schimpfwörtern, optional mit einer Person aus Home Assistant verknüpft
- Mehrere Kinder pro Gerät; am gemeinsamen Gerät gilt die strengste Regel
- „Wer schaut?“ pro Gerät, auch mit „Unbeschränkt“ für Erwachsene
- Regeln pro Kind: nur pädagogisch wertvolle Videos, Schimpfwörter blockieren, strenge Bewertung, Shorts sperren
- Tägliches YouTube-Limit und Schauzeiten pro Kind, getrennt für Werktage und Wochenende, mit Vorwarnung und Bonuszeit für heute
- Erlaubte Videos und das Transkript gesperrter Videos, um direkt aus einer Nachricht zu entscheiden
- PIN-Schloss: Ohne PIN können Benutzer ohne Adminrechte den Schutz nicht lockern
- Dashboard-Karte mit Geräteliste, PIN-Feld, Profilen, Kanallisten und Verlauf
- Freigegebene und gesperrte Kanäle sowie erlaubte Schimpfwörter, global und pro Kind
- Editierbare Prompts für Alterseinstufung und pädagogische Bewertung
- Schauzeit pro Gerät und pro Kind, die letzten sieben Tage pro Kind, die letzten Videos pro Gerät (standardmäßig 20, einstellbar) und tägliche Videostatistik
- Warnungen, wenn Ollama oder die YouTube-Abfrage nicht mehr funktionieren
- Automationsvorlagen für Benachrichtigungen mit Knöpfen, Ansagen, das Zeitlimit und einen Tagesbericht
- Läuft auf jeder Home-Assistant-Installation, die HACS unterstützt

## Voraussetzungen

- Home Assistant ab 2026.8 mit [HACS](https://www.hacs.xyz)
- Ein erreichbarer [Ollama](https://ollama.com)-Server mit mindestens einem Modell
- Media Player, die App, Titel und Status melden, siehe [Unterstützte Geräte](#unterstützte-geräte)

## Installation

1. In HACS unter **⋮ → Benutzerdefinierte Repositories** `https://github.com/Hardskiller/parentcontrol` als Typ **Integration** hinzufügen.
2. **ParentControl** herunterladen und Home Assistant neu starten. `yt-dlp` installiert Home Assistant dabei automatisch.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** **ParentControl** wählen.
4. Ollama-Adresse, Modell, Media Player, einen PIN mit 4 bis 8 Ziffern und das erste Kind mit Name, Alter und optional einer Person eintragen. Dieses Kind gilt für alle ausgewählten Geräte.

Version 0.3.6 stellt auf Kinderprofile um. Beim Update von einer älteren Version ParentControl entfernen und neu einrichten.

## Kinderprofile

Jedes Kind ist ein Profil und erscheint als eigenes Gerät unter ParentControl. Ein Profil hat einen Namen und lässt sich mit einer Person aus Home Assistant verknüpfen; die Karte zeigt dann deren Bild.

Kinder legst du in den Optionen der Integration an, benennst sie um oder entfernst sie und ordnest sie dort den Geräten zu. Jedes Gerät braucht mindestens ein Kind. Die Regeln eines Kindes stellst du in der Karte oder über diese Entitäten ein:

- **Alter:** Mindestalter, das für dieses Kind gilt.
- **Nur pädagogisch wertvoll:** blockiert auch altersgerechte Videos ohne Lernwert. Ohne Schalter wird die Bewertung nur angezeigt. Der Standard-Prompt ist streng: Let's Plays und Gameplay gelten als Unterhaltung, außer sie erklären überwiegend etwas, etwa ein Tutorial.
- **Schimpfwörter blockieren:** blockiert auch altersgerechte Videos, zum Beispiel Musikvideos. Erkannt wird das über eine Wortliste im gesamten Transkript und über das Modell. Ohne Untertitel beurteilt das Modell nur Titel und Beschreibung, und Liedtexte können dann unerkannt bleiben.
- **Strenge Bewertung:** blockiert Videos ohne Untertitel und Videos, deren Prüfung fehlgeschlagen ist, etwa wenn Ollama nicht erreichbar ist. Außerdem pausiert sie YouTube, wenn das Gerät 150 Sekunden lang keinen Titel meldet. Das trifft auch viele harmlose Videos, vor allem Musik.
- **Shorts sperren:** pausiert jeden YouTube-Short, auch von freigegebenen Kanälen. Standardmäßig an.
- **Freigegebene Kanäle überspringen alle Prüfungen:** Mit Schalter läuft ein freigegebener Kanal ohne Prüfung. Ohne Schalter greifen Alter und Schimpfwörter weiter, nur fehlende Untertitel und fehlender pädagogischer Wert blockieren nicht.
- **Globale Freigaben übernehmen** und **Globale Wörter übernehmen:** ob die Listen für alle Kinder auch für dieses Kind gelten. Standardmäßig an.
- **Schauzeit heute:** Minuten, in denen ein Gerät mit diesem Kind abspielt, mit jeder App.
- **YouTube-Limit Mo–Fr** und **YouTube-Limit Sa–So:** Minuten YouTube pro Tag, 0 heißt kein Limit. Ein Limit erhöhen oder aufheben braucht den PIN.
- **Schauzeit Mo–Fr ab/bis** und **Sa–So ab/bis:** wann das Kind YouTube schauen darf. Gleicher Beginn und gleiches Ende heißt ganztägig, so ist es voreingestellt. Das Fenster zu vergrößern braucht den PIN.
- **Restzeit heute:** verbleibende YouTube-Minuten, unbekannt ohne Limit.

Fürs Limit zählt nur YouTube. Am gemeinsamen Gerät mit „Automatisch“ zählt die Zeit für jedes zugeordnete Kind, und YouTube pausiert, sobald eines davon sein Limit erreicht oder seine Schauzeit verlässt. Limit und Schauzeit gelten auch für freigegebene Kanäle und erlaubte Videos, aber nicht bei „Unbeschränkt“. Ein paar Minuten vorher löst ParentControl `parentcontrol_limit_warning` aus, beim Erreichen pausiert es und löst `parentcontrol_limit_reached` aus, beides einmal pro Tag und Kind. Die Vorwarnzeit stellst du in den Optionen ein, standardmäßig 5 Minuten.

**Bonuszeit:** Die Karte bietet pro Kind „+15 min“ und „+30 min“, die Aktion `parentcontrol.add_time` nimmt beliebige Minuten. Das braucht den PIN, gilt nur heute und verfällt um Mitternacht.

Sind einem Gerät mehrere Kinder zugeordnet, gilt die strengste Regel: das jüngste Alter, jeder Sperr-Schalter, den irgendein Kind an hat, und „alle Prüfungen überspringen“ nur, wenn es bei jedem Kind an ist. Ein Kanal oder ein Wort ist nur frei, wenn jedes Kind ihn erlaubt.

## Wer schaut?

Jedes Gerät hat eine Auswahl **Wer schaut?**, in der Karte und als Entität:

- **Automatisch:** alle dem Gerät zugeordneten Kinder, mit der strengsten Regel. Braucht nie den PIN.
- **Ein einzelnes Kind:** Es gelten nur seine Regeln. Braucht den PIN.
- **Unbeschränkt:** keine Prüfung, zum Beispiel wenn Erwachsene schauen. Braucht den PIN. Der Verlauf protokolliert die Videos weiter, die Zeit zählt aber für kein Kind.

Eine Auswahl gilt, bis das Gerät ausgeht, spätestens bis Mitternacht. Danach steht sie wieder auf **Automatisch**.

## Bedienung

Für alle Geräte gelten:

- **Prüfung:** Schalter, der die Prüfung für alle Geräte abschaltet.
- **Videos, Genehmigt, Pädagogisch wertvoll und Geskippt heute:** zählen jedes Video einmal pro Tag. Das Attribut `gesamt` enthält den Wert seit der Installation.
- **Optionen der Integration:** Modell, Geräteauswahl, PIN, gespeicherte Videos pro Gerät (5 bis 100, standardmäßig 20), Vorwarnzeit, Kinder und ihre Zuordnung, Listen und die editierbaren Prompts. Nach einer Prompt-Änderung werden Videos neu geprüft. Nur Admins können sie öffnen.
- **Einstellungen:** Schloss, das die Einstellungen schützt, siehe [PIN-Schloss](#pin-schloss).
- **Ollama und YouTube-Abfrage:** zeigen, ob beide Dienste funktionieren. Nach 10 Minuten Ausfall zeigt Home Assistant eine Warnung unter **Einstellungen → Reparaturen**.
- **Tagesbericht:** die Zahl der heute gesperrten Videos; die Attribute enthalten pro Kind YouTube-Zeit, Limit, Bonuszeit, Videos und Sperren sowie die gesperrten Videos mit der Art der Sperre.

Jedes überwachte Gerät erscheint als eigenes Gerät unter ParentControl. Dort liegen:

- **Wer schaut?:** siehe oben.
- **An den Anfang springen:** springt nach dem Pausieren auf den Videoanfang. Standard ist nur Pausieren.
- **YouTube-Prüfung:** zeigt Status, Titel, Mindestalter, Bewertungen, Begründungen und die aktiven Kinder.
- **Schauzeit heute:** zählt die Minuten, in denen das Gerät abspielt, mit jeder App.
- **Letzte Videos:** der neueste Titel als Zustand, die letzten Videos im Attribut `videos` mit Uhrzeit, Kanal, Entscheidung, Begründungen, aktiven Kindern und Kennzeichen für pädagogischen Wert, Schimpfwörter und Shorts. Jedes gesperrte Video hat einen `sperrtext`, der den Auslöser nennt. Bei Schimpfwörtern stehen dort die gefundenen Wörter, zusätzlich in `schimpfwoerter_liste`.

Fällt ein Video durch die Prüfung, wird es pausiert. Die Integration prüft das alle 3 Sekunden, solange das Video weiterläuft, und löst das Event `parentcontrol_paused` mit `block_reason`, `block_text`, `swear_words`, `profiles`, `profile_ids`, `video_id` und `url` aus. Im Logbuch steht derselbe Text.

## Erlaubte Videos und Transkripte

Ein gesperrtes Video lässt sich für die Kinder erlauben, die gerade geschaut haben: mit dem Knopf in der Nachricht oder mit der Aktion `parentcontrol.allow_video` und dem `player`. Es läuft sofort weiter und bleibt danach für diese Kinder erlaubt. Shorts, Limit und Schauzeit gelten trotzdem, und ein gesperrter Kanal gewinnt weiterhin. Die Karte listet die erlaubten Videos pro Kind; entfernen geht ohne PIN.

ParentControl speichert das Transkript der letzten 50 gesperrten Videos, jeweils bis zu 20.000 Zeichen. Es stammt aus den Untertiteln, die YouTube liefert; Musikvideos haben oft keine. In der Karte bietet ein aufgeklappter Verlaufseintrag **Transkript anzeigen** und einen Link zum Video auf YouTube. Das Transkript kann Schimpfwörter im Klartext enthalten und braucht deshalb den PIN, auch über die Aktion `parentcontrol.get_transcript`.

## PIN-Schloss

Das Schloss **Einstellungen** entscheidet, wer den Schutz lockern darf. Solange es zu ist, können Benutzer ohne Adminrechte keine Prüfung abschalten, kein Alter erhöhen, keinen Kanal und kein Wort freigeben, keinen Kanal aus der Sperrliste nehmen, globale Listen nicht wieder übernehmen und weder ein einzelnes Kind noch „Unbeschränkt“ wählen. Strenger machen geht immer: eine Prüfung einschalten, ein Alter senken, einen Kanal sperren oder „Automatisch“ wählen.

Geöffnet wird es mit dem PIN am Schloss. Es bleibt 5 Minuten offen, und jede Änderung startet die 5 Minuten neu. Zum Schließen braucht es keinen PIN. Nach 5 falschen PINs wird 15 Minuten lang kein PIN angenommen, und jede weitere Sperre dauert doppelt so lang. Jeder falsche PIN steht im Logbuch und löst das Event `parentcontrol_pin_failed` aus.

Admins und Automationen betrifft das Schloss nicht. Der PIN wird nur als Hash gespeichert; wer ihn vergisst, legt in den Optionen der Integration einen neuen fest.

Zustände kann Home Assistant vor Benutzern nicht verbergen. Jeder Angemeldete kann Status und die letzten Videos lesen.

## Dashboard-Karte

Die Integration bringt eine eigene Karte mit, ein zusätzlicher Download ist nicht nötig. Sie trägt die Karte unter **Einstellungen → Dashboards → Ressourcen** ein und hält dort die Version aktuell, damit Dashboards vor dem Zeichnen auf sie warten. Dashboards im YAML-Modus brauchen die Ressource stattdessen in ihrer Konfiguration:

```yaml
resources:
  - url: /parentcontrol/parentcontrol-card.js
    type: module
```

Du fügst die Karte im Dashboard-Editor unter **ParentControl** hinzu oder per YAML:

```yaml
type: custom:parentcontrol-card
```

Ohne PIN zeigt die Karte die Geräteliste: Status, Alter, Schauzeit, den laufenden Titel, die aktiven Kinder, Symbole für pädagogisch wertvolle Videos und Schimpfwörter und das Dropdown **Wer schaut?**. „Automatisch“ gilt dort sofort, alles andere fragt nach dem PIN. Ein Tipp auf ein Gerät, auf **Verlauf**, **Profile** oder **Allgemein** fragt zuerst nach dem PIN. Danach siehst du:

- **Gerät:** das laufende Video, **Wer schaut?**, **An den Anfang springen** und seine letzten Videos
- **Verlauf:** die letzten Videos aller Geräte. Bei jedem gesperrten Eintrag steht die Art der Sperre in Rot; ein Tipp auf den Eintrag zeigt den vollen Sperrtext mit den gefundenen Schimpfwörtern und die Einstufung des Modells. Die Knöpfe zum Freigeben oder Sperren eines Kanals fragen, ob es für alle Kinder gilt oder nur für die Kinder, die geschaut haben. **Mehr anzeigen** lädt weitere Einträge.
- **Profile:** pro Kind Alter, YouTube heute mit Limit und Restzeit, die Knöpfe „+15 min“ und „+30 min“, Limits, Schauzeiten, ein Diagramm der letzten sieben Tage mit Limit, alle Regeln, die Vererben-Schalter, Kanallisten, erlaubte Wörter und erlaubte Videos
- **Allgemein:** den Schalter „Prüfung“, die Listen für alle Kinder, die Statistik von heute und den Zustand von Ollama und der YouTube-Abfrage

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

## Listen

Es gibt Listen für alle Kinder und Listen pro Kind. Du bearbeitest sie in der Karte oder in den Optionen der Integration, mit einem Eintrag pro Zeile.

**Kanäle:** Freigegebene Kanäle können nach einem Semikolon ein Mindestalter haben. Ohne Zahl gilt 0.

```text
Die Maus; 0
Checker Tobi; 6
```

Namen müssen vollständig passen, ohne Rücksicht auf Groß- und Kleinschreibung, Leerzeichen und Zeichen. Eine Sperre gewinnt immer, und die globale Sperrliste gilt immer. Bei Freigaben geht der Eintrag des Kindes vor dem globalen, und die globale Liste gilt nur, wenn das Kind sie übernimmt. Ist ein Kind jünger als das eingetragene Alter, wird das Video normal geprüft. Ein freigegebener Kanal gilt als Ganzes, auch für Videos, die niemand gesehen hat.

Die globale Freigabeliste startet mit bekannten deutschen Kinderkanälen. Die Alterswerte sind Schätzungen, keine offiziellen Freigaben, und du kannst jede Zeile ändern oder löschen.

**Erlaubte Schimpfwörter:** Ein Wort gilt als ganzes Wort, ohne Rücksicht auf Groß- und Kleinschreibung. `Mist*` erlaubt alle Wörter, die mit „Mist“ beginnen. Die globale Liste startet mit milden Wörtern, die Kinder überall hören: `blöd*`, `idiot*`, `doof*`, `dumm*`, `quatsch*`, `mist*`, `depp*`, `trottel*` und `kacke`. Jede Zeile lässt sich ändern oder löschen. Beim Update werden diese Standardwerte einmalig eingetragen, wenn die Liste noch leer ist. Wörter, die YouTube als `[ __ ]` zensiert hat, lassen sich nie erlauben. Meldet das Modell Schimpfwörter, ohne sie zu nennen, bleibt das Video gesperrt.

Diese Aktionen ändern die Listen ohne die Optionen. Ohne `profile` ändern sie die Listen für alle Kinder:

| Aktion | Wirkung | PIN |
|---|---|---|
| `parentcontrol.allow_channel` | gibt einen Kanal frei, optional mit `age`, und nimmt ihn aus der Sperrliste | ja |
| `parentcontrol.block_channel` | sperrt einen Kanal und nimmt ihn aus der Freigabeliste | nein |
| `parentcontrol.remove_channel` | entfernt einen Kanal aus der Liste in `list` (`allowed` oder `blocked`) | bei `blocked` |
| `parentcontrol.allow_word` | erlaubt ein Schimpfwort | ja |
| `parentcontrol.remove_word` | verbietet ein Schimpfwort wieder | nein |
| `parentcontrol.add_time` | gibt einem Kind heute zusätzliche Minuten | ja |
| `parentcontrol.allow_video` | erlaubt das Video, das auf `player` läuft, und spielt es weiter | ja |
| `parentcontrol.remove_video` | nimmt ein Video von den erlaubten Videos | nein |
| `parentcontrol.get_transcript` | liefert das Transkript eines gesperrten Videos | ja |

Ohne `channel` nehmen die Kanal-Aktionen den laufenden Kanal von `player`, das ergibt einen einfachen Dashboard-Knopf:

```yaml
type: button
name: Kanal sperren
tap_action:
  action: perform-action
  perform_action: parentcontrol.block_channel
  data:
    player: media_player.tv
```

## Automationsvorlagen

Fertige Automationen für Benachrichtigungen an die Home-Assistant-App:

| Vorlage | Import |
|---|---|
| Nachricht bei Sperre: Titel, Gerät, Kinder und Art der Sperre, mit Knöpfen „Video erlauben“, „Kanal freigeben“ für die schauenden Kinder und „Gesperrt lassen“ sowie Links zum Video und zum Dashboard | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fnotify_on_block.yaml) |
| Zeitlimit: vor dem Limit oder dem Ende der Schauzeit und beim Erreichen | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Ftime_limit.yaml) |
| Ansage bei Pause: sagt dem Kind über einen Lautsprecher, warum YouTube stoppt oder wie viel Zeit bleibt, ohne Schimpfwörter. Nimm einen anderen Lautsprecher als den Fernseher, denn eine Ansage über Cast auf dem Fernseher beendet YouTube. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fannounce.yaml) |
| Tagesbericht: YouTube-Zeit, Limit, Bonuszeit und Videos pro Kind sowie die gesperrten Videos, zu einer wählbaren Uhrzeit (standardmäßig 20 Uhr) | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fdaily_report.yaml) |
| Falscher PIN, optional erst ab einem bestimmten Versuch | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fwrong_pin.yaml) |
| Dienst ausgefallen: Ollama oder die YouTube-Abfrage seit einer einstellbaren Zeit aus, und wieder da | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fservice_down.yaml) |

## Unterstützte Geräte

ParentControl erkennt YouTube am App-Namen, an der App-ID oder an der Quelle eines Media Players. Damit ein Video geprüft werden kann, muss der Player außerdem den Titel melden.

| Gerät und Integration | Titel | Stand |
|---|---|---|
| Google TV, Chromecast und Fernseher mit Chromecast über Google Cast | ja, teils bis zu 2 Minuten verzögert | getestet |
| Apple TV über die Apple-TV-Integration | Titel erwartet, Kanal unklar | nicht getestet |
| Fire TV und Android TV über ADB oder Android TV Remote | nein | nur „Keine Daten“ |
| LG webOS über die LG-webOS-Integration | nein, nur bei Live-TV | nur „Keine Daten“ |

Ohne Titel zeigt ParentControl „Keine Daten“. Nur mit strenger Bewertung pausiert es YouTube auf so einem Gerät. Ohne Kanal greifen die Kanallisten nicht.

## So wird geprüft

Die Integration sucht das Video über Titel, Kanal und Dauer, lädt Beschreibung und Untertitel und schickt Auszüge an Ollama. Titel und Kanal gehen dafür an YouTube, die Bewertung selbst bleibt lokal.

## Grenzen

- Das Mindestalter ist die Schätzung eines Sprachmodells, keine offizielle Altersfreigabe. Es kann falsch sein.
- Geprüft wird nur Text, nicht das Bild.
- Der Anfang eines Videos läuft immer ungeprüft, bis Titel und Einschätzung vorliegen. Das gilt auch für Shorts: Jeder Short läuft an, bevor er erkannt ist, und nach dem Wischen startet der nächste. Ganz ausblenden kann Shorts nur YouTube selbst, zum Beispiel mit einem beaufsichtigten Konto.
- Ohne strenge Bewertung läuft ein Video weiter, wenn Ollama ausfällt oder es keine Daten gibt.
- Wer wirklich vor einem gemeinsamen Gerät sitzt, kann ParentControl nicht erkennen. Bei „Automatisch“ gilt die strengste Regel aller zugeordneten Kinder, und die Schauzeit zählt für jedes von ihnen.
- Erfasst werden nur überwachte Media Player. Browser auf Laptops, Handys, Tablets und Spielkonsolen können die Prüfung umgehen. Die Home-Assistant-App auf dem iPhone meldet nicht, was andere Apps abspielen.
- Das Abrufen über `yt-dlp` ist von YouTube nicht vorgesehen und kann jederzeit aufhören zu funktionieren.

Die Integration ersetzt keine Aufsicht.

## Lizenz

MIT
