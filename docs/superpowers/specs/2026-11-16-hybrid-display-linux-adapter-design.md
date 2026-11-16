# Streng lesender Linux-Hostadapter: Entwurf

Datum: 2026-11-16. Status: Dokumentationsentwurf, keine Implementierungs- oder
Live-Freigabe. Basis: `664047789e099a9f2c2371972225fcff304be706`,
Branch `feature/hybrid-display-linux-adapter`.

## Auftrag, Quellen und Architekturentscheidung

Nur dieses Dokument und der [Implementierungsplan](../plans/2026-11-16-hybrid-display-linux-adapter-implementation.md)
werden neu angelegt. Bestehende Verträge bleiben unverändert. Dieser Entwurf
erteilt weder Testausführung noch Hostzugriff, Installation, Git-Veröffentlichung,
Workflow, Start eines Clients oder Hardwareabnahme.

Verbindliche Quellen: [AGENTS](../../../AGENTS.md), [Sicherheitsgrenzen](../../agent-guidance/safety-boundaries.md),
[Hardwarebaselines](../../agent-guidance/hardware-baselines.md), [MVP-Design](2026-11-15-hybrid-display-mvp-design.md),
[alter Plan](../plans/2026-11-15-hybrid-display-mvp-implementation.md),
[README](../../../prototype/hybrid-display/README.md), alle neun vorhandenen
Bibliotheksmodule, alle acht Hybrid-Display-Testdateien, Classifier und Policytests.
Der alte Plan beschreibt teilweise inzwischen überholte Schnittstellen; der
Quellstand an obiger Basis ist für die reine Bibliothek maßgeblich.

Collector aus PR #10: ursprünglicher Commit
`86bb46c613e84aae296ffc40c5b23c7d61eb7ddf`, Korrektur
`f286cc906ae654e12f267a0bb4ab9269495f4637`; Merge hat Eltern
`83a3858ef4b8df939ffacbadc28ca04fcfda4567` und `f286cc906ae654e12f267a0bb4ab9269495f4637`.
PR-Diff und beide Commits sind gelesen. Die Metaklassenkorrektur bleibt erhalten.

Betrachtete Wege:

1. Befehlswrapper um loginctl/kscreen-doctor: verworfen. GUI-Hilfsprogramme können
   abstürzen/Core-Dumps erzeugen; ein hart begrenzter Kindprozess benötigt im
   Fehlerfall gewöhnlich Signale. Das widerspricht hier dem Signalverbot.
2. Gespeicherte KWin-Konfiguration als Laufzeitbeleg: verworfen. Sie belegt
   weder die aktuelle Sitzung noch aktuelle aktive Ausgänge.
3. Gewählt als Entwurfsentscheidung: kleiner expliziter HostReader mit nativen,
   begrenzten lokalen D-Bus-Leseaufrufen und einzeln freigegebenen Dateiquellen.
   Kein Befehlsstart. Fehlende vorhandene Dienste bedeuten BLOCKED, kein Autostart.
   Die unten benannten Kompatibilitäts- und Transportgates bleiben vor Live-Nutzung offen.

Keine Aussage über die Machbarkeit des langfristigen direkten Gaming Modes.
Nested bleibt ein begrenztes Entwicklungs-MVP. Dell und HP/Build #4 bleiben
getrennte Hardwarebelege; keine historischen Connectoren oder Sitzungsnummern
werden als aktuelle Werte übernommen.

## Schichten und Datenfluss

```text
Linux-Backend -> rohe begrenzte Werte -> reine Parser -> Facts
             -> collect_snapshot -> SessionSnapshot -> späterer Preflight
```

- `collect.py`, Modelle, Resolver und Preflight bleiben rein und unverändert.
- Parser erhalten ausschließlich exakte Built-in-bytes beziehungsweise geprüfte,
  abgetrennte DTOs; keine I/O-, Umgebungs-, D-Bus- oder Logzugriffe.
- HostReader deklariert ausschließlich `read_env(key)`, `read_file(SourceKey)`
  und `query(QueryKey)`. SourceKey/QueryKey sind geschlossene Enums plus geprüfte
  numerische/kanonische Parameter, keine frei wählbaren Pfade oder Methodennamen.
- Nur `linux_reader.py` besitzt Hostrechte. Transport wird injiziert; kein
  Import oder Konstruktor erhebt Daten. Eine spätere explizite `read_inventory`
  ist die einzige Orchestrierungsoperation, synchron und ohne Hintergrundarbeit.
- CLI, LaunchPlan, Lifecycle, ProcessAdapter, Gamescope, Hardwaretest und Export
  sind keine Abhängigkeiten des Readers. Insbesondere kein Runner-Import.
- Geometrie, Maßstab, Herkunft und Konsistenzmarker verbleiben in einem privaten
  Adapter-DTO. Keine zusätzlichen Schlüssel in den neun Collector-Facts.

## Exakte Quellen-Allowlist

Die Tabellen sind abschließend; nicht genannte Quellen sind verboten.
Alle Limits sind konservative Entwurfspolitik, keine gemessenen Systemgrenzen.
Gesamtdauer einer Collection höchstens 5 Sekunden, gesamte rohe Nutzlast höchstens
262144 Bytes einschließlich der zweiten Konsistenzaufnahme. Pro Operation gilt
zusätzlich das Tabellenlimit, begrenzt durch die verbleibende Gesamtfrist.
Limits werden vor Allokation/Dekodierung erzwungen. Keine automatischen Retries.

### Eigene Prozessidentität und Umgebung

Nur Kernelprimitiven für effektive/reale UID, eigene PID und monotone Zeit.
UID 0, unterschiedliche reale/effektive UID oder privilegierte Ausführung blockieren.
Keine Gruppen-/Benutzerdatenbank, kein HOME, kein PATH, keine vollständige Umgebung.

| Schlüssel | Format / Bytes maximal | Frist | Fehlercode | Verwendung / Datenschutz |
|---|---|---|---|---|
| XDG_SESSION_ID | ASCII `[A-Za-z0-9]{1,32}`, 32 | 50 ms | session_context_invalid | nur Vergleich mit Logind, nie Beweis oder Ausgabe |
| XDG_SESSION_TYPE | exakt wayland/x11/tty, 16 | 50 ms | session_context_invalid | Widerspruch zu Logind blockiert |
| XDG_CURRENT_DESKTOP | exakt KDE/plasma/Plasma, 16 | 50 ms | session_context_invalid | keine Teilstring-/Prefixannahme |
| XDG_RUNTIME_DIR | exakt `/run/user/<eigene UID>`, 64 | 50 ms | session_context_invalid | aus eigener Umgebung; prüfen, nicht ersetzen |
| DBUS_SESSION_BUS_ADDRESS | exakt `unix:path=/run/user/<eigene UID>/bus`, 96 | 50 ms | session_bus_invalid | kein TCP, abstract, guid, Fallback oder Autolaunch |

Nur diese fünf Namen gezielt lesen, nicht erst os.environ kopieren/iterieren.
Keine WAYLAND_DISPLAY-/DISPLAY-Erhebung: Reader verbindet keinen Grafikclient.
Fehlende Werte werden nicht erraten. Eine andere legitime Busadressschreibweise
ist außerhalb dieses ersten Profils und blockiert statt still normalisiert zu werden.

### Lokale IPC-Quellen

Keine Netzwerkverbindung. Nur AF_UNIX am überprüften eigenen Sessionbus und
`/run/dbus/system_bus_socket`; keine weiteren Sockets. Systembus-Peer UID 0,
Sessionbus-Peer eigene UID; Sockettyp und Runtime-Verzeichnisbesitz/Modus prüfen.
Keine Introspection, ListNames, ListUnits, ListProcesses, Watches oder Abonnements.
Alle Anfragen ohne Autostart an zuvor aufgelöste eindeutige Owner, außer den
Leseaufrufen an den Busdaemon selbst. Kein Set, keine D-Bus-Signale senden.

| ID | Bus, Ziel, Objekt, Interface, Operation | Rückgabe / Limit | Frist | Fehlercode / Datenschutz |
|---|---|---|---|---|
| B0 | beide; org.freedesktop.DBus; /org/freedesktop/DBus; org.freedesktop.DBus; Hello() genau einmal pro Verbindung | unique name, 128 Bytes | 250 ms | ipc_invalid; nur flüchtige Verbindung, keine Namensreservierung |
| B1 | beide; org.freedesktop.DBus; /org/freedesktop/DBus; org.freedesktop.DBus; GetNameOwner(name) | unique name, 128 Bytes | 250 ms | owner_missing; Name nur intern |
| B2 | beide; gleiches Busdaemonobjekt; GetConnectionUnixUser(owner), GetConnectionUnixProcessID(owner) | jeweils uint32, je 128 Bytes | je 250 ms | owner_invalid; UID/PID nie Bericht |
| B3 | System; org.freedesktop.login1; /org/freedesktop/login1; org.freedesktop.login1.Manager; GetSessionByPID(pid) | Objektpfad, 256 Bytes | 250 ms | session_unverified; kein Fallback auf eine andere Sitzung |
| B4 | System; durch B3 belegtes Sessionobjekt; org.freedesktop.DBus.Properties; Get(org.freedesktop.login1.Session, property) | feste Properties unten, zusammen 4096 Bytes | zusammen 500 ms | session_unverified; keine Namen/Pfade ausgeben |
| B5 | Session; org.kde.KScreen; /backend; org.kde.KScreen.Backend; getConfig() | a{sv}, 65536 Bytes | 500 ms | kscreen_unavailable oder kscreen_schema_invalid; Rohmap privat |
| B6 | Session; gleicher Owner/Objekt/Interface; getEdid(output_id) | ay, 4096 Bytes pro Output | je 100 ms | edid_invalid; sofort intern hashen, nie ausgeben |

Bootstrap vor B0: nur SASL AUTH EXTERNAL mit der eigenen UID, danach BEGIN;
keine andere Identität, kein Cookie-/Dateizugriff, keine Unix-FD-Aushandlung.
Authentisierungsantwort höchstens 4096 Bytes/250 ms. RequestName, AddMatch,
StartServiceByName und weitere Bootstrapmethoden bleiben verboten. Hello legt
nur den flüchtigen Verbindungsnamen an; keine Dienste/Settings werden verändert.
Verbindungen werden am Ende geschlossen, kein persistenter Busclient.

B1 zulässige name-Argumente: am Systembus nur `org.freedesktop.login1`;
am Sessionbus nur `org.kde.KWin` und `org.kde.KScreen`. B2 nur deren B1-Owner.
B3 nur eigene PID, die beiden belegten Owner-PIDs und maximal 16 explizit
deklarierte Client-PIDs. Kein allgemeines PID-/Sitzungsinventar.
B4 Properties exakt: Id, User, Type, Desktop, Remote, Active, Class, State.
Id ASCII wie oben; User ist (uint32, object path) mit eigener UID; Type=wayland,
Desktop aus obiger Menge; Remote=false, Active=true, Class=user, State=active.
Andere Werte sind ein bekannter negativer Sitzungskontext und blockieren dieses
Live-Readerprofil vor jeder KScreen-Abfrage. Collector selbst darf weiterhin
negative synthetische Fakten übersetzen. KWin- und KScreen-Owner müssen zur
gleichen bestätigten eigenen Session gehören; keine fremde Sitzung übernehmen.

KScreen-Protokoll ist ausdrücklich ein **versionsgebundenes Profil**, keine
Behauptung über die vorhandene Maschine. Primärquellen:
[KDE libkscreen v6.3.5 Wrapper](https://github.com/KDE/libkscreen/blob/v6.3.5/src/backendlauncher/backenddbuswrapper.h),
[Implementierung](https://github.com/KDE/libkscreen/blob/v6.3.5/src/backendlauncher/backenddbuswrapper.cpp),
[Serializer](https://github.com/KDE/libkscreen/blob/v6.3.5/src/configserializer.cpp).
Sie belegen /backend, getConfig/getEdid und die Mapstruktur. Der gelesene
[aktuelle Serializer](https://github.com/KDE/libkscreen/blob/master/src/configserializer.cpp)
zeigt bereits Formatunterschiede, etwa optionales enabled. Daher keine pauschale
Kompatibilitätsbehauptung für historisches Plasma/KScreen 6.8.2.
Vor Backendimplementierung muss ein exakt benanntes Zielversionsprofil statisch
an Primärquellen und synthetischen Fixtures bestätigt werden. Fehlt dieses:
`kscreen_profile_unverified`, kein Live-KScreenzugriff. Kein probeweises Introspecting.

B5 Pflichtprojektion: outputs mit id, name, connected, enabled, pos{x,y},
size{width,height}, scale, rotation, clones, replicationSource, currentModeId,
modes mit id/size/refreshRate. Höchstens 16 Outputs, 128 Modes pro Output,
16 Clone-IDs, Tiefe 8, 64 Schlüssel pro Map, 128 UTF-8-Bytes pro Skalarstring.
Unbekannte begrenzte Metadaten werden im Decoder verworfen, nie rekursiv gerendert.
Fehlendes enabled bleibt unbekannt, nicht automatisch true. Doppelte Mapkeys,
ungültige Signaturen, NaN/Inf, bool als Zahl oder Größenüberschreitung blockieren.
Die Versionsbestätigung muss diese konkrete Projektion und Semantik abdecken.

### Dateien und Pfadparameter

Kein Verzeichnislisting. Der Aufrufer liefert ein explizites `ConnectorManifest`
mit höchstens 16 Paaren (card_index, connector) und deklarierter Vollständigkeit.
card_index: exakter int 0..15, kein bool. Connector entspricht exakt dem bestehenden
Collector-CONNECTOR-Muster und höchstens 24 ASCII-Bytes. Keine Historienvorgabe.
Unvollständige/ungeprüfte Inventare blockieren; KScreen muss jeden verbundenen
Ausgang genau einmal dem Manifest zuordnen.

| SourceKey | einzig zulässiger Pfad | Format / Limit | Frist | Fehlercode / Datenschutz |
|---|---|---|---|---|
| DRM_STATUS | /sys/class/drm/card<N>-<connector>/status | connected/disconnected plus LF; 16 Bytes | 100 ms | drm_status_invalid; keine Pfadausgabe |
| DRM_ENABLED | /sys/class/drm/card<N>-<connector>/enabled | enabled/disabled plus LF; 16 Bytes | 100 ms | drm_enabled_invalid; nicht mit connected verwechseln |
| DRM_EDID | /sys/class/drm/card<N>-<connector>/edid | binär 0..4096 Bytes | 100 ms | edid_invalid; keine Ausgabe der Bytes |
| DRM_DEVICE_LINK | /sys/class/drm/card<N>/device | kontrollierter Symlink, Zieltext höchstens 1024 Bytes | 100 ms | drm_device_invalid; PCI-Adresse nur intern |
| PROCESS_STAT | /proc/<PID>/stat | genau ein Stat-Datensatz, 4096 Bytes | 100 ms | process_identity_unverified; nur comm/starttime intern |
| PROCESS_STATUS | /proc/<PID>/status | begrenzte ASCII-Felder, 8192 Bytes | 100 ms | process_identity_unverified; ausschließlich Uid projizieren |

PID exakter int 1..2147483647; nur eigene PID, KWin-/KScreen-Owner oder deklarierte
Client-PIDs nach B3. Keine /proc-Enumeration, cmdline, environ, exe oder fd-Liste.
comm im stat-Datensatz nicht naiv an Leerzeichen trennen; schließende Klammern
im Namen berücksichtigen, feste Feldanzahl und starttime validieren.
Clientnamen exakt gamescope, steam, vkcube; Wrapper/Umbenennungen sind unbekannt.
Mehr als 16 Client-PIDs blockiert vor jedem Lesen. Ein bekannter Treffer genügt
für einen Konflikt; eine leere PIDliste beweist keine Prozessfreiheit.

### Deklarierte Eingaben, ausdrücklich keine gemessenen Hostfakten

`DeclaredFacts` enthält nur: ConnectorManifest, bekannte Client-PIDs,
`clients_complete`, `focus_service_active`, `decky_active`, `capabilities`,
`kscreen_profile`. Keine Pfade oder argv, keine beliebigen Metadaten.
Exakte unveränderliche DTOs und Built-ins, Prüfung durch Typidentität vor
Iteration, Länge, bool, Gleichheit oder repr. UID/Sessionbindung der Deklaration
ist erforderlich; keine persistierte Dateiquelle dafür.
capabilities ist eine explizite Teilmenge gamescope/steam/vkcube, höchstens drei;
keine Programmstarts, PATH-Suche oder automatische Optionsbehauptung.
focus_service_active und decky_active sind explizite bool-Deklarationen, nicht
durch diesen Reader gemessen; unknown blockiert statt false.

`clients_complete` ist keine verifizierbare Aussage über alle laufenden Prozesse.
Deshalb ist die erste Backendstufe **nicht berechtigt**, aus einer leeren oder
als vollständig bezeichneten Liste den gemessenen Wert existing_clients=()
abzuleiten. Ohne separat gelieferten, vertrauenswürdig bestätigten aktuellen
Vollständigkeitsbeleg bleibt `client_inventory_unverified` und snapshot=None.
Ein solcher Beleg hat in diesem ersten Profil bewusst **keine Hostquelle**.
Die reine Orchestrierung ist über Fixturebelege testbar; ein vollständiger
Live-Snapshot ist bis zu einem separat entworfenen Nachweisverfahren gesperrt.
Keine Prozesssuche hinzufügen, um diesen Sperrgrund zu umgehen. Auch manuelle
Deklarationen machen keinen Host- oder Preflight-Erfolg nachgewiesen.
Dies ist eine explizite Funktionsgrenze des ersten Entwicklungsabschnitts.

Erlaubte Befehls-argv: **leere Menge**. Befehlsadapterstufe im Plan ist eine
Negativgrenze mit Testdouble, kein subprocess-Backend. stdin/stdout/stderr,
shell=false, minimale Kindumgebung, Prozess-Timeout und Cleanup sind mangels
Kindprozessen nicht aktiv. Jede spätere nichtleere argv-Allowlist benötigt ein
eigenes Konzept einschließlich Signal-/Timeoutkonflikt und neue Freigabe.
Kein timeout-Wrapper, keine indirekte Shell, kein busctl/qdbus-Fallback.

## Sichere Dateiauflösung und zeitliche Konsistenz

Nur O_RDONLY, O_CLOEXEC, O_NOFOLLOW; bei geeigneten Dateien O_NONBLOCK.
Normale Dateien nur nach fstat als regulär und im erwarteten procfs/sysfs;
keine Geräte, FIFOs, fremden Mounts oder Schreibflags. Keine chmod/utime/xattr.
Benutzerpfade niemals entgegennehmen. Feste Segmente und Dezimalparameter,
keine Slash-, NUL-, Punkt-/Punktpunkt-Komponenten oder Prozentdekodierung.

Sysfs enthält legitime Links: einzig card<N>, card<N>-<connector> und card<N>/device
dürfen kontrolliert aufgelöst werden, nicht pauschal alle Symlinks erlauben.
Ziel muss nach höchstens 8 Hops/32 Komponenten unter /sys/devices innerhalb
einer PCI-Topologie liegen; letzte GPU-Komponente kanonische volle BDF, die
Ausgangskomponente muss zum Manifest passen. card<N>, dessen device-Link und
alle zugehörigen Connectorlinks müssen dieselbe kanonische PCI-GPU ergeben;
ein normaler card-Link ist erlaubt, ein ausgetauschter GPU-Link blockiert.
Kein /sys/kernel/debug und kein
Ausbruch über Mounts. Relative '..' aus **Kernel-Linkzielen** nur innerhalb
dieser kontrollierten Auflösung, nie aus Eingabeparametern. Unsupported
Platform-GPUs blockieren. Dateiende selbst nie Symlink.

Auflösung fd-relativ an fest geöffneten Wurzeln; Komponenten und Mount-/Inode-
Identität prüfen, nicht resolve()+späterer offener Pfad. Für proc-PIDs
starttime/UID vor und nach Lesezugriff vergleichen; verschwundene oder
wiederverwendete PID blockiert. Keine Signale, keine PID-Übernahme.
Fstat-Größe ist nur ein Hinweis (Sysfs häufig Größe 0): höchstens Limit+1
lesen, genau diese Zusatzbyteprüfung verhindert stille Kürzung.
Keine vollständige Datei vor dem Limit laden.

Deadline vor und nach jeder Operation prüfen, keine Threads/Signalsperren.
**Offenes Kernel-Gate:** O_NONBLOCK garantiert bei beliebigen procfs/sysfs-
Attributen keinen harten Wallclock-Abbruch eines bereits blockierenden
Kernelreads. Kein Timeout versprechen, den der Reader nicht erzwingen kann.
Vor Live-Dateilesen muss für exakt diese Attribute die benötigte
Nichtblockierungs-/Deadlineeigenschaft belegt sein; sonst `reader_deadline_unverified`
und kein Zugriff. Kein Hilfsprozess oder Signal als stiller Ausweg.

B1/B2/Session/Config/DRM/EDID werden in einer einzigen Collection zweimal
konsistent bestätigt (keine Retryschleife). Owner, Session, Outputprojektion,
Verbindungs-/Aktivflags und EDID-Digests müssen gleich bleiben. Änderung,
Hotplug, unlesbare Daten oder Fristablauf: `inventory_changed`, atomar ablehnen.
Das ist eine endliche Konsistenzkontrolle, kein atomarer Kernel-Snapshot und kein
Schutz gegen alle ABA-Wechsel. Vor späterem Start erneut separat prüfen.

## Parser, Zuordnung und Modellgrenzen

EDID: Header, Länge als Vielfaches von 128, Extensionanzahl und alle Checksummen
prüfen; höchstens 32 Blöcke. Leere EDID nur disconnected+disabled. Rohbytes nur
kurz im begrenzten Speicher; keine Serien-/Hersteller-/Modelltexte extrahieren.
Vollständiger SHA-256 ausschließlich intern zum Vergleich und als
OutputIdentity.edid_sha256; niemals in Berichten, repr oder Exceptions.
KScreen-getEdid-Hash und Sysfs-Hash plus eindeutiger kanonischer Connectorname
müssen genau eine Zuordnung ergeben. Keine bloße Namensgleichheit bei Multi-GPU,
kein Primärmonitor-Fallback; doppelte/fehlende Identitäten blockieren konservativ.
Disconnected Einträge ohne EDID dürfen nur durch eindeutigen kanonischen Namen
im Manifest zugeordnet werden; keine Gamingrolle daraus.

Intern benötigt das bestehende Modell den **vollen** Hash. Präfixe sind keine
Lookupschlüssel und dürfen ihn nicht ersetzen. Ausgabeseitig höchstens
`edid:` + 12 Kleinhexzeichen + `…`, Kollisionen als mehrdeutig markieren.
Keine Ausgabe ganzer Hashes, Seriennummern, Benutzerwerte, Pfade, Argumente
oder roher EDID. Auch repr(snapshot.outputs[0]) niemals verwenden: vorhandene
Output-repr enthält Adressen. Adapterresultat verbirgt sämtliche Payloads.

Geometrie: int x/y -32768..32767, int width/height 1..16384 für aktive Ausgänge,
finite scale 0.25..8 (bool ausgeschlossen); Rotation nur 1/2/4/8 im ersten Profil.
Logical rectangles aus bestätigter KScreen-Semantik, keine Rundungsheuristik.
clones nicht leer, replicationSource > 0 oder überlappende aktive logische
Rechtecke ergeben mirrored=true; uneindeutige Geometrie blockiert. Inaktive
Ausgänge dürfen fehlende Modedaten haben, werden nicht als aktiv geraten.
Skalierung/Geometrie dienen Prüfung und verbleiben privat, keine Modellerweiterung.
connected/enabled müssen zwischen KScreen und DRM übereinstimmen.

Facts exakt: session_type, desktop, own_local_session, kwin_running, outputs,
existing_clients, focus_service_active, decky_active, capabilities.
Output/OutputIdentity werden neu aufgebaut; manufacturer/model immer leer.
Maximal 16 Outputs/Clients, maximal drei Capabilities, vor Iteration begrenzen.
Die bestehenden Collector-Prüfungen einschließlich Metaklassenabwehr bleiben
zusätzliche Grenze. Erfolg ist nur Datenübersetzung. Gamingrolle bleibt None.
Warnung monitor_description_missing ist daher erwartbar; nichts erfinden.
WaylandSupport.SUPPORTED ist separat und wird aus Programmlabels nicht abgeleitet.

## Fehler, Datenschutz und Transportgrenzen

ReadResult/ParseResult/AdapterResult: eingefrorene Datenobjekte, Payload repr=False;
bei Fehler ausschließlich sortierte deduplizierte feste Codes und payload=None.
Geschlossene Codes aus Tabellen plus: source_not_allowed, input_invalid,
source_unavailable, source_denied, source_limit, source_timeout, source_type_invalid,
ipc_invalid, ipc_limit, inventory_changed, association_ambiguous,
declaration_missing, client_inventory_unverified, kscreen_profile_unverified,
reader_deadline_unverified, reader_failed, collector_blocked, command_not_allowed.
Keine Exceptiontexte/Tracebacks, Rohwerte oder generisches asdict/vars-Dumping.
Ein Erfassungsfehler liefert niemals Facts, Geometrie oder Teilsnapshot.
Keine automatische Übergabe an vorhandene Diagnostics: deren Codekatalog bleibt
unverändert. Öffentliche Zusammenfassung nur blocked/success und feste Codes;
optionale gekürzte Monitorlabels brauchen später einen separaten Formatter.

IPC-Empfang begrenzt Header+Body **vor** Dekodierung; je Message maximal 65536
Bytes, FD-Anhänge und fremde Antworten ablehnen, serielle Reply-Zuordnung,
höchstens 32 unerwartete Messages/32768 Bytes insgesamt, dann blockieren.
Authentisierung/Handshake höchstens 4096 Bytes/250 ms; keine unbeschränkten
Queues. Ein synchroner select/poll-Loop mit monotoner Frist, keine Threads.
Keine autostartenden Binding-Convenience-APIs oder automatische Reconnects.
Konkretes Binding und seine Ressourcenbegrenzung sind ein offenes Transportgate:
vor Linux-Backendimplementierung Dependency/Version statisch prüfen, benennen
und separat freigeben. Keine Paketinstallation aus diesem Dokument ableiten.

Verboten: Shellstrings, shell=true, sudo/root, sämtliche Schreibbefehle,
systemctl start/stop/enable/disable, KScreen-Set-/Konfigurationsaufrufe,
DRM-force/Hotplug, allgemeine /proc-Scans, rekursive /sys-Scans, Netzwerk,
Decky-/Pluginaktionen, alle Clientstarts, Signale, Hintergrundthreads,
unbeschränkte Ausgabe, automatische Repairs, Cache-/Exportdateien.
D-Bus-Methoden können serverseitig dennoch Implementierungsfehler haben.
Die Leseabsicht ist keine nachgewiesene Nebenwirkungsfreiheit; API- und
Versionsreview und gesonderte Live-Freigabe bleiben erforderlich.

## Sicherheitsvertragsmigration: erst später, separat freizugeben

Heute unveränderte Verbote:
`tests/test_hybrid_display_safety.py::product_violations` verbietet global
os/sys/subprocess/signal/socket/pathlib/io/dbus/systemd und weitere Hostimports,
open/read/write/Popen/kill sowie funktionale /sys/class/drm-/Hilfsprogrammreferenzen.
`RepositoryRegressionTests.test_product_is_pure_non_executable_and_separate_from_focus`
wendet dies auf jede Pythondatei unter dem Prototyp an.
`ReadmeContracts.test_no_os_adapter_boundary` und `readme_issues['no_os_adapter']`
verlangen ausdrücklich das Fehlen eines Betriebssystemadapters.
README und reine Modulverträge verbieten Erhebung beim Import und in den
Kernfunktionen. Der alte Plan erlaubt zukünftige Adapter nur nach neuer Freigabe.
AGENTS/Sicherheitsgrenzen erteilen selbst keine Ausführungserlaubnis.

Spätere eng begrenzte Migration, kein blanket ignore:

- Nur `linux_reader.py` erhält einen eigenen strikteren Source-/Call-Checker,
  der diese vollständige Allowlist, read-only Flags, keine Importsideeffects,
  keine dynamische Dispatchauflösung und keine unerlaubten Imports/Calls prüft.
  Alle übrigen Produktdateien bleiben im unveränderten Reinheitschecker.
  Pfadliterale und native Methoden liegen ausschließlich in linux_reader.py;
  reader_policy arbeitet nur mit Keys/Parametern und synthetischen
  Auflösungsmetadaten, niemals mit Hostpfaden oder echten offenen Handles.
- Nur die Repositorytest-Schleife zur Zuordnung an den speziellen Checker sowie
  die README-Abwesenheitsaussage werden gezielt präzisiert. README muss dann
  ehrlich den vorhandenen, nicht ausführbaren und livegesperrten Reader nennen.
- `StructuralFixtures.test_product_host_imports_and_python_entrypoints_are_forbidden`
  und `test_hardware_contract_ignores_force_prose_but_rejects_control_paths`
  bleiben für den Kern unverändert. Neue Adapterfixtures beweisen jede
  zulässige Quelle und die Ablehnung naher verbotener Varianten.
- Alle anderen bestehenden Safetytests bleiben unverändert: sämtliche
  ReadmeContracts außer no_os_adapter; Release-/Payload-/Session-/Focuschecks;
  launcher_violations; alle StructuralFixtures; alle Classifier-Fixtures.
  Ebenso bleiben alle sieben anderen Hybrid-Display-Testdateien unverändert,
  insbesondere die drei Metaklassenregressionen im Collector.
- Classifier und `tests/test_container_workflow_policy.py` bleiben unverändert.
  H-only und H+E sind tests-only; unbekanntes G blockiert weiterhin.
  **E-only-Dokumentation ist nicht H-only:** manuell dispatchtes E-only kann
  nach aktueller Policy einen Containerbau verlangen. Kein Dispatch in diesem Auftrag.
- Keine Änderung von Containerfile, Justfile, Workflows, Image-Lock, Packaging,
  Installer, Sessiondateien oder Focus. Keine Launcher/Entrypoints.

Neue vor Implementierung rote Schutzfälle stehen im Plan, insbesondere
Adapter-Ausbruch trotz erlaubtem Modul, forbidden neighbor paths/methods,
autostart, oversized frame/file, Metaklassen und fehlende Vollständigkeitsbelege.
Nicht einen realen Safetytest schwächen, um Hostcode grün zu bekommen:
zuerst neue positive/negative Policyfixtures, dann separat genehmigte
Präzisierung, erst dann native I/O-Implementierung. Der Plan berücksichtigt
diese Abhängigkeit trotz der fachlichen Stufenreihenfolge.

## Live-Testgrenze und offene Gates

Fixturetests beweisen ausschließlich Parser-/Policyverhalten, keine Hostfunktion,
keine fehlenden Nebenwirkungen, keinen sicheren Start und keine Hardwarefunktion.
Offene Gates: Ziel-KScreenversion/Format, begrenztes IPC-Binding, Kernelread-
Deadlines, verlässlicher Clientvollständigkeitsbeleg. Solange eines fehlt:
kein vollständiger Live-Snapshot und keine Freigabe aus einem Fixture-Erfolg.

Erste gesondert zu autorisierende Live-Diagnose: eigene bestätigte lokale
Plasma-Wayland-Sitzung, genau benannte Tabellenquellen und Limits, keine Starts,
keine Display-/Dienst-/Sitzungsänderungen, keine Reparatur oder Wiederholung.
Quellgrenzen und mögliche Server-/Kernelnebenwirkungen vorab prüfen.
Vollständiger Rollback bedeutet: keine Zustandsänderung erforderlich;
lokale FDs/IPC-Verbindungen schließen und begrenzte Speicherwerte verwerfen.
Wenn doch eine Zustandsänderung beobachtet wird, ist diese Anforderung verletzt:
stoppen, festen Fehler und manuellen Bedarf melden, keine automatische Recovery.
Erstlesetest ist keine Grafik-, Steam-, Spiel- oder Hardwareabnahme.
