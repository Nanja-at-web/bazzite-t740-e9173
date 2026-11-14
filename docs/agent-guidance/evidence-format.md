# Beleg- und Protokollformat

Pro Aussage/Messung diese Felder verwenden; nicht erhobene Werte als
„nicht nachgewiesen“ oder „nicht erhoben“ ausweisen:

| Feld | Inhalt |
|---|---|
| Identität | Datum/Zeit mit Zeitzone, Hardware-ID ohne Seriennummer, Dell oder HP |
| Ausgangslage | Commit, Branch, Worktree, OS/Kernel, Image-Digest, Softwareversionen |
| Modus | normaler Gaming Mode / Plasma / nested Gamescope; nicht gleichsetzen |
| Aktion | exakter Befehl/argv oder manuelle Aktion, Freigabeumfang, Host/Sandbox |
| Ergebnis | Exitcode, relevante redigierte Ausgabe, Zeitpunkt und Beobachter |
| Quelle | Repositorypfad und Zeilen/Commit, Paketversion, Journalzeit oder GitHub-Objekt |
| Einordnung | Tatsache / Codefunktion ohne Hardwarevalidierung / Absicht / Hypothese / Widerspruch / veraltet / fehlender Beleg / technisch unbekannt |
| Grenzen | fehlende Rechte/Session, gekürzte Ausgabe, rotierte Logs, nicht getestete Funktionen |

Zusammengesetzte Shell-Aufrufe liefern ohne Instrumentierung nur den Gesamtcode;
keine Einzelcodes erfinden. Leere Logs beweisen nicht, dass kein Ereignis stattfand.
Connector `connected`, gespeichertes Layout und aktuell sichtbares Bild getrennt
belegen. Statusfeld, Profilname und tatsächliche Eingabezustellung getrennt prüfen.
Kein endlicher Test beweist universelles „niemals“: Abnahme auf dokumentierte
Geräte, Aktionen und Übergänge begrenzen; nicht beobachtete Fälle bleiben offen.

Bei erlaubtem Export: Schema/Dateiname, Quelle, Messzeit und Redaktionsumfang
mitgeben; Rohdaten nur im ausdrücklich erlaubten Ziel speichern. Im Nur-Leseauftrag
nur redigierte Ausgabe an die Konversation, keine Exportdateien.

Datenschutz: keine Authdateien, Schlüssel oder vollständigen Umgebungen lesen.
Token-/Passwort-/Privatschlüssel-Funde nur als Pfad, Zeile und Kategorie melden.
Aus Logs IPs, Konten, personenbezogene Argumente und unnötige Gerätekennungen
entfernen. EDID nur mit benötigtem Hersteller/Modell, Modus und Hash zuordnen;
keine rohen EDID-/Seriennummerndumps. Öffentliche Digests/Prüfsummen sind Belege,
keine Zugangsdaten. Keine echten Secrets als Testdaten verwenden.

Abschluss: alle betroffenen Dateien vollständig prüfen, neue/unversionierte Dateien
einschließen, erlaubte Pfade abgleichen, Verweise und Frontmatter statisch prüfen,
`git diff --check`, frischen Status und Stat auswerten. Ausgelassene Tests nennen.
Keine Durchführung oder Hardwarevalidierung aus bloßem Vorhandensein ableiten.
