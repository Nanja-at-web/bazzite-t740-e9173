# Hybrid-Display-MVP Implementation Plan

> Für die spätere, ausdrücklich freigegebene Ausführung: passende Methodik aus
> `superpowers:executing-plans` beziehungsweise bei gewählter Agentenausführung
> `superpowers:subagent-driven-development` verwenden. Checkboxen sind geplante
> Schritte, keine erledigten Arbeiten oder Ausführungsfreigaben.

**Ziel:** Ein manuelles, reversibles nested-Display-MVP unter bestehendem Plasma
vorbereiten, zuerst mit Grafikclient, danach Steam und erst danach einem Spiel.

**Architektur:** KWin verwaltet beide physischen Monitore. Ein repositorylokaler
Vordergrundlauncher startet eine explizit verschachtelte Gamescope-Instanz mit
genau einem gewählten Client. Fensterplatzierung erfolgt manuell durch KWin.

**Technik:** Python-3-Standardbibliothek, vorhandenes Gamescope/Plasma, später
vkcube und normaler Steam-Launcher; `unittest`, argv-Listen, Linux-Prozesshandles.
Keine Paketinstallation als impliziter Planschritt.

**Spezifikation:**
[Hybrid-Display-MVP-Design](../specs/2026-11-15-hybrid-display-mvp-design.md).

## Freigabe und globale Grenzen

Aktuell erlaubt sind nur Erstellung/Prüfung dieses Plans und des Designs sowie
der beauftragte Review-Patch und dessen temporäre Anwendbarkeitsprüfung. Kein
hier genannter Produktcode, Test oder Hardwarebefehl wird jetzt ausgeführt.
Auch die nachstehenden Regressionstests können temporäre Dateien, Prozesse,
Sockets oder Test-Git-Repositories erzeugen: Sie benötigen eine spätere Freigabe.

Vor Ausführung [AGENTS.md](../../../AGENTS.md),
[Sicherheitsgrenzen](../../agent-guidance/safety-boundaries.md),
[Belegformat](../../agent-guidance/evidence-format.md),
[Hardwarebaselines](../../agent-guidance/hardware-baselines.md) und Design lesen.
Worktree/Branch/HEAD/Benutzeränderungen prüfen; keine andere Arbeit überschreiben.
Der vorhandene Integrationsworktree ist keine Freigabe für Branchwechsel oder
weitere Worktrees. Staging, Commit, Push, PR, Merge und Workflows jeweils separat.
PR #8 bleibt unabhängig; keine Commit-Schritte aus Methodik automatisch ausführen.

Für alle Aufgaben gelten ausdrücklich:

- KWin besitzt beide physischen Ausgänge; kein direkter DRM-Fallback.
- `gamescope-session-plus` weder starten noch sourcen; `--prefer-output` nicht
  zur Fensterplatzierung verwenden.
- Benutzergesteuerte Werte niemals per Shell auswerten. argv als Liste,
  kein `shell=True`, `eval`, `os.system` oder zusammengesetzter Shellbefehl.
- Keine globalen Umgebungsänderungen und keine aus fremden Prozessen kopierten
  oder geratenen GUI-Variablen. Kindumgebung darf die Elternumgebung nicht ändern.
- Keine Signale an vorbestehende Steam-/Gamescope-Prozesse, keine automatische
  Prozessbeendigung bei unklarer Eigentümerschaft und kein ungeschütztes PID-Race.
- Keine automatische Monitorumschaltung, Displayreparatur, systemweite
  Installation, Standardsitzungsänderung oder automatische Wiederholung.
- Keine Dienste, Plugins, Controllerprofile oder Eingabegeräte manipulieren.
  OutputManager darf keine force-/Hotplug-Operationen ausführen und wird nicht
  eingebunden. Hybrid-Focus und Decky sind nicht Bestandteil des MVP.
- Keine vollständigen Prozessumgebungen, Roh-EDIDs, Seriennummern oder fremden
  Anwendungsargumente in Diagnoseberichten. Keine echten Geheimnisse als Testdaten.
- Kein Container-/ISO-Build, keine Veröffentlichung, keine Lock-/Workflowänderung.
- Grafik-Gate vor Steam-Gate vor Spiel-Gate. Dell validiert HP nicht; nested
  validiert keine direkte Gamescope-DRM-Mehrbildschirmausgabe.

## Dateistruktur und Schnittstellen

Alle folgenden Pfade sind **geplant und noch nicht erstellt**:

| Pfad | Verantwortung |
|---|---|
| `prototype/hybrid-display/src/hybrid_display/__init__.py` | nebenwirkungsfreier Paketimport |
| `prototype/hybrid-display/src/hybrid_display/model.py` | unveränderliche Datenmodelle |
| `prototype/hybrid-display/src/hybrid_display/preflight.py` | reine Startentscheidung |
| `prototype/hybrid-display/src/hybrid_display/outputs.py` | reine EDID-/Ausgangszuordnung |
| `prototype/hybrid-display/src/hybrid_display/command.py` | argv und begrenzte Kindumgebung |
| `prototype/hybrid-display/src/hybrid_display/runner.py` | eigene Kindprozesse und Stopgrenzen |
| `prototype/hybrid-display/src/hybrid_display/collect.py` | explizit lesende Inventaradapter |
| `prototype/hybrid-display/src/hybrid_display/cli.py` | Preflight-/Start-CLI |
| `prototype/hybrid-display/src/hybrid_display/diagnostics.py` | redigierter Bericht |
| `prototype/hybrid-display/bin/hybrid-display-preflight` | repositorylokaler Entrypoint |
| `prototype/hybrid-display/bin/hybrid-display-run` | repositorylokaler Entrypoint |
| `prototype/hybrid-display/README.md` | Bedienung und begrenzter Rückweg |
| `docs/hybrid-display-mvp-test.md` | späteres leeres Hardwareprotokoll |
| `tests/test_hybrid_display_*.py` | isolierte Verhaltens-/Schutztests |

In Tests den geplanten `src`-Pfad explizit ergänzen; keine Installation nötig.
Keine Imports aus `prototype/hybrid-focus`. Reine Modelle benutzen ausschließlich
übergebene Daten und keine Live-Probes beim Import.

Kernverträge, in Aufgabe 1 anzulegen:

- `OutputIdentity(edid_sha256: str, manufacturer: str, model: str)`.
- `Output(identity: OutputIdentity, gpu_pci: str, drm_connector: str,
  kwin_name: str, enabled: bool, mirrored: bool)`.
- `SessionSnapshot(session_type: str, desktop: str, own_local_session: bool,
  kwin_running: bool, outputs: tuple[Output, ...], existing_clients: tuple[str, ...],
  focus_service_active: bool, decky_active: bool, capabilities: frozenset[str])`.
- `PreflightResult(ok: bool, reasons: tuple[str, ...])`.
- `LaunchOptions(client: str, edid_sha256: str, width: int = 1920,
  height: int = 1080, fps: int = 60)`; `client` nur `graphics` oder `steam`.
- `RunResult(exit_code: int, reason: str, unresolved_children: tuple[str, ...])`.
- `GateEvidence(graphics_passed: bool, steam_passed: bool, game_passed: bool)`.

Sichtprüfung, Versions-/Bootbelege und Recoveryfreigabe bleiben zusätzlich im
Hardwareprotokoll; ein CLI-Status kann sie nicht allein bestätigen.

## Review-Fokus

1. Zwei gleiche Monitormodelle oder doppelte EDIDs: eindeutig zuordnen oder
   abbrechen, keine Connector-/Primärmonitorheuristik (Aufgabe 2).
2. Vorbestehendes Steam übernimmt neue Startargumente: Preflight verweigert Start,
   kein automatisches Beenden (Aufgaben 1/5/9).
3. PID-Wiederverwendung oder entkommene Steam-Runtime-Kinder: keine fremden
   Prozesse signalisieren, unaufgelösten Rückbau melden (Aufgabe 4).
4. Fehlende eigene GUI-Umgebung oder aktiver Fokusdienst: blockieren, nichts
   übernehmen/reparieren (Aufgaben 1/5).
5. Native Wayland-Clients erreichen äußeres KWin statt Gamescope: Clientpfad
   belegen, sonst keine Grafik-/Steam-/Spielabnahme (Aufgaben 3/8/9/10).

## Gemeinsamer TDD- und Prüfablauf

Für Aufgaben 1–7 jeweils zuerst den benannten Verhaltenstest schreiben, gezielt
ausführen und den erwarteten fachlichen Fehler bestätigen. Bei fehlendem Modul
ist Importfehler zunächst zulässig; nach minimalem Importgerüst muss die benannte
Verhaltensassertion rot sein, bevor die Funktion implementiert wird. Dann minimal
implementieren, denselben Test grün prüfen und die genannte Regression ausführen.
Kein grünes Ergebnis vorwegnehmen; keine Hardwarefunktion aus Mocks ableiten.

Ab Aufgabe 2 gemeinsame Regression, nur später nach Freigabe:

```bash
python3 -B -m unittest discover -s tests -p 'test_hybrid_display_*.py' -v
```

Aufgaben 8–10 beginnen ebenfalls mit einem roten Test der jeweiligen Gate-Regel.
Das ersetzt nicht den nachfolgenden echten Hardwarebeleg. Hardwareprotokolle
bleiben bis zur Messung leer beziehungsweise ausdrücklich NICHT GETESTET.

## Aufgabe 1: Reine Preflight-Modelle und Sitzungsbedingungen

**Dateien:** Create `prototype/hybrid-display/src/hybrid_display/{__init__,model,preflight}.py`
und `tests/test_hybrid_display_preflight.py`.

**Schnittstelle:** Modelle aus der Tabelle; `evaluate_preflight(snapshot:
SessionSnapshot) -> PreflightResult`. Keine Live-Abfragen.

- [ ] Rot: `test_tty_or_missing_kwin_refuses_start` verlangt `ok=False` und
  konkrete Gründe für TTY, fremden/entfernten Sitzungskontext oder fehlendes KWin.
  Weitere Tests: weniger als zwei aktive erweiterte Outputs, vorhandenes Steam
  oder Gamescope, aktiver Fokusdienst/Decky, fehlende Programme/Optionen.
- [ ] Fehlergrund bestätigen: fehlende sichere Startverweigerung, nicht ein
  Test-Tippfehler. Zulässige vollständig synthetische Plasma-Snapshot wird akzeptiert.
- [ ] Minimal: unveränderliche Modelle und reine Prädikate; Start nur bei
  vollständig bekannten Voraussetzungen. Gründe deterministisch sortieren.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_preflight.py' -v`.
- [ ] Regression: dieselben Fälle inklusive positiver Plasma-Fixture; keine Live-Daten.

**Hardwareprüfung:** keine. **Rollback:** keine Laufzeitänderung; spätere
Dateirücknahme nur für eigene Änderungen und mit passender Freigabe.
**Abbruch:** Live-Zugriffe beim Import oder unklare Voraussetzung wird akzeptiert.
**Verbotene Seiteneffekte:** Dienste/GUI starten, Sessionumgebung importieren,
Prozesse beenden, Testdateien außerhalb des später genehmigten Testbereichs.

## Aufgabe 2: EDID-Zuordnung

**Dateien:** Create `prototype/hybrid-display/src/hybrid_display/outputs.py` und
`tests/test_hybrid_display_outputs.py`; Modify geplante `model.py` nur falls
zum festgelegten Vertrag nötig.

**Schnittstelle:** `resolve_output(outputs: tuple[Output, ...], edid_sha256:
str) -> Output`, bei keinem/einem nicht aktiven/mehreren Treffern `ValueError`.

- [ ] Rot: `test_identity_survives_connector_rename` verlangt gleiche EDID-Auswahl
  nach Umbenennung von DP-1 nach DP-2; `test_duplicate_edid_is_rejected` verlangt
  Ablehnung statt Ersttreffer. Gleiche Hersteller/Modelle mit anderen Hashes
  bleiben getrennt. Fehlender/ungültiger Hash und Spiegelung scheitern.
- [ ] Fachlicher Fehlergrund: Auswahl hängt noch am Connector oder rät bei Ambiguität.
- [ ] Minimal: SHA-256-Format prüfen, genau einen aktiven nicht gespiegelten
  Treffer auswählen; Hersteller, DRM und KWin getrennt erhalten.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_outputs.py' -v`.
- [ ] Regression: gemeinsame Display-Suite ausführen.

**Hardwareprüfung:** erst Aufgabe 8; derzeit nur synthetische EDIDs/Metadaten.
**Rollback:** keine Displayänderung. **Abbruch:** Connector wird als dauerhafte
Identität benutzt oder fehlende Daten lösen Fallback aus.
**Verbotene Seiteneffekte:** force/status schreiben, Hotplug, KWin-Konfiguration,
Roh-EDID-Berichte oder persistente Gaming-Monitorwahl.

## Aufgabe 3: Sichere Argumente und Kindumgebung

**Dateien:** Create `prototype/hybrid-display/src/hybrid_display/command.py` und
`tests/test_hybrid_display_command.py`.

**Schnittstellen:** `build_argv(options: LaunchOptions, capabilities:
frozenset[str]) -> list[str]`; `build_child_env(parent: dict[str, str],
options: LaunchOptions) -> dict[str, str]`. Fähigkeiten stammen später aus
versionsbezogener bestätigter Erhebung, niemals aus Annahmen.

- [ ] Rot: `test_graphics_argv_is_explicitly_nested` verlangt die Liste
  `['gamescope', '--backend', 'wayland', '--expose-wayland', '-w', '1920', '-h', '1080', '-W',
  '1920', '-H', '1080', '-r', '60', '--', 'vkcube']` bei bestätigten Fähigkeiten.
  `test_invalid_or_missing_capabilities_never_fall_back_to_drm` verlangt Fehler.
- [ ] Zusätzlich rot: manipulative Werte werden abgelehnt, Elternumgebung bleibt
  bytegleich, keine `--prefer-output`-/Grab-Flags.
  `test_graphics_client_cannot_use_outer_wayland_target` verlangt für beide
  Clientmodi bestätigtes `--expose-wayland` und blockiert fehlende Unterstützung.
  Steam ergänzt `--steam` nur bei bestätigter lokaler Unterstützung, dann
  `-- steam -gamepadui`; sonst Start ablehnen. Keine Variante ohne interne
  Wayland-Exposition als stillen Ersatz konstruieren.
- [ ] Fachlicher Fehlergrund: freie Befehlszeichenfolge, unsicherer Backendwechsel
  oder ungeprüftes äußeres Wayland-Clientziel wäre noch möglich.
- [ ] Minimal: feste Clientauswahl, positive ganzzahlige Dimensionen/FPS,
  explizites Wayland-Backend, Kopie der eigenen Umgebung ohne globale Änderungen.
  Gamescope stellt interne Clientziele bereit; keine Socketnamen erfinden.
  Der argv-Test prüft diese Anforderung, der echte interne Socket-/Fensterbeleg
  für vkcube und Steam bleibt zwingend Aufgabe 8 beziehungsweise 9.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_command.py' -v`.
- [ ] Regression: gemeinsame Display-Suite.

**Hardwareprüfung:** Backend und tatsächliche innere Clientziele in Aufgaben 8/9.
**Rollback:** keine Starts durch reine Funktionen. **Abbruch:** lokale Optionen
unbestätigt oder Backend/Umgebung nicht deterministisch.
**Verbotene Seiteneffekte:** Shellauswertung, globale Umgebungs-/Portaländerungen,
Sourcen des Sitzungswrappers, Intel-/Polaris-Override, DRM-Fallback.

## Aufgabe 4: Begrenzter Prozesslebenszyklus

**Dateien:** Create `prototype/hybrid-display/src/hybrid_display/runner.py` und
`tests/test_hybrid_display_lifecycle.py`.

**Schnittstelle:** `run_nested(argv: list[str], child_env: dict[str, str]) ->
RunResult`. Interner eigener Prozesshandle für direkt gestartete Kinder;
Stopanforderung nur für stabil belegte Identitäten, kein öffentliches Stoppen
beliebiger PID. Linux-pidfd für Signale verwenden; fehlender sicherer Pfad
bedeutet Meldung/manual recovery, kein PID- oder Prozessgruppen-Kill-Fallback.

- [ ] Rot: `test_stop_never_signals_preexisting_process` verlangt keine Signale
  an eine fremde Steam-Fixture. `test_pid_reuse_or_unknown_owner_refuses_stop`
  verlangt unresolved statt Signal. Früher Exit/Timeout führt zu keinem Restart.
- [ ] Fachlicher Fehlergrund: Eigentumsgrenze und begrenzter Rückbau fehlen.
- [ ] Minimal: eigene neue Prozessgruppe beim Start, direkte Kindhandles erfassen,
  regulären Exit abwarten; genehmigter Stop einmalig TERM nur über sichere Handles.
  Gruppe allein ist kein Signalziel. Entkommene/unbekannte Kinder nur melden;
  keine rekursive Namenssuche, kein KILL. Exit und ungeklärte Kinder zurückgeben.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_lifecycle.py' -v`.
  Adaptertests ohne echte Signale zuerst; kontrollierte harmlose Testkinder erst
  nach passender Testprozessfreigabe. Keine echten Steam-/Gamescope-Prozesse.
- [ ] Regression: gemeinsame Display-Suite inklusive unveränderter Elternumgebung.

**Hardwareprüfung:** regulärer Stop in 8–10; Fehlerinduktion nur extra genehmigt.
**Rollback:** nur eigene kontrollierte Testkinder regulär beenden; unklare
Eigentümerschaft melden. **Abbruch:** fremdes Signal, PID-Race oder unaufgelöster
Rückbau. **Verbotene Seiteneffekte:** pkill/killall, automatisches KILL/Retry,
Dienst-/Displayreset, Aufräumen fremder Steam-Runtime-Prozesse.

## Aufgabe 5: Lesender Preflight und manuelle CLI

**Dateien:** Create geplante `collect.py`, `cli.py`, beide `bin/`-Entrypoints,
`prototype/hybrid-display/README.md`, `tests/test_hybrid_display_cli.py`.

**Schnittstellen:** `collect_snapshot() -> SessionSnapshot`, bei fehlendem
Beleg Fehler statt Annahme; `main_preflight(argv: list[str]) -> int` und
`main_run(argv: list[str]) -> int`. CLI: Preflight ohne Argumente; Start verlangt
`--client graphics|steam --monitor-edid SHA256`. Exit 0 erfolgreich, 2
Voraussetzung/Argument abgelehnt, 3 Laufzeitfehler. Preflight startet keine
Grafik-/Clientprozesse; ausschließlich wirkungsgeprüfte lesende Hilfsbefehle
sind nach entsprechender Freigabe zulässig.

- [ ] Rot: `test_failed_preflight_spawns_nothing`, `test_existing_steam_is_not_killed`
  und `test_foreign_session_is_not_imported`. Ein erfolgreiches synthetisches
  Startkommando ruft Runner genau einmal mit der erwarteten Liste auf.
- [ ] Fachlicher Fehlergrund: Orchestrierung könnte Preflight umgehen oder eine
  fremde GUI-Sitzung/Instanz übernehmen.
- [ ] Minimal: sichere Read-only-Adapter, harte Prüfung der eigenen GUI-Sitzung
  vor jeder GUI-Abfrage, kein D-Bus-Autostart. sysfs nur lesen. Für KWin zuerst
  Ausgabeformat des lokal vorhandenen `kscreen-doctor -o` statisch prüfen und
  dessen lesenden GUI-Aufruf gesondert freigeben; Fixtureparser dafür erstellen.
  Kein Aufruf bei TTY/SSH ohne belegten eigenen GUI-Kontext. Falls Ausgabe
  EDID/Connector/KWin nicht eindeutig verknüpft, BLOCKED statt Layoutdatei als
  Laufzeitbeleg. Optionsbestätigung nicht ungeprüft beim Import ausführen.
- [ ] Minimal ergänzen: README erklärt manuelle KWin-Platzierung, explizite
  Bestätigung vor Abnahme, reguläres Schließen und ungelöste Rückbaufehler.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_cli.py' -v`.
- [ ] Regression: gemeinsame Display-Suite; Adapterfixtures für fehlende Rechte,
  unvollständige Ausgabe und aktiven Fokusdienst. Keine Live-Probes im Test.

**Hardwareprüfung:** erst später freigegebener Preflight in Aufgabe 8.
**Rollback:** CLI-Ablehnung lässt Sitzung unverändert; erfolgreiche Starts nach
Aufgabe 4 stoppen. **Abbruch:** GUI-Absturz, unklare Befehlswirkung oder geratene
Zuordnung. **Verbotene Seiteneffekte:** install/enable/start eines Dienstes,
automatische Fenster-/Displayplatzierung, neue Sitzung, Standardänderung.

## Aufgabe 6: Begrenzte redigierte Diagnose

**Dateien:** Create `prototype/hybrid-display/src/hybrid_display/diagnostics.py`
und `tests/test_hybrid_display_privacy.py`; Modify geplante `cli.py` für Ausgabe.

**Schnittstelle:** `render_report(fields: dict[str, object]) -> str` mit festem
Schema: `schema_version`, `boot_context`, `versions`, `outputs`, `selection`,
`owned_processes`, `backend`, `result`, `errors`, `limitations`. Nur explizit
gesammelte Felder, keine beliebigen Objekte/Umgebungen serialisieren.

- [ ] Rot: `test_unknown_fields_raw_edid_and_synthetic_secrets_are_omitted`
  verlangt keine fremden argv/Umgebungs-/Seriennummernfelder.
  `test_journal_limits_are_visible` verlangt höchstens 100 Einträge je Quelle,
  höchstens 512 Zeichen je Zeile und sichtbaren Kürzungshinweis.
- [ ] Fachlicher Fehlergrund: bisher wären unbeschränkte Rohdaten oder
  unbekannte Felder in der Ausgabe möglich.
- [ ] Minimal: Feld- und Typprüfung, erlaubte Fakten extrahieren, sensible
  Zeilen weglassen, Zugriffs-/Kürzungsgrenzen dokumentieren. Kindausgaben nicht
  ungefiltert durchreichen. Standard stdout ohne Logdatei/Cache.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_privacy.py' -v`.
- [ ] Regression: gemeinsame Display-Suite; synthetische Geheimnisse, kein
  tatsächlicher Secret-Scan mit Wertausgabe und keine echten privaten Testdaten.

**Hardwareprüfung:** redigierte Vorher-/Nachherausgabe erst ab Aufgabe 8.
**Rollback:** keine Exportartefakte standardmäßig. **Abbruch:** unredigierte
sensible Ausgabe oder nicht markierter fehlender Messkontext.
**Verbotene Seiteneffekte:** Roh-EDID-/Environmentdump, automatischer Export,
Journalrotation/-löschung, private Steamdaten in teilbaren Berichten.

## Aufgabe 7: Schutzverträge und Abnahmevorlage

**Dateien:** Create `tests/test_hybrid_display_safety.py`,
`tests/test_hybrid_display_gates.py`, `docs/hybrid-display-mvp-test.md` und
`prototype/hybrid-display/src/hybrid_display/gates.py`; Modify geplante README.

**Schnittstellen:** `can_run_stage(stage: str, evidence: GateEvidence) -> bool`;
stage nur `graphics`, `steam`, `game`. Graphics ohne vorausgehenden Gatebeleg,
Steam nur mit graphics_passed, Game nur mit graphics_passed und steam_passed.
Diese reine Funktion strukturiert das Protokoll, ersetzt keine Freigabe und
ist kein alleiniger Nachweis einer tatsächlich bestandenen Messung.

- [ ] Rot: `test_release_and_focus_wiring_is_rejected` prüft Fixtures mit
  Einbindung in Container-/ISO-/Workflow-/Sitzungsdateien und Fokusimports.
  Realer Schutzvergleich verlangt unveränderte geschützte Eingaben gegenüber
  dem vor Implementierung ausdrücklich festgelegten Basiscommit; in diesem Plan
  `c61d0a4e821cc9984343b70bb471d9320510dc95`.
- [ ] Fachlicher Fehlergrund: bisher fehlt eine prüfende Grenze gegen unbeabsichtigte
  Integration. Test muss eine synthetisch veränderte Eingabe erkennen, nicht nur
  unveränderte Dateien grün lesen.
- [ ] Minimal: Lese-/Fixturetests für `.github/workflows/`, `Containerfile`,
  `build_files/`, `system_files/`, `installer/`, `disk_config/`, `image-lock.json`
  und `prototype/hybrid-focus/`; keine Snapshotaktualisierung, um Rot zu umgehen.
  `gates.py` zunächst nur unbekannte stage ablehnen; weitere Fälle folgen in 8–10.
- [ ] Vorlage enthält Hardware/Kabel/EDID, Versionen, Boot-ID, monotone Marker,
  Freigabeumfang, F1–F12, Baseline, Gatebelege, Fehler, Stop und Rückkehr.
  Nicht gemessene Felder bleiben NICHT GETESTET. HP/Dell getrennt.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_safety.py' -v`.
- [ ] Regression: gemeinsame Display-Suite; anschließend nach separater
  Schreibtestfreigabe `python3 -B -m unittest discover -s tests -v`.

**Hardwareprüfung:** keine hier; Vorlage für 8–10. **Rollback:** keine
Releaseeingabe verändern; bei Verletzung stoppen, keine fremden Änderungen
zurücksetzen. **Abbruch:** geschützter Pfad verändert oder Test verlangt reale
Systemmutation. **Verbotene Seiteneffekte:** Release-/ISO-Einbindung, Classifier-
Änderung, Fokusinstallation, Git-Schreibaktion, Build oder Workflowstart.

## Aufgabe 8: Erstes Grafikclient-Gate

**Dateien:** Modify geplante `gates.py`, `tests/test_hybrid_display_gates.py`
und `docs/hybrid-display-mvp-test.md`; keine Änderungen am Displaybackend.

- [ ] Rot: `test_graphics_stage_needs_no_steam_or_game` verlangt Graphics mit
  leeren Gatebelegen; Steam/Game bleiben ohne Grafikbeleg gesperrt.
- [ ] Fachlicher Fehlergrund: gestufte Freigabereihenfolge fehlt noch.
- [ ] Minimal: reine Gateentscheidung ergänzen; Protokollabschnitt für Grafik.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_gates.py' -v`.
- [ ] Regression: gemeinsame Display-Suite; unveränderte Schutzdateien prüfen.

**Hardwareprüfung, ausschließlich nach neuer konkreter Freigabe:** Dell neu
inventarisieren, Arbeit sichern, Tastatur/Maus und Rückweg bestätigen. Umgang mit
aktivem Fokusdienst separat klären; Preflight darf ihn nicht stoppen. Separat
genehmigter Wechsel nach Plasma und nötige manuelle Ausgangsaktivierung sind
Vorbereitung, keine Launcherfunktion. Fünf Minuten Plasma-Baseline ohne neue
DRM-Fehler, dann Preflight und:

```bash
python3 -B prototype/hybrid-display/bin/hybrid-display-run --client graphics --monitor-edid BESTAETIGTER_SHA256
```

`BESTAETIGTER_SHA256` ist vor Verwendung durch einen frisch belegten Hash zu
ersetzen. Das Startkommando selbst konfiguriert keinen Ausgang. Gamescope manuell
auf den gewählten Ausgang verschieben, Vollbild bestätigen, Terminal/Browser auf
Monitor 2 bedienen; anschließend vkcube/Gamescope regulär schließen. Quellen,
Exitcodes, Sichtprüfung und monotonen Fehlervergleich protokollieren. Bereits
hier belegen, dass vkcube innerhalb Gamescopes läuft und dessen internen
Xwayland- beziehungsweise Wayland-Endpunkt verwendet; äußeres KWin als direktes
Clientziel ist ein Fehler, auch wenn das Fenster zufällig am richtigen Monitor ist.

**Rollback:** eigene Instanz regulär schließen, KWin/beide Ausgänge prüfen;
einmaliges TERM nur bei separat genehmigtem sicheren Eigentumsnachweis.
**Abbruch:** äußeres Clientziel, schwarze Ausgabe, neuer i915-/DRM-Fehler, KWin-Absturz, unklare
Zuordnung, fehlender Preflight oder Rückweg. Kein bestandener Grafikbeleg.
**Verbotene Seiteneffekte:** Steam/Spiel starten, Displayreparatur, Hotplug,
Retry, Controlleränderung, unautorisierter Export oder Neustart.

## Aufgabe 9: Steam-Gamepad-UI-Gate

**Dateien:** Modify geplante `gates.py`, `tests/test_hybrid_display_gates.py`,
`docs/hybrid-display-mvp-test.md`; `command.py` nur bei durch Test belegtem Bedarf.

- [ ] Rot: `test_steam_requires_passed_graphics` verlangt Ablehnung bei
  graphics_passed=False und Akzeptanz bei belegtem Grafik-Gate.
- [ ] Fachlicher Fehlergrund: Steam könnte vor dem Grafik-Gate zugelassen werden.
- [ ] Minimal: Gateentscheidung und Protokoll ergänzen, keine automatische
  Auswertung eines vorherigen Exitcodes als Hardwareerfolg.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_gates.py' -v`.
- [ ] Regression: gemeinsame Display-Suite, insbesondere vorhandenes Steam,
  fremde PID und Kindumgebungsgrenzen.

**Hardwareprüfung, neue Steam-Start-/Stopfreigabe erforderlich:** Grafikprotokoll
vollständig bestanden und Voraussetzungen frisch bestätigt. Vorhandenes Steam
durch Bediener regulär beenden; Preflight erneut. Start mit derselben CLI und
`--client steam`. Benötigte lokale Optionen vorher bestätigen. Gamescope manuell
platzieren, dann Gamepad UI nur dort nachweisen; Monitor 2 bedienen. Innere X11-
und Wayland-Ziele anhand erlaubter Felder/Fenster prüfen. Overlayfunktion separat
beobachten, keine Decky-Funktion verlangen. Steam vollständig beenden und
Gamescope-/Plasma-Rückkehr bestätigen. Steam kann eigene reguläre Nutzerdaten
schreiben; die spätere Freigabe muss das umfassen, ohne Projekt-/Systeminstallation.

**Rollback:** reguläres Steam-Ende, eigene Gamescope-Instanz schließen, beide
Plasma-Ausgänge prüfen. Entkommene/unbekannte Runtime-Kinder melden, nicht killen.
**Abbruch:** bestehende Steam-Instanz übernimmt Start, Client am äußeren KWin,
falscher Monitor, neues DRM-Problem, nicht vollständiger Rückbau.
**Verbotene Seiteneffekte:** Spielstart, SteamOS-Sitzungswrapper, Decky,
automatische Beendigung vorhandenen Steams, globale Umgebungs-/Portaländerung.

## Aufgabe 10: Spiel-, Renderer- und Stabilitäts-Gate

**Dateien:** Modify geplante `gates.py`, `tests/test_hybrid_display_gates.py`,
`docs/hybrid-display-mvp-test.md` und README für gemessene Grenzen.

- [ ] Rot: `test_game_requires_both_prior_gates` verlangt graphics_passed und
  steam_passed; `test_game_passed_flag_alone_is_insufficient` verhindert Abkürzung.
- [ ] Fachlicher Fehlergrund: Spieltest wäre ohne beide Vorbelege möglich.
- [ ] Minimal: Gateentscheidung ergänzen; Hardwareprotokoll für Renderer,
  F1–F12, drei Zyklen und 30-Minuten-Durchlauf. Keine Rendererwerte erfinden.
- [ ] Gezielt: `python3 -B -m unittest discover -s tests -p 'test_hybrid_display_gates.py' -v`.
- [ ] Regression: gemeinsame Display-Suite; volle Repositorysuite nur mit
  passender Schreibtestfreigabe und keine Builds daraus ableiten.

**Hardwareprüfung, eigene Freigabe für ein konkret benanntes vorhandenes Spiel:**
nach bestandenem Steam-Gate Renderer aus Spiel/zulässiger Spielanzeige erfassen.
Intel UHD 630 auf Dell, später Radeon E9173 auf HP; llvmpipe/softpipe/lavapipe
scheitern. Gamescopes Vulkan-Gerätewahl oder ein offener DRM-Knoten genügt nicht.
Desktopinteraktion, Spielende, Steam-Ende und Gamescope-Ende getrennt prüfen.
Drei vollständige Start-/Stopzyklen, einer mindestens 30 Minuten; FPS/Framezeiten
soweit vorhanden, Last und Fokusverhalten notieren. HDR/VRR/Direct Scanout und
Latenz nur bei tatsächlichem Nachweis bewerten. Fehlende Messwerkzeuge nicht
installieren; fehlenden Beleg ausweisen.

**Rollback:** Spiel regulär schließen, Steam vollständig beenden, eigene
Gamescope-Instanz schließen, KWin/beide Displays/Desktopanwendung prüfen.
**Abbruch:** Software-Rendering, Ausgangsverlust, KWin-Absturz, neuer DRM-Fehler,
Fokusminimierung oder nicht sicherer Rückbau. Kein Wiederholungsversuch als Reparatur.
**Verbotene Seiteneffekte:** Controller-Routing, Profile/Glyphenintegration,
Audioauswahl, automatischer Sitzungswechsel, Veröffentlichung oder HP-Abnahme aus Dell.

## Eigener späterer Schritt: CI-Klassifizierung

Der aktuelle [Classifier](../../../scripts/classify-container-changes.py)
kennt `prototype/hybrid-focus/` und `tests/test_hybrid_focus_*.py` als F.
Neue Pfade unter `prototype/hybrid-display/` und `tests/test_hybrid_display_*.py`
fallen im aktuell gelesenen Stand auf unbekannte Kategorie G und blockieren die
Klassifizierung. Dokumentationspfade liegen dagegen in E. Nicht durch Umbenennen
in Fokusdateien umgehen oder eine erfolgreiche Remote-CI vorwegnehmen.

**Jetzt keine Änderung.** Ein späterer eigener Änderungsauftrag müsste benennen:

- **Dateien:** `scripts/classify-container-changes.py` und
  `tests/test_container_workflow_policy.py`.
- **Rot/fachlicher Grund:** neue reine MVP-Pfade sind derzeit G/blocking;
  Policytest verlangt Tests ohne Container/Release/ISO für PR bzw. reinen
  Dokumentations-/Prototyp-Main-Push. Unbekannte Pfade müssen blockiert bleiben.
- **Minimal:** explizite neue Pfadklasse nach gesonderter Policyentscheidung;
  bestehende Dispatch-/Main-/Mischklassenregeln nicht aufweichen.
- **Gezielt:** `python3 -B -m unittest discover -s tests -p 'test_container_workflow_policy.py' -v`.
- **Regression:** `python3 -B -m unittest discover -s tests -p 'test_build_provenance.py' -v`
  und volle Policy-Matrix, insbesondere unbekannte/Mischpfade sowie
  `run_iso=false`; Schreibtestfreigabe nötig.
- **Hardwareprüfung:** keine. **Rollback:** ausschließlich eigene freigegebene
  Policyänderung zurücknehmen, keine Benutzeränderung überschreiben.
- **Abbruch:** neue Veröffentlichung, ISO-Auslösung oder abgeschwächtes Fail-closed.
- **Verbotene Seiteneffekte:** Workflowstart, Container-/ISO-Build, Push/PR/Merge
  oder automatische Revision-/Lockänderung.

Classifieränderungen sind selbst Kategorie B und können bei später autorisierten
Remote-Ereignissen Containerprüfung auslösen. Das muss eine künftige Git-/CI-
Freigabe ausdrücklich abdecken. Kein heutiger Dokumentationsauftrag erlaubt sie.

## Ausführungsgates und Abschluss

Vor späterer Umsetzung Design/Plan prüfen und genaue Pfade, Testnebenwirkungen
und Ausführungsart freigeben. Hardwarestufen 8, 9 und 10 benötigen jeweils eigene
Start-/Stop-/Recoverygrenzen und frische Voraussetzungen. HP bekommt ein eigenes
Protokoll mit direktem E9173-Anschluss und erhaltener historischer Rückkehrbasis.
Kein Hardwareerfolg wird durch bestandene Softwaretests ersetzt.

Nach jeder freigegebenen Stufe nur tatsächlich ausgeführte Prüfungen melden,
vollständigen Diff einschließlich neuer Dateien sowie frischen Status lesen.
Kein Staging/Commit, keine Workflow-/Build-/Releaseaktion als Abschlussautomatismus.
