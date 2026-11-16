# Linux-Hostadapter Implementation Plan

> Für eine spätere ausdrücklich freigegebene Umsetzung:
> superpowers:subagent-driven-development oder superpowers:executing-plans
> taskweise verwenden. Checkboxen sind Planung, keine Ausführungsfreigabe.
> Keine automatischen Commit-/Pushschritte.

**Ziel:** Einen eng begrenzten, explizit aufgerufenen Leseadapter vorbereiten,
ohne den reinen Collector oder die Start-/Releasegrenzen aufzuweichen.

**Architektur:** Injizierter HostReader liefert begrenzte private Rohdaten;
reine Parser und Orchestrierung bauen die neun Collector-Facts. Nur der
zukünftige Linux-Reader darf benannte Hostquellen lesen. Keine Kindprozesse.

**Technik:** Python, unittest-Fixtures, exakte Built-in-Typen, immutable DTOs,
fd-relative Dateizugriffe und synchron begrenzter lokaler IPC-Transport.
Das konkrete D-Bus-Binding benötigt vor seiner Implementierung eine gesonderte
Dependency-/Versionsprüfung; nichts installieren.

**Spezifikation:** [Adapterdesign](../specs/2026-11-16-hybrid-display-linux-adapter-design.md).
Exakte Ausgangsbasis: `664047789e099a9f2c2371972225fcff304be706`.

## Globale Grenzen

Dieser Auftrag erstellt nur Design und Plan. Kein nachstehender Test, Parser,
Adapter, Hostaufruf oder Produktpatch wird jetzt implementiert/ausgeführt.
AGENTS, Sicherheitsgrenzen und die bisherigen Reinheitsverträge bleiben
unverändert. Vollständige Quellen-Allowlist, Limits und Codes stehen verbindlich
im Design; keine selbständige Erweiterung durch eine Implementierung.

Gesamtfrist 5 Sekunden; rohe Gesamtnutzlast 262144 Bytes; 16 Outputs/Clients;
3 Capabilities; keine Retries; payload=None bei jedem Fehler. Metaklassen- und
Container-Unterklassen vor jeder Callbackmöglichkeit durch `is` ablehnen.
Keine Signale, Threads, Kindprozesse, Installationen, Logs, Exporte oder GUIstarts.
Keine Änderungen an Collector, Modellen, Preflight, CLI, Lifecycle oder Diagnostics.
Keine Produkt-/Session-/Releaseintegration, keine Workflows/Builds/Git-Schreibaktionen.
Tests mit temporären Dateien/Prozessen benötigen später eine eigene passende
Freigabe; die hier zuerst geplanten Tests benutzen ausschließlich In-Memory-Doubles.

## Review-Fokus und Abhängigkeiten

1. PID-/Owner-Wechsel während Collection: vollständige Ablehnung statt fremder Sitzung.
2. Fehlendes enabled, NaN/Inf oder bool als Maßzahl: unbekannt bleibt blockierend.
3. Sysfs-Symlink/Bind-Mount/Traversal: kein Ausbruch aus festem Quellraum.
4. Zu großer IPC-Header vor Bodyallokation und hängender Kernelread:
   Grenzen vor Verarbeitung, unbewiesene Deadline blockiert vor I/O.
5. Leere Clientliste oder bloße Capabilitybehauptung: kein Nachweis von
   Prozessfreiheit/Optionsunterstützung; kein vollständiger Live-Snapshot.

Jeder Punkt besitzt unten benannte rote Tests. Sie sind Verhaltensfälle mit
festen erwarteten Codes, keine Quelltext-Grep-Tests als Ersatz für Laufzeitgrenzen.

Die fachlichen Stufen 1–9 entwickeln nur reine Verträge und Transportdoubles.
Stufe 10 präzisiert nach separater Freigabe die existierende Safetyzuordnung.
**Erst nach erfolgreicher Stufe 10** dürfen die in 7 beschriebenen nativen
Operationen überhaupt implementiert werden; ihre Doppelfälle werden dann erneut
gegen das native, weiterhin vollständig injizierte Backend geprüft. Kein
temporäres blanket ignore und kein erlaubnisloses Live-I/O für einen Rotnachweis.
Stufe 11 ist ein neuer Auftrag, nicht Teil einer Implementierungsfreigabe.

## Geplante Dateiverantwortung und Schnittstellen

Alle hier genannten neuen Produkt-/Testdateien sind Zukunft, nicht heutiger Scope.
Produktbasis P = `prototype/hybrid-display/src/hybrid_display/`;
Testbasis T = `tests/`. Namen in Stufen sind relativ zu diesen expliziten Basen.

| Datei | Verantwortung |
|---|---|
| P/host_reader.py | Protocol, geschlossene Keys und private immutable Ergebnisobjekte |
| P/parse_session.py | eigene Sitzung/Owner aus begrenzten Daten prüfen |
| P/parse_kscreen.py | versionsgebundene KScreen-Daten und Geometrie |
| P/parse_drm.py | DRM-Flags, EDID und stabile Zuordnung |
| P/reader_policy.py | erlaubte Parameter, Pfade und IPC-Operationen |
| P/reader_commands.py | jede Befehlsanforderung ohne Spawn ablehnen |
| P/linux_reader.py | einzige spätere native Hostschicht; bis Safetygate nur injizierte Doubles |
| P/adapter.py | Reihenfolge, Fristen, Konsistenz und Collectorübergabe |
| T/test_hybrid_display_reader.py | Protocol/DTO/Metaklassen-Verträge |
| T/test_hybrid_display_parse_session.py | synthetische Sitzungspayloads |
| T/test_hybrid_display_parse_kscreen.py | begrenzte KScreen-Fixtures |
| T/test_hybrid_display_parse_drm.py | synthetische EDID-/Connector-Fixtures |
| T/test_hybrid_display_reader_policy.py | Allowlist/Traversal/Mount-/IPC-Policy |
| T/test_hybrid_display_reader_commands.py | Null-Befehlsallowlist |
| T/test_hybrid_display_linux_reader.py | injizierte Datei-/IPC-Transportdoubles |
| T/test_hybrid_display_adapter.py | atomare Orchestrierung und Collectorintegration |

ReadResult hat payload: bytes|None (repr=False), reasons: tuple[str,...].
ParseResult hat value: private DTO|None (repr=False), reasons: tuple[str,...].
AdapterResult hat snapshot: SessionSnapshot|None (repr=False),
reasons: tuple[str,...]; keine öffentlichen Rohfacts/Geometrie.
Alle results frozen; genau ein Payload oder Fehler, nie beide, keine generischen
Exceptiontexte. Öffentliche Konstruktoren prüfen ihre Invarianten.
HostReader.read_env(key: EnvKey)->ReadResult,
read_file(source: FileSource)->ReadResult,
query(query: BusQuery)->ReadResult. IPC-Rohwerte werden als begrenztes
versionsgebundenes Frame geliefert, ausschließlich Decoder in Parsermodulen.
Enums und DTOs niemals durch Namen/Gleichheitsmethoden fremder Typen imitierbar.

DeclaredFacts und ConnectorManifest sind gemäß Design streng begrenzte private
DTOs. Ein separater In-Memory-Fixturebeleg kann Vollständigkeit für Tests
repräsentieren; der native Reader kann ihn nicht selbst erzeugen.
Keine öffentliche complete=true-Abkürzung für echten Live-Erfolg.

## Einheitlicher späterer TDD-Zyklus

Für jede Stufe:
- [ ] Benannten Test gegen minimales importierbares Gerüst schreiben.
- [ ] Nur diesen Test starten, korrekten Assertion-Rotgrund dokumentieren.
      Import-/Syntaxfehler sind kein fachlicher Rotnachweis.
- [ ] Kleinste beschriebene Umsetzung, kein zusätzlicher Hostzugriff.
- [ ] Gleichen Test grün; anschließend das benannte Modul vollständig prüfen.
- [ ] Diff einschließlich neuer Dateien lesen; passende Regression nach Freigabe.
Keine konkreten künftigen Testzahlen vorwegnehmen. Baseline des Collectorstandes
war 371; spätere Zahlen aus tatsächlich ausgeführten Prüfungen berichten.

Prüfbefehle im Folgenden sind ausschließlich für eine spätere Freigabe:
`PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest tests.<Modul> -v`.
Kein py_compile-Cache; Syntax/AST nur speicherintern.

### 1. HostReader-Protokoll und Ergebnisobjekte

**Dateien:** P/host_reader.py; T/test_hybrid_display_reader.py.
**Interfaces:** obige ReadResult/ParseResult/AdapterResult, Enums und
HostReader-Protocol, noch ohne Linuximplementierung.
- [ ] Rot: test_payload_is_detached_hidden_and_atomic verlangt keine Aliase,
  keine Rohwerte in repr/str und payload=None bei Fehler.
- [ ] Rot: test_metaclass_and_container_callbacks_never_run prüft list/tuple/set/
  frozenset/dict-/bytes-Unterklassen mit eigener Metaklasse, calls exakt leer.
- [ ] Rotgrund: ungeschütztes DTO würde Alias/Callback oder Teilpayload zulassen.
- [ ] Minimal: immutable DTOs, feste Codes, Identitätsprüfungen, keine I/O-Imports.
- [ ] Prüfen: test_hybrid_display_reader vollständig; bestehender Collector unverändert.
**Abbruch:** zusätzlicher dynamischer SourceKey, Rohdatenrepr oder Import-I/O.
**Verboten:** Hostzugriffe, Threads, Methodenimplementierung durch Protocol-Defaults.

### 2. Reine Sitzungsparser

**Dateien:** P/parse_session.py; T/test_hybrid_display_parse_session.py.
**Interface:** parse_session(raw: SessionRaw, own: OwnIdentity)->ParseResult.
- [ ] Rot: test_foreign_remote_inactive_or_uid_mismatch_blocks erwartet
  session_unverified und value=None; keine KScreen-Anfrage im aufrufenden Double.
- [ ] Rot: test_owner_pid_or_session_changes_blocks prüft doppelte Aufnahme.
- [ ] Rotgrund: fehlende kreuzweise Eigentumsprüfung würde fremde GUI übernehmen.
- [ ] Minimal: fünf eigene Umgebungswerte gegen B3/B4 prüfen, UID/Sessiongleichheit,
  vollständige Typ-/Schema-/Längenprüfung; keine Annahme aus Env allein.
- [ ] Prüfen: test_hybrid_display_parse_session, dann Reader-DTO-Tests.
**Abbruch:** fehlende Pflichtproperty oder nicht bestätigter Owner wird akzeptiert.
**Verboten:** Logind-/D-Bus-Zugriffe im Parser, fremde Umgebungen, Variablen raten.

### 3. Reine KScreen-Parser

**Dateien:** P/parse_kscreen.py; T/test_hybrid_display_parse_kscreen.py.
**Interface:** parse_kscreen(frame: bytes, profile: KScreenProfile)->ParseResult.
- [ ] Rot: test_missing_enabled_unknown_profile_or_invalid_scale_blocks;
  kscreen_profile_unverified beziehungsweise kscreen_schema_invalid, value=None.
- [ ] Rot: test_limits_before_decode_and_geometry_overlap prüft 17 Outputs,
  129 Modes, doppelte Keys, Tiefe 9, NaN/Inf/bool, scale und Rotation,
  clone/replication/Überlappung und nebeneinander liegende gleichwertige Fixtures.
- [ ] Rotgrund: fehlende Profil-/Größenprüfung oder geratenes enabled/Spiegelung.
- [ ] Minimal: exakt bestätigte Profilprojektion des Designs, begrenzter Decoder;
  Geometrie privat, kein Output-Identitätsfallback.
- [ ] Prüfen: test_hybrid_display_parse_kscreen vollständig.
**Abbruch:** Zielversionsschema nicht statisch bestätigt, optionale Pflichtdaten.
**Verboten:** kscreen-doctor, Layoutdateien, Methodenaufrufe, Geometrieänderung.

### 4. Reine DRM-/EDID-Parser

**Dateien:** P/parse_drm.py; T/test_hybrid_display_parse_drm.py.
**Interface:** parse_drm(raw: DrmRaw)->ParseResult;
associate(kscreen: KScreenData, drm: DrmData)->ParseResult.
- [ ] Rot: test_edid_limit_checksum_extension_and_empty_rules_blocks; edid_invalid.
- [ ] Rot: test_duplicate_gpu_name_or_digest_and_disagreement_blocks;
  association_ambiguous/inventory_changed statt erstem Treffer.
- [ ] Rot: test_hash_internal_only_and_prefix_collision_not_selection prüft
  keine EDID-/Hash-/Adresswerte in Resultrepr; getrennte unveränderliche Outputs.
- [ ] Rotgrund: fehlende EDID-Prüfung oder mehrdeutige Zuordnung würde Erfolg liefern.
- [ ] Minimal: höchstens 4096 Bytes, Header/Blocksummen/Extensionzahl; SHA-256
  intern; genaue Zuordnung mit B6 und kanonischer PCI-/Connectoridentität.
- [ ] Prüfen: test_hybrid_display_parse_drm und unveränderte Output-/Collector-Tests.
**Abbruch:** Raw-EDID-/Serienfelder werden Teil von Facts/Fehlern, Fallbackmonitor.
**Verboten:** sysfs lesen, bestehende Modelle oder Collector lockern.

### 5. Allowlist- und Pfadvalidierung

**Dateien:** P/reader_policy.py; T/test_hybrid_display_reader_policy.py.
**Interfaces:** validate_source(source: FileSource)->ParseResult;
validate_query(query: BusQuery)->ParseResult; validate_manifest(value: object)->ParseResult.
- [ ] Rot: test_neighbor_path_traversal_symlink_mount_and_parameter_denied;
  source_not_allowed/source_type_invalid vor jedem Double-read.
- [ ] Rot: test_ipc_autostart_set_introspection_foreign_owner_or_network_denied.
- [ ] Rot: test_bounded_auth_hello_allowed_but_requestname_addmatch_startservice_denied.
- [ ] Rot: test_normal_card_symlink_allowed_but_swapped_gpu_link_denied.
- [ ] Rotgrund: breite Pfad-/Methodenpräfixprüfung würde eine benachbarte Quelle erlauben.
- [ ] Minimal: jede Tabellenquelle einzeln modellieren; fixed roots,
  kontrollierte Links, feste Bus-/Methodenargumente, negative Grenzen ohne I/O.
  Policy verarbeitet ausschließlich Keys und synthetische Auflösungsmetadaten;
  Hostpfadliterale und native Auflösung bleiben allein in linux_reader.py.
- [ ] Prüfen: test_hybrid_display_reader_policy inklusive bool/int und Metaklassen.
**Abbruch:** freie Pfadstrings, globale Sysfs-Freigabe oder unbestätigter Sessionbus.
**Verboten:** tatsächliches open/socket, Existenzprobes, rekursive Enumeration.

### 6. Begrenzte Befehlsgrenze mit Testdouble

**Dateien:** P/reader_commands.py; T/test_hybrid_display_reader_commands.py.
**Interface:** reject_command(argv: object)->ReadResult.
- [ ] Rot: test_all_argv_rejected_before_spawn verlangt command_not_allowed,
  payload=None, exakt null Calls am injizierten Spawn-Double.
- [ ] Rot: test_shell_tuple_subclass_and_fake_timeout_wrapper_never_visited.
- [ ] Rotgrund: eine vermeintliche Read-only-Ausnahme würde einen Prozess starten.
- [ ] Minimal: alle Anforderungen ablehnen; erlaubte argv-Menge ist leer.
- [ ] Prüfen: test_hybrid_display_reader_commands.
**Abbruch:** Anforderung an einen echten Hilfsbefehl; neues Konzept nötig.
**Verboten:** subprocess, shell, stdin/stdout/stderr-Vererbung, kill/timeout-Wrapper.
Eine positive Befehlsimplementierung ist ausdrücklich nicht Teil dieses Plans;
sie wäre ohne neue Lösung des Signal-/Timeoutkonflikts widersprüchlich.

### 7. Begrenzter Datei- und IPC-Reader mit Testdouble

**Dateien:** P/linux_reader.py; T/test_hybrid_display_linux_reader.py.
**Interface:** LinuxReader(transport: ReaderTransport, clock: Clock).
ReaderTransport ist ein injiziertes Low-level-Protokoll mit open_readonly,
stat_handle, read_chunk, close_handle und begrenzten Unix-Message-Transaktionen;
in dieser Stufe nur Fake. Kein Aufruf namens open, keine Hostpfadliterale oder
Hostimports vor Stufe 10: der bestehende Kernchecker bleibt bis dahin grün.
Die reale Zuordnung zu nativen Primitiven erfolgt erst nach dessen gezielter
Migration, ausschließlich in linux_reader.py.
- [ ] Rot: test_limit_plus_one_size_zero_and_deadline_gate_before_read:
  source_limit/reader_deadline_unverified, kein unbounded read.
- [ ] Rot: test_replaced_inode_pid_starttime_or_owner_blocks_atomically.
- [ ] Rot: test_frame_header_limit_and_unexpected_message_budget_before_decode.
- [ ] Rot: test_timeout_closes_own_fds_without_signal_thread_or_retry.
- [ ] Rotgrund: fehlende Vorprüfung würde I/O beginnen, oversize allokieren oder hängen.
- [ ] Minimal: Policyaufruf vor Transport, Frist-/Bytebudgets, fd-relative
  Kontrollschritte, zwei Konsistenzaufnahmen, feste Fehler ohne Exceptiontext.
- [ ] Prüfen: test_hybrid_display_linux_reader plus Policy-/Parsermodule.
**Abbruch:** unbewiesene Kerneldeadline, nicht begrenztes Binding, Autostart,
dynamische Pfade oder native I/O vor Safetygate.
**Verboten:** echte Dateierhebung, IPC-Verbindung oder Signal an Testprozesse.
Nach Stufe 10 eigener genehmigter Unterabschnitt: exakte native Primitiven nur
hier verdrahten, identische Tests mit injizierten Low-level-Doubles erneut;
Binding/Version und Kernelfristen vorher statisch belegen, nichts installieren.

### 8. Orchestrierung zu Facts

**Dateien:** P/adapter.py; T/test_hybrid_display_adapter.py.
**Interface:** assemble_facts(reader: HostReader, declarations: DeclaredFacts)->ParseResult.
- [ ] Rot: test_session_gate_precedes_gui_and_total_budget_precedes_next_read.
- [ ] Rot: test_missing_client_completeness_or_declaration_returns_no_facts;
  client_inventory_unverified/declaration_missing, value=None.
- [ ] Rot: test_any_source_failure_or_second_snapshot_change_discards_everything.
- [ ] Rotgrund: fehlender Gate-/Atomaritätsvertrag würde Teilfacts oder
  unbewiesene false-Werte an den Collector reichen.
- [ ] Minimal: feste Reihenfolge, eigene Session vor B5/B6, zwei Konsistenzaufnahmen,
  Budget und neun exakte Schlüssel; kein automatischer weiterer Versuch.
- [ ] Prüfen: test_hybrid_display_adapter mit Fixtures und Callreihenfolge.
**Abbruch:** geänderte Owner/EDID, unvollständige Clientquelle, unbekannte Flags.
**Verboten:** native Backendinstanz als Testdefault, Preflight-/CLI-Aufruf, unknown=false.

### 9. Übergabe an unveränderten Collector

**Dateien:** P/adapter.py; T/test_hybrid_display_adapter.py.
**Interface:** read_inventory(reader: HostReader, declarations: DeclaredFacts)->AdapterResult.
- [ ] Rot: test_exact_nine_facts_and_detached_collector_snapshot_only_on_success;
  tatsächlichen Collector aufrufen, keine Collector-Mockassertion als Ersatz.
- [ ] Rot: test_collection_is_not_preflight_or_wayland_option_permission.
- [ ] Rotgrund: Zusatzfelder, Aliase oder missverstandene Capability würden
  durchgeschleust oder als Startfreigabe ausgegeben.
- [ ] Minimal: assemble_facts-Erfolg genau einmal an collect_snapshot; dessen
  Fehler atomar als collector_blocked, nie Rohsnapshot-/Fehlerdump.
- [ ] Prüfen: Adapter- und vollständige Collector-Tests, dann Display-Fixtures.
**Abbruch:** notwendige Collector-/Modelländerung; dafür fehlt Freigabe.
**Verboten:** Gamingrolle wählen, WaylandSupport automatisch setzen, Runner starten.

### 10. Safety-/Classifier-Vertragsmigration

**Dateien:** gezielte spätere Änderung T/test_hybrid_display_safety.py und
prototype/hybrid-display/README.md; neue T/test_hybrid_display_reader_safety.py.
**Unverändert:** scripts/classify-container-changes.py,
T/test_container_workflow_policy.py und alle anderen bestehenden Testdateien.
- [ ] Rot: test_core_host_import_still_forbidden_and_adapter_exact_source_allowed.
- [ ] Rot: test_adapter_exception_cannot_hide_write_network_autostart_or_import_io.
- [ ] Rot: test_adapter_module_alias_dynamic_call_and_neighbor_path_rejected.
- [ ] Rot: test_readme_describes_reader_without_live_launcher_or_acceptance.
- [ ] Rotgrund: bisheriger globaler Checker kennt keine begrenzte Readerklasse;
  neue negative Fixtures müssen eine unerlaubte Ausnahme tatsächlich erkennen.
- [ ] Minimal: separater Adapterchecker nur für linux_reader.py,
  bestehender Kernchecker unverändert; exakte Scannerzuordnung und nur
  no_os_adapter-Abwesenheitstest durch engeren Vorhandenseinsvertrag ersetzen.
  Alle übrigen Safetytests/Fixtures unverändert erhalten.
- [ ] Prüfen: neue Readersafety, bestehende Safety, sämtliche Displaytests;
  Build-Provenance/Policy und volle Discovery nur nach passender Testfreigabe.
  H-/H+E-Tests-only und G-fail-closed mit bestehenden Policytests bestätigen.
**Abbruch:** blanket ignore, abgeschwächter Negativtest, Build-/Releaseänderung.
**Verboten:** Workflowstart, Klassifizierungslockerung, Import-/Startintegration.
Nach positiver Migration zuerst den nativen Teil aus Stufe 7 separat prüfen.
Ein grüner statischer Checker ersetzt die injizierten Verhaltensprüfungen nicht.

### 11. Erst danach: separat autorisierte Live-Diagnose

**Dateien:** keine Produktänderung. Ein neues Protokollziel benötigt eigene
Freigabe; keine automatische neue Datei aus dieser Planung.
- [ ] Vorab prüfen: Zielprofil, IPC-Binding, Kerneldeadline und
  Clientvollständigkeitsbeleg sind einzeln nachgewiesen. Fehlt ein Gate:
  BLOCKED, keine Live-Erhebung und kein Snapshot-Erfolg.
- [ ] Neue Freigabe muss konkrete Maschine, eigene lokale Sitzung, Quellen,
  Aufrufzahl, Limits, Datenschutz und Abbruch festlegen.
- [ ] Erster Live-Test ausschließlich lesend; keine Client-/GUIstarts,
  Display-/Dienst-/Sitzungs-/Pluginänderungen, keine Exporte/Caches.
- [ ] Beleg: tatsächliche feste Codes/Status, Grenzen ausdrücklich benennen.
  Fixturegrün ist weder Host- noch Hardwarebeleg.
- [ ] Rollback: nur eigene Handles schließen, Speicher verwerfen;
  keine Zustandsänderung erforderlich. Andernfalls verletzt, stoppen und
  manuellen Bedarf melden, keine Recovery durchführen.
**Rotgrund:** in Stufen 7–9 bereits testbar: Livegate ohne Beleg muss blockieren.
Kein absichtlicher realer Systemfehler als Rotnachweis.
**Verboten:** Gamescope, Steam, vkcube, Signale, Retry, Builds, Workflows.

## Heutiger Abschluss und spätere Übergabe

Heute ausschließlich zwei neue Dokumente, Index leer, keine bestehenden Dateien
geändert. Ungestagter Patch gegen den exakten Ausgangscommit, Größen-/SHA-256-
Beleg, statische Inhalts-/Link-/Whitespaceprüfung und unabhängiger lesender Review.
Keine Tests, Produktimplementierung oder Live-Erhebung im Dokumentationsauftrag.
Spätere Umsetzung benötigt ausdrückliche Zustimmung zu Pfaden, Testnebenwirkungen
und der gezielten Safety-Migration; Live-Diagnose bleibt davon getrennt.
