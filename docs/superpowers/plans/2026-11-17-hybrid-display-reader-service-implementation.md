# Hybrid-Display Reader-Service Implementation Plan

> Für später ausdrücklich freigegebene Umsetzung: superpowers:executing-plans
> oder superpowers:subagent-driven-development taskweise verwenden. Dieser Plan
> erteilt keine Ausführungs-, Installations-, Build-, Live- oder Gitfreigabe.

**Goal:** Einen einzigen isolierten, fail-closed IPC-Reader mit festem Socket
vorbereiten, ohne einen generischen Helper oder Collector-/Startpfad einzuführen.

**Architecture:** Ein reiner Codec und ein enger Socketclient kommunizieren mit
festem systemd-User-Service. Native Readerquellen bleiben prozessisoliert und
atomar; reine Foundation, Collector und Preflight bleiben getrennt.

**Tech Stack:** Python/unittest mit injizierten In-Memory-Doubles; später native
Runtime und systemd nach separater Dependency-/Sandboxfreigabe, keine neue
D-Bus-Wireparserimplementierung. Konkrete native Bibliothek noch nicht ausgewählt.

**Spec:** [ADR](../specs/2026-11-17-hybrid-display-reader-service-adr.md) und
[vollständiger Sicherheitsvertrag](../specs/2026-11-17-hybrid-display-reader-service-security.md).

## Global Constraints

- Heute ausschließlich drei Markdowndateien, kein Code, Unit, Installer oder Testlauf.
- Ein Service/eine Socketunit, Accept=no, fester Pfad, keine argv/Shell/subprocess.
- Version1, Header16 B, Request4096 B, Response262144 B, ein CAPTURE_IPC je Verbindung.
- Hauptprozess5s, Reader4s, Header100ms, Request/Send250ms; absolute monotone Fristen.
- MemoryMax64M, TasksMax1, CPUQuota25%, keine Schreibpfade/Geräte/Netzfamilien.
- Quellenlimits, maximal110 Reader-Transaktionen, atomare Fehler, feste Codes.
- Keine automatic Gate-/KScreen-Profilfreigabe oder Host-/Hardwarebehauptung.
- Keine neuen Commits/PRs/Workflows als Planstandard; jede Gitaktion separat freigeben.

## Review Focus

- SO_PEERCRED an socketaktiviertem Listener kann Manager statt Reader attestieren:
  Aufgabe2 muss falsche Binary-/PIDbehauptung verhindern.
- Same-UID/kompromittierter Reader besitzt ohne Busmediation noch Methodenautorität:
  Aufgabe1 lässt diesen Entscheidungsblocker nicht durch Unitoptionen verschwinden.
- ProtectHome/RootDirectory/PrivateTmp/Usernamespaces können Bus/Schreibschutz
  beeinflussen: Aufgaben1 und6 müssen Wirkung und Verweigerung statt Fallback prüfen.
- Slowloris, Restzeitabrundung und EOF nach formal korrekter Antwort: Aufgaben2/3.
- Neues natives Artefakt darf Python-Safety-/Releasechecks nicht still umgehen:
  Aufgaben4/5/6 halten exakte Dateizuordnung und Negativnachbarn fest.

## Geplante spätere Dateiverantwortung

Alle folgenden Pfade sind **Plan**, keine heutige Dateifreigabe:

| Pfad | Verantwortung |
|---|---|
| prototype/hybrid-display/src/hybrid_display/reader_service_protocol.py | reiner Header-/Recordcodec, DTOs, feste Codetabelle |
| prototype/hybrid-display/src/hybrid_display/reader_service_client.py | einzige zukünftige native Client-Socketgrenze mit injizierten Primitiven |
| prototype/hybrid-display/native-reader/reader.c | fester Prozesseinstieg, Deadline und Identität, keine Launcherfunktion |
| prototype/hybrid-display/native-reader/source_policy.c | geschlossene B0–B6-Zustands-/Methodenpolicy |
| prototype/hybrid-display/native-reader/transport.c | ausgewählte native Library-/Message-/Allocatorgrenze |
| prototype/hybrid-display/native-reader/reader.h | feste interne POD-/Fake-ABI, Ownership und endliche Statuswerte |
| prototype/hybrid-display/packaging/units/hybrid-display-reader-v1.service | späterer exakter Servicevertrag |
| prototype/hybrid-display/packaging/units/hybrid-display-reader-v1.socket | späterer exakter Listenervertrag |
| tests/test_hybrid_display_reader_service_protocol.py | reine Protokoll-/Ressourcentests |
| tests/test_hybrid_display_reader_service_client.py | injizierter Socket-/Clock-/Peer-/Ancillarytest |
| tests/test_hybrid_display_reader_service_safety.py | exakte Native-/Unit-/Checkerzuordnung mit synthetischen Fixtures |
| tests/native/hybrid_display_reader/ | spätere native Fake-ABI-/Lifetime-/Faulttests, eigener freizugebender Scope |

Build-/Loader-/Packagingformat und dazugehörige neue Dateien werden erst nach
Aufgabe1 in einem konkret genehmigten Scope ergänzt, nicht aus dieser Tabelle
automatisch abgeleitet. Keine Modifikation bestehender Build-/Releaseeingaben.

## Einheitlicher TDD-Ablauf je Aufgabe

- [ ] Testfall mit fachlichen Assertions schreiben; Import-/Syntaxfehler nicht als Rot zählen.
- [ ] Nur benannte vollständige unittest-Adresse/Fake-ABI-Fall ausführen und Rotgrund festhalten.
- [ ] Minimale Umsetzung, identische Assertions grün; keine Livequelle als Default.
- [ ] Unabhängigen Diff einschließlich neuer Dateien prüfen und betroffene Regression ausführen.
- [ ] Bei unklarer Erwartung, neuem Pfad oder Sicherheitswiderspruch Scope klären;
      Harnessadressierung/-Assertionreihenfolge minimal korrigieren, nicht Erwartungen lockern.

### Aufgabe1: Umsetzungsfähigkeit als explizites Gate

**Dateien:** zunächst nur getrennt genehmigte Ergänzung dieses Entwurfs.
**Ergebnis:** festes Runtime-/BOM-/Syscall-/Packagingprofil und dokumentiertes
Bedrohungsmodell, noch keine Unitaktivierung.

- [ ] Offene AUTH-/FD-Konfiguration, Timer-/Seccompverträglichkeit und opaque
      Callabbruch für die konkrete Runtime entscheiden. Kein Default-libdbus-Erfolg annehmen.
- [ ] Controllerdelegation/Usernamespaces/Busalias-/read-only-tmp-Bedingungen als
      positive und negative synthetische Konfigurationen spezifizieren.
- [ ] Same-UID- und mutierende Busmethoden-Restgrenze explizit akzeptieren lassen
      oder separat freigegebene Bus-/MAC-Mediation entwerfen; keine implizite zweite Helperkomponente.
- [ ] Rotfall `test_missing_enforcement_evidence_blocks_deployment`: bloße
      Unitoptionen/Versionsnummer liefern keine Native-/Deploymentfreigabe.
- [ ] Minimaler Reviewnachweis ergänzt fehlende Belege, niemals ein Overridebit
      im späteren Clientrequest. Ohne Ergebnis hier nur reine Aufgaben2/3 erlaubt.

### Aufgabe2: Codec und Peer-/Slowlorisgrenze

**Dateien:** reader_service_protocol.py und Protokolltest.
**Interface:** `decode_request(frame: bytes)` und
`decode_response(frame: bytes) -> IpcCaptureResult`; exakte immutable DTOs,
kein Snapshot und keine seiteneffektbehafteten Objekte.

- [ ] Rotfälle: `test_prefix_rejects_oversize_before_body_allocation`,
      `test_version_type_id_count_and_trailing_bytes_are_closed`,
      `test_unknown_reason_and_subclass_callbacks_never_escape`,
      `test_no_generic_paths_commands_gate_flags_or_profile_overrides`,
      `test_kscreen_failure_codes_19_20_preserve_existing_reasons`.
- [ ] Minimal: exakt v1-Header, Clientliste, feste Recordreihenfolge/-grenzen und
      Codemapping; keine generische JSON-/Pickle-Dekodierung vor Limits.
- [ ] Gleiches Modul grün; `test_blocked_has_no_capture_records` und
      `test_fixture_profile_never_becomes_live_compatibility` grün.

### Aufgabe3: Einmaliger begrenzter Socketclient

**Dateien:** reader_service_client.py und Clienttest.
**Interface:** `capture_ipc(declared_client_pids, io, clock) -> IpcCaptureResult`;
`io` ist vollständig injiziert (Socketlookup/connect/peer/recvmsg/send/shutdown/close),
keine implizite native Instanz beim Import oder in Tests.

- [ ] Rotfälle: `test_only_fixed_unix_socket_and_own_uid_allowed`,
      `test_socket_activation_peer_is_not_claimed_as_reader_pid`,
      `test_absolute_deadline_includes_connect_header_body_eof_and_decode`,
      `test_slowloris_partial_send_and_extra_frame_never_reset_budget`,
      `test_scm_rights_and_ctrunc_close_owned_fds_and_block`,
      `test_crash_disconnect_and_invalid_response_return_no_partial_data`,
      `test_complete_valid_frame_and_eof_is_commit_not_service_health`.
- [ ] Minimal: ein Connect, kein Spawn/StartUnit, vollständiger Request plus
      SHUT_WR, begrenzte Antwort/EOFprüfung, Cleanup bei jedem Fehler.
- [ ] Grün ohne echte Sockets; gezielter Negativtest SSH-/Managerkontext führt
      nicht zu grafischer Bindungsbehauptung. Kein automatischer Retry.

### Aufgabe4: Native Policy/Lifetime unter Fake-ABI

**Dateien:** native-reader/{reader.c,source_policy.c,transport.c,reader.h} und
separat freizugebende tests/native/hybrid_display_reader/.
**Interface:** versionierte nativeigene POD-/Status-/Funktionstabelle, keine
Pythonobjekte, keine Exceptions oder Rawwerte über eine ABI.

- [ ] Erst nach Aufgabe1/konkreter Build-Testfreigabe Assertion-Rotfälle für
      acquire/send/pending/receive/cancel/close/unref und jedes Faultinjektionsloch.
- [ ] Rotfälle für fehlende/wechselnde Owner, Peer-/Owner-UID/PID/Sessionabweichung,
      falsche Signatur/Serial,16/17 Outputs,32/33 unerwartete Messages,64-KiB-Grenze,
      beide Captures/Restbytebudget, AUTH-/FD-Policy und vollständig atomare Ausgabe.
- [ ] Minimal: feste B0–B6-Tabelle, kein DBus-Introspect/Listing/Autostart;
      Library nur durch eigene geprüfte Funktionsgrenze, begrenzte Projektion.
- [ ] Eigener Timer/Managerabbruch nur im Readerkontext, keine fremden PID-/Signalziele;
      Fakeclock und -timer prüfen späten Connect/Auth/Allocator ohne echten Bus.
- [ ] Grün mit Fake-ABI plus eigener tatsächlicher nativer Ressourcenprüfung
      unter neuer Testfreigabe. Mocks allein belegen keine Library-/Kernelgrenze.

### Aufgabe5: Safety-Migration vor nativer Freigabe

**Dateien:** neue Readerservicetests; später exakt benannte Stellen in
`tests/test_hybrid_display_safety.py` und `prototype/hybrid-display/README.md`.

- [ ] Rotfixtures vor Checkeränderung: exakt erlaubter Socketclient wird noch
      abgewiesen; Nachbarpfade, Wrapperbefehle, Templates, freie Execs und C-Fremdcode bleiben verboten.
- [ ] Enger Checker nur für exakte Clientdatei; bisherige pure-core-Prüfung für
      jedes bisherige Produktmodul unverändert weiter anwenden.
- [ ] Exakte Unit-/Artefaktzuordnung mit negativen Nachbarn, kein blanket ignore.
      Reject-command-Tests und subprocess-/signal-Verbote im Hauptprozess unverändert.
- [ ] Native Source-/ABI-/Privacyregeln getrennt vom Python-AST prüfen.
- [ ] README nur im freigegebenen Native-Milestone ehrlich präzisieren. Kein
      Collector-/Preflight-/CLI-/Runnerumbau oder Classifierlockerung.

### Aufgabe6: Unit-/Packagingentwurf, Vollzugsnachweis getrennt

**Dateien:** erst nach expliziter zusätzlicher Freigabe die zwei exakten Units,
festgelegte Build-/BOM-Dateien und zugeordnete Safetytests.

- [ ] Rotfixtures `test_private_network_required_and_no_host_abstract_reachability_claim`
      sowie für jede fehlende Mindesthärtung, fremden Busbind, beschreibbares
      tmp, geändertes ExecStart/Argument, Restartschleife und Accept=yes/Template.
- [ ] Minimale deklarative Units gemäß Matrix; kein Hoststart zum Grünmachen.
- [ ] Statische grüne Regeln belegen nur Unitinhalt. Separat autorisierter
      isolierter Wirkungsnachweis muss Namespaces, UID-Abbildung, Controller,
      Seccomp, echte Schreib-/Device-/Familienverbote, Unzugänglichkeit von
      Host-Abstract-Sockets und positive Erreichbarkeit beider festen
      Dateisystem-Busaliase bestätigen. Keine Socket-Negativprobe heute ausführen.
- [ ] Reproduzierbare Nativeartefakte und gepinnter Ziel-BOM separat belegen;
      keine Container-/ISO-/Releaseaktion aus dieser Aufgabe ableiten.
- [ ] Kein Install/Enable/Start durch Produktclient, Tests oder Import.

### Aufgabe7: Spätere Integration und Plasma-Liveabnahme, neuer Auftrag

- [ ] IPC-Daten bleiben private DTOs; keine Facts oder Auswahl beim Empfang.
      Adapterhandoff erst nach allen notwendigen Gatebelegen separat planen.
- [ ] Clientvollständigkeit und DRM-Deadlines werden durch die neue Architektur
      nicht gelöst. Der alte generische HostReader bekommt keinen Erfolgsoverride.
- [ ] Eigene lokale Plasma-Ausführung, Peer-/Owner-/Logindbindung und reales
      Profil separat bestätigen; SSH bleibt unzureichend für eigene GUIbindung.
- [ ] Keine Display-/Dienst-/Session-/Pluginaktion, Steam-/Gamescopestart oder
      Hardwarevalidierung; kein Aktivieren dieses Dienstes ohne konkrete Freigabe.

## Abschlusskriterium und heutige Übergabe

Vor jeder späteren Fertigmeldung: gültige Rot→Grün-Belege, eindeutige Testzahlen,
vollständiger Diff/neue Dateien, native Privacy-/Ressourcenbelege, unabhängiger
Review, tatsächlicher Sandboxvollzug und unveränderte andere Gates. Keine
vorweggenommene Testzahl oder Native-/Hostbehauptung. Heute nur Dokumente und
ungestagter Review-Patch; keine Commit-/Push-/PR-/Workflowaktion.
