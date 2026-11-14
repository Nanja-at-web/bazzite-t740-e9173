---
name: bazzite-build-release-safety
description: "Use when reviewing or preparing Bazzite container images, installer ISOs, image-lock.json changes, digests, SHA-256 checksums, build numbers, provenance, GitHub Actions, pushes, pull requests, merges, releases, or deployment rollback."
---

# Bazzite-Build- und Release-Sicherheit

## Zweck und Geltungsbereich

Referenz und Artefaktidentität schützen; Container, ISO und Veröffentlichung
getrennt behandeln. Gilt für Quellen, Locks, Workflows, Signaturen, Provenance und
Rollback. Kein Build-Erfolg ersetzt Hardwarevalidierung; keine automatische
Veröffentlichung oder Wiederherstellung unbekannter Build-#4-Eingaben.

## Voraussetzungen und Freigabestufen

[AGENTS.md](../../../AGENTS.md) und [Hardwarebaselines](../../../docs/agent-guidance/hardware-baselines.md)
lesen. Auftrag, Pfade, Branch/HEAD/Worktree, geschützte Dateien, Zielhardware und
konkrete Stufe erfassen. Benutzeränderungen erhalten; `main` geschützt.

| Stufe | Gegenstand und erforderliche Grenze |
|---:|---|
| 1 | Lokale lesende Prüfung: Quellen, vorhandene Metadaten/Logs, Trigger und Hashes; keine Dateien erzeugen |
| 2 | Lokale Dokumentation: nur ausdrücklich erlaubte Dateien, kein Produktcode |
| 3 | Lokaler Codeänderungsentwurf: nur freigegebene Pfade; kein Build oder Git-Remotezugriff mit Schreibwirkung |
| 4 | Container-Build: konkreter Commit, Eingaben, Ausführungsort und Nebenwirkungen; kein Push/ISO |
| 5 | Manueller ISO-Build: eigener Auftrag, exakter Payload-Digest; kein impliziter Containerbuild oder Lockrefresh |
| 6 | Push oder Pull Request: Aktion, Branch, Ziel und dadurch ausgelöste CI ausdrücklich benennen |
| 7 | Merge: konkreter PR/Commit und Ziel, einschließlich ausgelöster CI/Publikation ausdrücklich freigeben |
| 8 | Release: konkrete Artefakte, Prüfsummen, Signaturen und Veröffentlichung ausdrücklich freigeben |

**Keine höhere Stufe aus einer niedrigeren ableiten.** Auch umgekehrt erlaubt
eine Stufe keine unbenannten Begleitaktionen. Commit, Workflow-Auslösung,
Signierung, Lockänderung und Deployment-Rollback brauchen jeweils passende
ausdrückliche Freigabe. ISO ausschließlich manuell starten.

## Erlaubt, freigabepflichtig, verboten

Lesend: Diffs, vorhandene Provenance, öffentliche Digest-/SHA-256-Werte,
Workflowtrigger und Signaturergebnisse prüfen. Registry-/GitHub-Leseabfragen nur
im passenden Auftrag; kein Authlogin oder Credentialexport.

Schreibarbeit, Build, Push/PR, Merge, Workflow, Release und Systemrollback nur
gemäß konkreter Freigabe. Grundsätzlich ausgeschlossen: Secrets ausgeben,
historische Belege verfälschen, uncommittete Arbeit überschreiben, Versionstags
still verschieben oder Dell-Ergebnisse als HP-Validierung ausgeben.

## Ablauf

1. Stufe und erlaubte Nebenwirkungen festhalten; unklare Freigabe blockiert die
   betreffende Aktion, bereits autorisierte unabhängige Prüfung fortsetzen.
2. HP Build #4 aus README als historische Referenz sichern, ohne Dateien zu
   ändern; Dell- und HP-Belege getrennt auswerten. Damaliger exakter Containerdigest
   ist nicht nachgewiesen, kein heutiger Lock ersetzt ihn.
3. Quellcommit, Buildnummer, Base-/Payload-Digests und Versionskonsistenz prüfen.
   Container-Image und installierter ISO-Payload sind verschiedene Artefakte.
4. Trigger, Publishbedingungen und manuelle ISO-Auslösung statisch lesen.
   PR/Main-Push kann CI/Containerbuild auslösen; Freigabe muss diese Folge abdecken.
5. Nur autorisierte Stufe ausführen. Neue Artefakte mit unveränderlichen IDs,
   SHA-256 und separatem Signaturnachweis erfassen. Kein Workflowstatus allein
   beweist erfolgreiche Signierung; tolerierte Teilschrittfehler prüfen.
6. Rollbackartefakt/Deployment benennen und erhalten. Rollback nicht als
   Freigabeersatz ausführen. Vor jeder weiteren Stufe deren Freigabe prüfen.

## Belege, Abbruch und Abschluss

[Belegformat](../../../docs/agent-guidance/evidence-format.md): Stufe/Freigabe,
Commit, Version/Buildnummer, Eingabe-/Ausgabedigests, Workflow-ID, ISO-SHA-256,
Signatur und Hardwarebeleg separat. [Sicherheitsgrenzen](../../../docs/agent-guidance/safety-boundaries.md)
beachten; keine privaten Schlüssel, Registrytokens oder vollständigen Umgebungen.

Bei Dirty-Worktree-Konflikt, unbekannter Payloadidentität, Versionskonflikt,
Signaturfehler, unerwarteter Schutzdateiänderung oder fehlender Freigabe stoppen.
Nicht durch Lockrefresh, Neubuild oder Überschreiben „korrigieren“.

Vor Abschluss erlaubte Pfade und vollständigen Diff inklusive neuer Dateien,
frischen Status und einschlägige statische Prüfungen auswerten. Ausgelassene
Builds/Hardwaretests nennen. Jede Stufe separat als geprüft/offen dokumentieren;
keinen Release oder Hardwareerfolg aus Dokumentation ableiten.
