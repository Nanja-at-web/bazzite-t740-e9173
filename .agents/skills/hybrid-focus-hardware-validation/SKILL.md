---
name: hybrid-focus-hardware-validation
description: "Use when an explicitly authorized Dell OptiPlex 5080 two-monitor hardware acceptance test, ten-cycle controller focus test, input-leakage check, controller button-glyph validation, or prototype rollback validation is requested."
---

# Hybrid-Focus-Hardwarevalidierung

## Zweck, Geltungsbereich und Nicht-Ziele

Kontrollierte Abnahme auf Dell OptiPlex 5080 Micro (Modell vor Test bestätigen)
für Controller-Routing und Displaybetrieb, getrennt
nach normalem Gaming Mode und nested Gamescope. Nested dient nur Diagnose,
Entwicklung oder möglichem Fallback; es validiert nicht das unbewiesene Endziel
„normaler Gaming Mode plus eigenständiges Plasma“. Keine HP-Revalidierung,
Implementierung oder Build-/Releasefreigabe.

## Zwingende Voraussetzungen

**Nicht starten**, solange Freigabe oder eines dieser Pflichtfelder fehlt:

- Hardware/Modell, GPU, Treiber, OS/Kernel und Image-Digest/Quellcommit;
- Hersteller/Modell beider Monitore, physischer Anschluss jedes Monitors mit
  Kabel/Adapter, belegter DRM-Connector, primärer Gaming- und sekundärer Desktop-Monitor;
- Controllerhersteller/-modell, Familie, Verbindungsart und Originalprofil;
- aktueller und geplanter Sitzungsmodus sowie getestete Softwareversionen
  (Gamescope, Steam, Plasma/KWin, InputPlumber, Prototyp, gegebenenfalls Decky).

Physische Tastatur/Maus, gesicherte Arbeit, zwei belegbar aktive Displays und ein
autorisierter sicherer Rückweg sind erforderlich. [Testprotokoll](references/protocol.md)
enthält Felder, zehn Zykluszeilen, Abbruch- und Abnahmekriterien.

## Aktionen und Ablauf

| Kategorie | Grenze |
|---|---|
| Lesend erlaubt | Inventar, Versionen, bestehende Profile, Dienst-/Socketstatus, Logs und Hashvergleich im gegebenen Auftrag |
| Ausdrückliche Freigabe | Installation, Export, Dienst-/Steam-/Gamescope-Steuerung, Fokus-/Profilwechsel, Sitzungs-/Displayänderung, Fehlerinduktion, Rollback und Neustart |
| Verboten | Testbeginn mit fehlenden Pflichtdaten, geratene Rollen, unautorisierte Reparatur/HP-Tests, parallele Eingabezustellung, automatische Eskalation zur Endarchitektur oder Veröffentlichung |

1. [AGENTS.md](../../../AGENTS.md), [Baselines](../../../docs/agent-guidance/hardware-baselines.md)
   und aktuelle Prototypgrenzen lesen. Freigabe für jede geplante Zustandswirkung
   dokumentieren; bestehende Skripte sind keine Freigabe.
2. Pflichtdaten und Vorzustand vollständig erfassen. Unvollständig: `BLOCKED`.
3. Normalen Gaming Mode nur im genehmigten Ablauf als eigene Baseline prüfen.
   Paralleles Plasma dort nur bei tatsächlich vorhandener Implementierung und
   genehmigter Messung testen; andernfalls „nicht nachgewiesen“, nicht nachbauen.
4. Nested separat genehmigen und kennzeichnen; Startfehler vollständig erfassen,
   nicht durch Änderung des normalen Gaming Mode umgehen.
5. Im gewählten, funktionsfähigen Modus zehn vollständige Zyklen
   Spiel → Desktop → Spiel mit dem Protokoll durchführen. Beide Eingabeempfänger
   und tatsächliche Profile beobachten, nicht nur den CLI-Zielstatus.
6. Echte Xbox-, PlayStation-, Nintendo-Button-Glyphen und neutralen Fallback je
   tatsächlich vorhandenem Gerät prüfen; Familiennamensanzeige erfüllt das Ziel nicht.
7. Nur genehmigte Diagnoseexporte und Fehlerfälle durchführen. Exakte
   Originalprofile vor/nach begrenztem Rollback belegen; erst dann Abbau erwägen.

## Fehler, Datenschutz und Abschluss

Bei Leakage, verlorener Rückkehr, degraded/unklarem Zustand oder Ausgabeverlust
sofort Testeingaben beenden. Sichere Spiel-Rückkehr im genehmigten Umfang
bevorzugen, keine aggressiven Wiederholungen. Ohne bestätigten Ausgangszustand
keine Deinstallation fortsetzen; Benutzer informieren und manuelle Schritte nennen.

[Belegformat](../../../docs/agent-guidance/evidence-format.md) verwenden; keine
Secrets, Roh-EDID, Seriennummern oder persönlichen Spiel-/Desktopinhalte exportieren.
[Sicherheitsgrenzen](../../../docs/agent-guidance/safety-boundaries.md) gelten.

Abnahme nur mit zehn vollständig belegten Zyklen ohne beobachtete Gamepad-,
Tastatur- oder Maus-Leakage, erreichbarer Rückkehr, echten passenden Glyphen und
bestätigtem Rollback. Fehlende Familien oder Fehlerfälle als offen ausweisen.
Endliche Messung beweist kein universelles „niemals“; Ergebnis auf Testmatrix
begrenzen. Modus/Hardware im Urteil nennen, keine HP- oder Endarchitekturvalidierung
aus einem Nested-Erfolg ableiten. Frischen Git-/Schutzdateiabgleich vorlegen.
