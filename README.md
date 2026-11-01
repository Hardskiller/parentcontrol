# ParentControl

Home-Assistant-Integration, die laufende YouTube-Videos mit einem lokalen Ollama-Modell auf ein Mindestalter einschätzt und ungeeignete Videos automatisch pausiert.

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

- **Standardalter:** gilt für alle Geräte.
- **Eigenes Alter pro Gerät:** optional in den Optionen der Integration. Leer bedeutet Standardalter.
- **Prüfung:** Schalter, der die Prüfung für alle Geräte abschaltet.
- **YouTube-Prüfung (Sensor pro Gerät):** zeigt Status, Titel, Mindestalter und Begründung.

Liegt das Mindestalter über dem Alter, wird das Video pausiert, bei jedem erneuten Play wieder. Dabei wird das Event `parentcontrol_paused` ausgelöst.

## So wird geprüft

Die Integration sucht das Video über Titel, Kanal und Dauer, lädt Beschreibung und Untertitel und schickt Auszüge an Ollama. Titel und Kanal gehen dafür an YouTube, die Bewertung selbst bleibt lokal.

## Grenzen

- Das Mindestalter ist die Schätzung eines Sprachmodells, keine offizielle Altersfreigabe. Es kann falsch sein.
- Geprüft wird nur Text, nicht das Bild.
- Der Anfang eines Videos läuft immer ungeprüft, bis Titel und Einschätzung vorliegen.
- Fällt Ollama aus oder gibt es keine Daten, läuft das Video weiter.
- Das Abrufen über `yt-dlp` ist von YouTube nicht vorgesehen und kann jederzeit aufhören zu funktionieren.

Die Integration ersetzt keine Aufsicht.

## Lizenz

MIT
