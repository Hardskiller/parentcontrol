# ParentControl

[English version](README.md)

Home-Assistant-Integration, die laufende YouTube-Videos mit einem lokalen Ollama-Modell auf ein Mindestalter einschätzt und ungeeignete Videos automatisch pausiert.

## Funktionen

- Überwacht beliebig viele Media Player
- Mindestalter von 0 bis 18, mit Standardalter und optional eigenem Alter pro Gerät
- Optional pro Gerät: an den Anfang springen, nur pädagogisch wertvolle Videos, Schimpfwörter blockieren, strenge Bewertung
- Editierbare Prompts für Alterseinstufung und pädagogische Bewertung
- Schauzeit pro Gerät und tägliche Videostatistik
- Läuft auf jeder Home-Assistant-Installation, die HACS unterstützt

## Voraussetzungen

- Home Assistant mit [HACS](https://www.hacs.xyz)
- Ein erreichbarer [Ollama](https://ollama.com)-Server mit mindestens einem Modell
- Media Player, die App, Titel und Status melden. Getestet ist bisher nur Google Cast.

## Installation

1. In HACS unter **⋮ → Benutzerdefinierte Repositories** `https://github.com/Hardskiller/parentcontrol` als Typ **Integration** hinzufügen.
2. **ParentControl** herunterladen und Home Assistant neu starten. `yt-dlp` installiert Home Assistant dabei automatisch.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** **ParentControl** wählen.
4. Ollama-Adresse, Modell, Media Player und Standardalter eintragen.

## Bedienung

Für alle Geräte gelten:

- **Standardalter:** gilt, solange ein Gerät kein eigenes Alter hat.
- **Prüfung:** Schalter, der die Prüfung für alle Geräte abschaltet.
- **Videos, Genehmigt, Pädagogisch wertvoll und Geskippt heute:** zählen jedes Video einmal pro Tag. Das Attribut `gesamt` enthält den Wert seit der Installation.
- **Optionen der Integration:** Modell, Geräteauswahl, eigenes Alter pro Gerät und die editierbaren Prompts. Nach einer Prompt-Änderung werden Videos neu geprüft.

Jedes überwachte Gerät erscheint als eigenes Gerät unter ParentControl. Dort liegen:

- **An den Anfang springen:** springt nach dem Pausieren auf den Videoanfang. Standard ist nur Pausieren.
- **Nur pädagogisch wertvoll:** blockiert auch altersgerechte Videos ohne Lernwert. Ohne Schalter wird die Bewertung nur angezeigt.
- **Schimpfwörter blockieren:** blockiert auch altersgerechte Videos, zum Beispiel Musikvideos. Erkannt wird das über eine Wortliste im gesamten Transkript und über das Modell. Ohne Untertitel beurteilt das Modell nur Titel und Beschreibung, und Liedtexte können dann unerkannt bleiben.
- **Strenge Bewertung:** blockiert Videos ohne Untertitel und Videos, deren Prüfung fehlgeschlagen ist, etwa wenn Ollama nicht erreichbar ist. Das trifft auch viele harmlose Videos, vor allem Musik.
- **YouTube-Prüfung:** zeigt Status, Titel, Mindestalter, Bewertungen und Begründungen.
- **Schauzeit heute:** zählt die Minuten, in denen das Gerät abspielt, mit jeder App.

Wer das Dashboard erreicht, kann diese Schalter umstellen.

Fällt ein Video durch die Prüfung, wird es pausiert. Die Integration prüft das alle 3 Sekunden, solange das Video weiterläuft, und löst das Event `parentcontrol_paused` aus.

## So wird geprüft

Die Integration sucht das Video über Titel, Kanal und Dauer, lädt Beschreibung und Untertitel und schickt Auszüge an Ollama. Titel und Kanal gehen dafür an YouTube, die Bewertung selbst bleibt lokal.

## Grenzen

- Das Mindestalter ist die Schätzung eines Sprachmodells, keine offizielle Altersfreigabe. Es kann falsch sein.
- Geprüft wird nur Text, nicht das Bild.
- Der Anfang eines Videos läuft immer ungeprüft, bis Titel und Einschätzung vorliegen.
- Ohne strenge Bewertung läuft ein Video weiter, wenn Ollama ausfällt oder es keine Daten gibt.
- Erfasst werden nur überwachte Media Player. Browser auf Laptops, Handys, Tablets und Spielkonsolen können die Prüfung umgehen.
- Das Abrufen über `yt-dlp` ist von YouTube nicht vorgesehen und kann jederzeit aufhören zu funktionieren.

Die Integration ersetzt keine Aufsicht.

## Lizenz

MIT
