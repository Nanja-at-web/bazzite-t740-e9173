---
name: bazzite-hybrid-diagnostics
description: "Use when investigating Bazzite Gamescope or Steam failures, black secondary monitors, KWin/Plasma/Wayland sessions, DRM connectors, InputPlumber controllers, missing hybrid-focus sockets, or installed prototype drift."
---

# Bazzite-Hybrid-Diagnose

## Zweck und Grenze

Istzustand und belegbare Ursachenhypothesen ermitteln. Gilt für normalen Gaming
Mode, Plasma und nested Gamescope, jeweils getrennt. Keine Reparatur, kein
Hardwaretest und keine Build-/Releasefreigabe. Endziel bleibt normaler Gaming
Mode plus paralleles Plasma; Machbarkeit **nicht nachgewiesen**.

## Voraussetzungen und Aktionen

Aktiven Auftrag, Hardware, Pfad/Branch/HEAD, vorhandene Benutzeränderungen und
Messkontext erfassen. [AGENTS.md](../../../AGENTS.md) beachten.

| Kategorie | Aktionen |
|---|---|
| Ohne zusätzliche Freigabe im Diagnoseauftrag lesend | Bestehende Dokumentation, Pakete, sysfs/EDID, Prozessnamen, Dienststatus, begrenzte Journale und installierte Dateien vergleichen; siehe [Befehle](references/commands.md) |
| Nur ausdrücklich freigegeben | Exporte, neue Messdateien, Privilegienerweiterung, Dienst-/Prozess-/Profil-/Display-/Sitzungsänderung, aktive Reproduktion, Steam-/Gamescope-Starts und Recovery |
| Grundsätzlich ausgeschlossen | Geheimnisoffenlegung, fremde Wayland-Sitzungsübernahme, geratene Sessionvariablen/Monitorrollen, ungefragte Input-Geräteöffnung oder Grabs, falsche Validierung |

Ein erlaubter Statusaufruf darf keinen fehlenden Dienst starten. Wirkung unklar:
nicht ausführen. SSH ohne geeigneten GUI-Kontext: keine GUI-Abfrage und keine
DISPLAY-/WAYLAND_DISPLAY-/DBUS_SESSION_BUS_ADDRESS-/XDG_RUNTIME_DIR-Manipulation.

## Ablauf

1. Auftrag abgrenzen, Repositorystatus lesen; [Hardwarebaselines](../../../docs/agent-guidance/hardware-baselines.md)
   und vorhandene Belege zuordnen. Frühere Messwerte nicht als aktuelle übernehmen.
2. Dokumentation, Daemon, CLI, Unit, Profil, UI, Installer/Deinstaller und relevante
   Tests statisch lesen. Befehle erst nach Wirkungsprüfung ausführen.
3. OS/Kernel/Image, GPU/Treiber/DRM-Geräte und Softwareversionen erheben.
4. Sitzung und relevante Prozesse erfassen. Normalen Gaming Mode und nested
   Betrieb unterscheiden; Prozessnamen allein belegen keine Compositor-Ownership.
5. Connectorstatus, enabled/DPMS, Modi und redigierte EDID zuordnen. Physische
   Verkabelung erfragen, wenn sie fehlt. Gespeicherte KWin-Layouts getrennt ausweisen.
6. Bereits laufendes InputPlumber lesend prüfen, Controller über sysfs identifizieren;
   keine Gerätedateien öffnen. Fehlende CompositeDevices nicht durch Start beheben.
7. Hybrid-Dienst, Runtimeverzeichnis, Socket und begrenzte Logs prüfen. Installierte
   Dateien ohne Produktimport mit Repositorybytes vergleichen, gerenderte Vorlagen
   berücksichtigen. Nur geprüften `status`-Request mit unterdrücktem Bytecode nutzen.
8. Fakten/Codefunktion/Absicht/Hypothese trennen; Displayproblem und Routingproblem
   getrennt bewerten. Für jede Hypothese fehlende Messwerte und Falsifikation nennen.

## Belege, Datenschutz und Abbruch

[Belegformat](../../../docs/agent-guidance/evidence-format.md): Zeit/Zeitzone,
Hardware, Commit/Image/Version, Modus, exakter Befehl, Host/Sandbox, Exitcode,
redigierte Ausgabe, Quelle und Messgrenze. Keine Secrets/Umgebungsdumps,
EDID-Seriennummern oder unnötigen persönlichen Daten. Nur stdout; Export extra
autorisieren. Regeln: [Sicherheitsgrenzen](../../../docs/agent-guidance/safety-boundaries.md).

Bei Rechte-/Sessionfehler Messgrenze dokumentieren; keine Sitzung übernehmen.
Bei GUI-Absturz, unbekannter Nebenwirkung oder erforderlichem Zustandswechsel
betroffenen Pfad abbrechen. Nichts automatisch bereinigen oder neu starten.
Fehler nicht durch wiederholte Profilwechsel behandeln.

## Abschluss und häufige Fehler

Quellen gegen aktuelle Messungen prüfen; leere/rotierte Logs und gekürzte Ausgaben
nennen. Kein „funktioniert“ aus Status/Profilname oder gespeichertem Layout
ableiten. Kleinsten nächsten Diagnoseschritt und dessen Freigabeumfang nennen.
Frischen Git-Status/Diff prüfen, Nebenwirkungen offenlegen. Keine Reparatur- oder
Hardwareabnahmebehauptung; nicht erhobene Eigenschaften: „nicht nachgewiesen“.
