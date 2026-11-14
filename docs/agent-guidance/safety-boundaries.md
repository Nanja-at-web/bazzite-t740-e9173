# Sicherheitsgrenzen und Freigaben

Gilt ergänzend zu [AGENTS.md](../../AGENTS.md). Ein Skill, Plan oder historischer
Testbefehl ist keine Freigabe. Berechtigte Hostausführung ersetzt keine fachliche
Freigabe. Frühere Freigaben gelten nur für ihren konkret benannten Umfang fort.

| Kategorie | Grenze |
|---|---|
| Lesend | Im laufenden Diagnoseauftrag vorhandene Dateien, Metadaten, Status und begrenzte Logs lesen; keine neuen Exporte/Caches |
| Ausdrücklich freizugeben | Dateiarbeit, Export, Instrumentierung, Dienst-/Prozesssteuerung, Profil-/Display-/Sitzungsänderung, Hardwaretest und Recovery |
| Ausgeschlossen | Geheimnisoffenlegung, fremde Sitzungsübernahme, Erraten von Connectoren/Rollen/Sessionvariablen, Überschreiben uncommitteter Benutzerarbeit, falsche Validierungsbehauptungen, absichtliche gleichzeitige Eingabezustellung |

Nur-Lese bedeutet auch: keine Test-Temporärdateien und kein Python-Bytecode.
`python3 -B` oder gezielt unterdrückte Bytecode-Erzeugung verwenden, keine
Sessionumgebung dafür verändern. Keine Produktmodule ungeprüft importieren.
Keine Input-Gerätenodes öffnen. Bestehende Controllerdaten über sysfs oder
bereits laufende Statusschnittstellen lesen. D-Bus-Autostart vermeiden; bei
fehlendem Dienst nicht als Diagnoseersatz starten.

SSH/Headless: keine DISPLAY-, WAYLAND_DISPLAY-, DBUS_SESSION_BUS_ADDRESS- oder
XDG_RUNTIME_DIR-Werte erraten, injizieren oder aus fremden Prozessen übernehmen.
Fehlende Session-/Sandboxrechte sind Messgrenzen. GUI-Abfragen bei fehlendem
geeignetem Sitzungskontext auslassen. `kscreen-doctor -o` verursachte im Audit
einen SIGABRT mit automatischem Core-Dump; nicht als risikofrei wiederholen.

Fail-safe ist eine Anforderung, keine Bestätigung des heutigen Prototyps:
bei Fehlern Wechsel abbrechen, Zustand belegen, sichere Spiel-Rückkehr bevorzugen.
Nur einen ausdrücklich autorisierten, begrenzten Recoveryablauf verwenden;
keine aggressiven Wiederholungen oder Neustarts. Keine parallele Zustellung.
Ist sichere Rückkehr nicht bestätigt, keine Deinstallation/Beleglöschung;
Benutzer über unklaren Zustand und notwendige manuelle Schritte informieren.
Der aktuelle Deinstaller garantiert diese Grenze nicht; nicht blind ausführen.

Buildfreigaben benennen Stufe, Commit, Ziel und erlaubte Nebenwirkungen:
1 Lesen; 2 Dokumentation; 3 lokaler Codeentwurf; 4 Container-Build;
5 manueller ISO-Build; 6 Push oder PR; 7 Merge; 8 Release.
Die Zahlen sind getrennte Freigabegegenstände, keine implizite Rechtehierarchie.
Ein ISO-Auftrag erlaubt weder Lockänderung noch Containerveröffentlichung.
Ein PR kann CI/Containerbuild auslösen; diese Folge vorher benennen und abdecken.
Workflow-Auslösung ist stets gesondert ausdrücklich zu autorisieren.
