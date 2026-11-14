# Repository-Regeln

## Auftrag, Ziel und Hardwarebelege

- Vor Arbeit Pfad, Branch, HEAD und Worktree lesen. Uncommittete und unversionierte
  Benutzerdateien erhalten; nichts überschreiben oder bereinigen.
- `main` nicht direkt bearbeiten und nicht direkt pushen. Branchwechsel, Staging,
  Commit, Push, Pull Request, Merge, Workflow-Auslösung und Release benötigen
  jeweils eine passende ausdrückliche Freigabe. Ein freigegebener Pull Request
  oder Merge darf `main` nur im konkret benannten Umfang verändern. Eine Freigabe
  für eine Git-Aktion umfasst keine andere Git-Aktion automatisch.
- Endziel: normaler Bazzite Gaming Mode mit Steam/Gamescope auf Monitor 1 und
  gleichzeitig eigenständiges Plasma auf Monitor 2. Machbarkeit: **nicht
  nachgewiesen**. Nested Gamescope dient Diagnose, Entwicklung oder als möglicher
  Fallback; ein Nested-Erfolg validiert die Endarchitektur nicht.
- HP t740 / Ryzen Embedded V1756B / Radeon E9173 / direkter E9173-DisplayPort /
  ISO Build #4 bleibt die historisch validierte Referenz. Dell-Ergebnisse separat
  erfassen; weder neue Images noch Dell-Tests erben diese Validierung.
- Identitäten und Messgrenzen stehen in
  [Hardwarebaselines](docs/agent-guidance/hardware-baselines.md), der ursprüngliche
  Bericht in [Audit 2026-11-14](docs/audits/2026-11-14-dell-hybrid-readonly-audit.md).

## Diagnose, Tests und sichere Rückkehr

- Nur-Lese-Diagnose erlaubt keine Exporte, Cachedateien oder temporären Testdateien.
  Python bei statischen Prüfungen mit `python3 -B` ausführen. Befehlswirkung vorab
  prüfen; unbekannte Wirkung bedeutet stoppen und Freigabeumfang benennen.
- Dienste, Prozesse, Displays, Controllerprofile, InputPlumber, Sitzungswechsel,
  Steam-/Gamescope-Starts und Hardwaretests benötigen konkrete Freigabe. Ein
  Dokumentationsauftrag erteilt sie nicht. Keine Eingabegeräte ungefragt öffnen,
  grabben oder exklusiv binden; keine fremde Sitzung übernehmen und keine
  Sessionvariablen erraten oder manipulieren.
- Bei Fehler/unklarem Routing Eingaben niemals gleichzeitig an Spiel und Desktop
  weitergeben. Sichere Rückkehr zum Spiel bevorzugen, aber nur im autorisierten
  Recoveryumfang. Ohne bestätigten sicheren Ausgangszustand keine Deinstallation
  fortsetzen. Fehler und notwendige manuelle Schritte mitteilen; keine aggressiven
  automatischen Neustart-, Profilwechsel- oder Wiederholschleifen.
- Echte Xbox-, PlayStation-, Nintendo-Button-Glyphen und neutraler Fallback sind
  das Ziel. Controllerfamilientext erfüllt diese Anforderung nicht.

## Build, Release und Belege

- Container-Build und ISO-Build sind getrennte Vorgänge mit getrennter Freigabe.
  ISO ausschließlich manuell und ausdrücklich autorisiert auslösen. Keine höhere
  Freigabestufe aus einer niedrigeren ableiten; keine automatische Veröffentlichung.
- Polaris-/Gamescope-Referenz, Buildkonfiguration, Workflows, `image-lock.json`,
  Digests, Checksummen und Provenance nur bei ausdrücklich passendem Änderungsauftrag
  bearbeiten. Historische Daten nicht durch aktuelle Werte ersetzen.
- Quellcommit, Image-Digest, Buildnummer, SHA-256, Signaturergebnis und Hardwaretest
  getrennt belegen. Build-Erfolg beweist weder Signatur noch Hardwarefunktion.
- Fakten, Codefunktion, Absicht, Hypothese und „nicht nachgewiesen“ trennen.
  [Belegformat](docs/agent-guidance/evidence-format.md) verwenden. Vor Abschluss
  frische statische Prüfungen, vollständige Änderungsprüfung einschließlich neuer
  Dateien und Git-Status auswerten. Nur tatsächlich geprüfte Erfolge melden.
- Keine Tokens, Passwörter, privaten Schlüssel, Gerätecodes oder vollständigen
  Prozessumgebungen ausgeben. Journale, EDID und Anwendungsdaten vor Weitergabe
  redigieren. Auch bei Geheimnissuchen nur Pfad/Zeile/Kategorie, niemals Werte melden.

## Methodik und Routing

- Verfügbare Superpowers für passende Diagnose, Skill-Erstellung und Verifikation
  verwenden. Der konkrete Benutzerauftrag begrenzt jede Methodik; keine Builds,
  Schreibtests, Agenten-Verhaltenstests oder Git-Aktionen daraus ableiten.
- Context7 nur für eine konkret benannte, verbleibende API-/Versions- oder
  Dokumentationsfrage nach Prüfung von Repository/lokaler Doku/Primärquellen;
  Software, Version und Quelle nennen. Keine Wahrheit über lokale Laufzeit ableiten.
- REA ausschließlich nach expliziter Freigabe eines benannten Binärartefakts und
  einer abgegrenzten Frage, die Quellen, Dokumentation und Logs nicht beantworten.
  Fehlende Werkzeuge nicht ungefragt installieren.
- Diagnose: [bazzite-hybrid-diagnostics](.agents/skills/bazzite-hybrid-diagnostics/SKILL.md).
- Autorisierter Hardwaretest:
  [hybrid-focus-hardware-validation](.agents/skills/hybrid-focus-hardware-validation/SKILL.md).
- Build-/Releasevorbereitung:
  [bazzite-build-release-safety](.agents/skills/bazzite-build-release-safety/SKILL.md).
- Gemeinsame [Sicherheitsgrenzen](docs/agent-guidance/safety-boundaries.md) ergänzen
  diese Regeln, erteilen aber selbst keine Ausführungsfreigabe.
