# Dell-Testprotokoll

Nur Definition eines späteren ausdrücklich freigegebenen Tests. Keine hier
beschriebene Aktion ist allein durch Lesen autorisiert. Historische Grundlage:
[Dell-Checkliste](../../../../docs/hybrid-focus-dell-test.md); deren Nested-Pfad
ist kein Nachweis der Endarchitektur. Sicherheitslücken des aktuellen Deinstallers
zuerst berücksichtigen, nicht dessen automatische Fehlerunterdrückung übernehmen.

## Eingabegate

Jedes Feld vor Testbeginn ausfüllen; „unbekannt“ blockiert den Start:

| Pflichtfeld | Aufzeichnung |
|---|---|
| Lauf | Zeit/Zeitzone, Beobachter, Auftrag/Freigabe, Test-ID |
| Rechner | Hersteller, Modell, Dell separat von HP |
| Grafik | GPU/PCI-ID, Treiber und Version |
| Software | OS/Kernel, Image-Digest, Repo-Commit/Worktree, Gamescope, Steam, Plasma/KWin, InputPlumber, Prototyp; Decky-Version oder begründet nicht verwendet |
| Monitor 1 | Hersteller/Modell, physischer Rechnerport, Kabel/Adapter, DRM-Connector, aktuelle Auflösung/Rate, Gaming-Rolle |
| Monitor 2 | Hersteller/Modell, physischer Rechnerport, Kabel/Adapter, DRM-Connector, aktuelle Auflösung/Rate, Desktop-Rolle |
| Controller | Hersteller/Modell, Familie, Verbindung, sichere Gerätezuordnung, Originalprofilpfad und Inhaltshash |
| Sitzung | aktueller Modus, geplanter Modus, belegte lokale Sessionzuordnung |
| Recovery | physische Tastatur/Maus, erreichbarer Rückweg, begrenzte autorisierte Schritte, Abbruchzuständigkeit |

Monitorzuordnung durch physische Bestätigung und aktuelle DRM-/EDID-Belege
korrelieren. Keine Rollen aus früheren DP-/HDMI-Namen übernehmen. Profile nur mit
gesonderter Freigabe sichern; im Nur-Leseteil Pfad/Hash und Wiederherstellbarkeit
prüfen. Fehlt ein sicherer Wiederherstellungspfad: `BLOCKED`.

## Getrennte Testmodi

1. **Normaler Gaming Mode:** vorherige Bildausgabe, Hardware-Rendering und
   Controllerfunktion prüfen. Paralleles Plasma auf Monitor 2 ist ein eigenes,
   bisher nicht nachgewiesenes Gate. Fehlende Implementierung blockiert dieses
   Gate; sie wird während des Tests nicht ergänzt.
2. **Nested Gamescope:** nur bei eigener Freigabe und belegtem Plasma-Zweimonitor-
   Zustand starten. Ergebnisse eindeutig als nested markieren. „Primary child
   shut down“ allein ist keine Ursache; Kommando, gesamte relevante Ausgabe,
   Exitcodes und beteiligte Prozesse erfassen, dann stoppen.

Gaming-Moduswechsel, Steam-Schließen/-Start und Fensterplatzierung jeweils als
Zustandswirkung vorab benennen. Keine konkurrierenden Compositoren versuchsweise
für DRM-Master starten. Hardware-Rendering mit geeignetem erlaubtem Beleg messen;
offener DRM-Node allein reicht nicht.

## Ein vollständiger Fokuszyklus

Beide Empfänger müssen beobachtbar sein, mit harmlosen dokumentierten Testaktionen
ohne Datenverlust. Beobachtungsaufbau und Messauflösung notieren; ungeeignete
Beobachtbarkeit blockiert eine Exklusivitätsbehauptung.

1. In `game` tatsächliches Profil, Eingabe im Spiel und keine Desktopemulation
   bestätigen. Sichtbaren Zielzustand erfassen.
2. Explizite autorisierte Desktopaktion auslösen. Zeitpunkt und Rückmeldung
   erfassen; ein Profil-/Statuswechsel allein ist kein Zustellungsnachweis.
3. D-Pad, South/East, Bumper, Trigger und rechten Stick einzeln prüfen. Desktop
   muss reagieren, Spiel darf weder Gamepad- noch emulierte Tastatur-/Mausaktionen
   erhalten. Unbenutzte Tasten und gehaltene Eingaben beim Übergang einbeziehen.
4. Zielanzeige und echte Button-Glyphen prüfen. Reinen Familiennamen als fehlende
   Glyphenfunktion bewerten. Unbekanntes Gerät darf keine erratenen Familienglyphen
   erhalten; neutralen Fallback prüfen.
5. Rückkehr mit Controller über das tatsächlich erreichbare Desktopcontrol
   auslösen. Exaktes Originalprofil und Spielreaktion bestätigen; Desktop darf
   keine weiteren emulierten Aktionen erhalten. Keine hängenden Eingaben.
6. Zeigerbewegung, Bildschirmrand und Fadenkreuz/Kamerabewegung prüfen: ohne
   explizite Aktion darf kein Fokuswechsel entstehen. Ergebnis protokollieren.

Bei erster Leakage/Unklarheit keine weiteren Testeingaben senden. Zyklen nicht
durch Dienstneustart oder Reconnect „reparieren“; ein Neustart beginnt einen neuen
Lauf und setzt eine eigene Freigabe voraus.

| Zyklus | Spiel→Desktop | Keine Eingabe im Spiel | Desktop nutzbar | Desktop→Spiel | Keine Desktop-Leakage | Profile/Glyphen/Anzeige | Beleg/Ergebnis |
|---:|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |
| 6 | | | | | | | |
| 7 | | | | | | | |
| 8 | | | | | | | |
| 9 | | | | | | | |
| 10 | | | | | | | |

## Fehlerfälle, Export und Rollback

Fehlender Socket, Dienst-/InputPlumber-Ausfall, Controllerverlust, Displayverlust,
degraded-Zustand und Fehler beim Profilrestore sind Abbruchfälle. Künstliche
Fehlerinduktion ist eine zusätzliche Freigabe, kein Pflichtbefehl zum sofortigen
Ausführen. Nicht getestete Fehlerfälle bleiben offen.

Nur bei Exportfreigabe Diagnose im Spielzustand, Desktopzustand und nach Rückkehr
erstellen; Ziele, Datenumfang und Redaktionsregeln vorher bestimmen. Relevante
Journalzeitfenster und Gamescope-Ausgabe beibehalten. Keine Auth-/EDID-Rohdaten.

Recovery: Testeingaben beenden, Zustand/Fehler erfassen, Benutzer informieren,
einmalig den vorab genehmigten sicheren Rückweg zum Spiel nutzen und tatsächliche
Originalprofile sowie Routing verifizieren. Ist das nicht bestätigt, stoppen und
manuelle Schritte abstimmen; keine automatischen Restart-/Uninstall-Schleifen.
Deinstallation, Pluginentfernung und Neustart nur separat autorisiert und erst
nach bestätigter Sicherheit. Danach Baseline vergleichen; scheitert sie, `FAIL`.

## Urteil

Pro Modus und Controllerfamilie `PASS`, `FAIL`, `BLOCKED` oder `NICHT GEPRÜFT`
vergeben. Zehn vollständige Zyklen, keine beobachtete Leakage einschließlich
Übergängen, nutzbarer Desktop, sichere Rückkehr, exakte Profile, sichtbarer Fokus,
passende echte Glyphen und erfolgreicher Rollback sind Gates. Familienanzeige
allein besteht die Glyphenabnahme nicht. Fehlende Familien separat offenhalten.
Erfolgreicher Fokus-Untertest ersetzt keine Display- oder Endarchitekturabnahme.
Auch ein PASS gilt nur für dokumentierte Hardware, Versionen und Aktionen.
