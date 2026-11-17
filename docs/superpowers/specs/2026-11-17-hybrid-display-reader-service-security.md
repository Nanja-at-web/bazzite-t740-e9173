# Reader-Service v1: Sicherheits-, Protokoll- und Migrationsvertrag

Status: Dokumentationsentwurf zur [ADR](2026-11-17-hybrid-display-reader-service-adr.md).
Alle Zahlen sind konservative Designentscheidungen, keine gemessenen Hostgrenzen.
Nur dieser zukünftige IPC-Pfad ist beschrieben; kein DRM-/proc-Dateibackend.

## Prozess, Socket und Identitätsgrenze

Ein festes natives Programm, kein Pythoninterpreter/Helperargument, keine
ExecStartPre/Post-, ExecStop-, Shell-, Template- oder generische Transientunit.
Root des späteren Artefakts: `/usr/lib/hybrid-display-reader-v1/root`, root-owned,
nicht gruppen-/benutzerschreibbar, minimale gepinnte Binary-/Runtime-BOM, keine
Shell, Paketmanager, Tools, Konfiguration aus HOME oder Pythonplugin-Suche.
ExecStart im Root: `/usr/libexec/hybrid-display-reader-v1`, null Argumente.
Noch kein Packagingformat/Runtime-Binding ausgewählt oder installiert.

Der Usermanager besitzt den Listener `%t/hybrid-display-reader-v1.sock` (0600),
Runtimeverzeichnis eigene UID/0700, kein Symlink, keine alternative Adresse.
Der Client prüft Verzeichnis und Socket mit injiziertem, gegen Austausch
abgesichertem Lookup, verbindet einmal nichtblockierend und prüft SO_PEERCRED:
UID exakt eigene unprivilegierte UID, keine UID0/abweichende EUID.
Der Reader erhält genau einen Listener-FD über Socketaktivierung; zusätzliche
Activation-FDs oder falscher FD-Typ blockieren. Keine selbst angelegten Socketpfade.

**Socketaktivierung:** Der Client kann als SO_PEERCRED-Peer den erzeugenden
Usermanager sehen, nicht den erst später acceptenden Reader. Eine solche PID
wird niemals als nachgewiesene Reader-Binary oder Service-Cgroup ausgegeben.
Das Vertrauensfundament ist die administrativ geprüfte feste Installation;
kein vom Peer geliefertes „sandbox_ok“-Bit ersetzt diese Prüfung. Eine vollständig
kompromittierte gleiche UID kann ihre Userunits oder Runtimepfade beeinflussen;
gegen dieses Angreifermodell ist der User-Service keine harte Identitätsgrenze.

Der Reader prüft den akzeptierten Client-Peer mit SO_PEERCRED (UID, PID), nicht
mit einer PID aus dem Request. Nur dieser Peer wird mit Logind an die eigene
aktive lokale Wayland/user-Sitzung gebunden. SSH, manager, remote, unbekannt oder
abweichende Desktopklasse blockieren vor KScreen. KWin-/KScreen-Owner müssen
jeweils dieselbe bestätigte Session besitzen. Der Reader selbst bleibt ein
Usermanagerprozess; dessen Environment ist kein GUI-Beleg. Keine fremde Umgebung
lesen und keine Sessionvariable raten, übernehmen oder ändern. Die frühere
Fünf-Env-Werte-Prüfung bleibt im reinen Fixturepfad erhalten; der neue native
Pfad ersetzt diese Beweisquelle ausdrücklich durch Client-Kernelpeer plus
Logind, nicht durch eigene Reader-Umgebungswerte. Der eigene Buspfad wird aus
der geprüften UID und dem fest gebundenen Socket bestimmt, nicht aus einem
frei übermittelten Busadressfeld.

## Ressourcen und zeitliche Grenzen

| Grenze | Vorgeschlagener verpflichtender Wert | Auswirkung/Prüfpflicht |
|---|---|---|
| MemoryMax / MemoryHigh / MemorySwapMax | 64M / 48M / 0 | Native Bibliothek, Decoder und Antwort leben im selben begrenzten Cgroup; Controllerwirkung nachweisen |
| TasksMax | 1 | Kein Thread/Fork/Pool; inkompatible Runtime ablehnen |
| CPUQuota / CPUQuotaPeriodSec | 25% / 100ms | Harte CPU-Drosselung, kein Echtzeitversprechen; CPUWeight=10 nur ergänzend |
| LimitAS / LimitNOFILE / LimitCORE / LimitFSIZE | 128M / 32 / 0 / 0 | Zweite Ressourcenebene; keine Dumps/Dateiausgabe, kein Ersatz für Cgroupkontrolle |
| Hauptprozessdeadline | 5s ab vor connect | Begrenzt Startwartezeit, vollständige Antwort, EOF und Parsing; keine Retries |
| Reader-Gesamtdeadline | 4s ab Prozesseintritt, beide Captures | Keine Resetmöglichkeit durch Request/Antwortfragmente |
| Header / kompletter Request | 100ms / 250ms ab accept | Slowloris beendet diesen Reader, keine gleitende Aktivitätsfrist |
| Responseausgabe | 250ms, innerhalb 4s | Nicht lesender Client blockiert keine weitere Erfassung |
| Start / Runtime / Stop | TimeoutStartSec=500ms / RuntimeMaxSec=4s / TimeoutStopSec=100ms | Type=exec, keine Pre-/Postprogramme; Manager-SIGKILL nur eigene Cgroup, Restart=no |
| Listener | Backlog=1, Accept=no | Ein bearbeiteter Client; kein Claim einer MaxConnections-Garantie bei Accept=no |
| Aktivierungsrate | TriggerLimitIntervalSec=60s, TriggerLimitBurst=3; StartLimitIntervalSec=60s, StartLimitBurst=3 | Überlast sperrt; kein Rerun/automatisches Entsperren im Client |

Ein reader-eigener CLOCK_MONOTONIC-Kerneltimer darf ausschließlich diesen Prozess
per terminierendem SIGALRM begrenzen, auch während eines opaken blockierenden
Bibliotheksaufrufs. Keine Python-/C++-Signalhandler, die unsicheren Cleanup
versuchen; kein Timerthread, kein kill(pid)-Ziel, keine fremden Signale.
Der jeweils frühere Einzel- oder Gesamtablauf wird vor dem Aufruf armiert;
Rearm erfolgt ausschließlich mit Restzeit. Rückkehr nach Frist verwirft Daten.
Manager-Cgroupbeendigung ist die unabhängige äußerste Grenze. Scheduler-/Kernel-
Latenz bleibt eine Linux-Messgrenze; kein mathematisch harter Wallclock-Beweis.
Timerarmierung ist vor jedem opaken Aufruf zwingend; ein Fehler dabei blockiert
vor dem Librarycall. Kein App-Code versucht nach dem terminierenden Signal
weiterzuarbeiten oder Teilergebnisse zu retten.

Unveränderte B0–B6-Quellenfristen: AUTH/Hello/Owner/UID/PID/Sessionlookup 250ms,
acht B4-Properties zusammen 500ms, Config 500ms, EDID je 100ms. Rawbudgets:
65536 B je vollständiger D-Bus-Message, AUTH4096 B, unerwartete Messages maximal
32/32768 B, gesamte Quellenaufnahme 262144 B über beide Captures. Pro Capture
21+C+O Queries, plus insgesamt vier AUTH/Hello-Schritte: höchstens110 Reader-
Transaktionen bei je16 Clients/Outputs;108 davon Methodencalls. Keine offene
Introspektion, Listen oder Retryschleifen. Clientframing zählt zusätzlich in die
unten festgelegte Responsegrenze. Bibliotheksinterne Heapüberhänge müssen in64M
passen, dürfen aber akzeptierte Quellen-/Messagebudgets nicht erweitern.

Der alte libdbus-Befund zu AUTH/FD/Connect wird nicht durch einen Watchdog
wegdefiniert: richtige AUTH-Auswahl und Byte-/FD-Policy müssen vor erfolgreichem
Betrieb belegt sein. Ohne passende Bibliothekskonfiguration bleibt der native
Transport gesperrt; keine heimliche Cookie-/FD-Handshake-Ausnahme.

## Sandboxmatrix: statische Prüfung und spätere Abnahme

Dies sind Anforderungen an zukünftige Units, **keine Unitdateien**. Unwirksame,
unbekannte oder nur still ignorierte Einstellungen führen zu Nichtfreigabe;
keine Abschwächung für einen grünen Test. Ein späteres Deployment muss Wirkung
in seinem tatsächlichen systemd-Usermanager nachweisen, nicht nur Syntax.

| Einstellung | Entwurf und Kompatibilitätsbedingung |
|---|---|
| NoNewPrivileges=true; CapabilityBoundingSet/ AmbientCapabilities leer | Keine Privilegiengewinnung, kein sudo/root; der Reader behält eigene UID |
| RootDirectory fest, ProtectSystem=strict | Minimale unveränderliche Runtime-BOM; vorhandene UID-/ABI-/Loaderannahmen gesondert prüfen |
| ProtectHome=true | Verdeckt auch /run/user und damit den normalen Benutzerbus; nicht als unverändert kompatibel behaupten |
| BindReadOnlyPaths | Ausschließlich Hostquelle %t/bus -> /run/hybrid-display-reader-v1/user-bus und /run/dbus/system_bus_socket -> /run/hybrid-display-reader-v1/system-bus im Readerroot; keine ganze Runtime-/HOME-Bindung |
| PrivateTmp=true | Mit strict allein bleiben private tmp-Pfade schreibbar; zusätzlich /tmp und /var/tmp explizit read-only, leer, keine Ausnahmen |
| RestrictAddressFamilies=AF_UNIX | Keine AF_INET/AF_INET6/AF_NETLINK; keine geerbten fremden Socketfamilien. Keine abstract-/exec-/Netzwerkadresse als Fallback |
| PrivateNetwork=true | Eigener tatsächlich wirksamer Netzwerknamespace trennt Host-Abstract-Unix-Sockets; feste dateisystemgebundene Busaliase separat positiv prüfen. Ohne wirksame Isolation keine Freigabe |
| RestrictSUIDSGID=true; LockPersonality=true | Keine SUID-/SGID-Erzeugung oder Personalityänderung; kein spezielles Runtimebedürfnis vorgesehen |
| MemoryDenyWriteExecute=true | Native Runtime ohne JIT/Textrel; bei Konflikt Runtime verwerfen, nicht Option entfernen |
| SystemCallArchitectures=native | Keine32-Bit-/Compat-ABI; Zielarchitektur im Artefakt fest binden |
| SystemCallFilter | Ausgangsmenge @system-service, davon @privileged/@resources/@mount/@reboot/@swap/@raw-io/@clock/@cpu-emulation/@obsolete/@debug ausschließen; exakte aufgelöste native Allowlist vor Packaging einfrieren |
| Engerer Filter nach Start | Reader vor fremden Inputs zusätzlich ohne execve/execveat/fork/vfork/clone/clone3/ptrace/bpf/mount/unshare/setns; nur nötige read/write/recvmsg/sendmsg/poll/Clock-/eigenen Timer-/Allocator-/Exit-Aufrufe. Implementierung braucht getrennte Freigabe |
| Keine Geräte | PrivateDevices=true, /dev zusätzlich unzugänglich, leere DeviceAllow/DevicePolicy=closed soweit wirksam; kein /sys-/dev-Bind. Kein Reader-open von Deviceknoten; vom Manager bereitgestellte null-stdio-FDs bleiben ohne Nutzdaten. Auch keine DRM-/Input-/Blocknodes über andere Pfade |
| Keine Schreibpfade | Keine ReadWritePaths, State-/Cache-/LogsDirectory oder beschreibbare RuntimeDirectory im Readerroot; kein O_CREAT/Dateischreiben/Verzeichnisanlegen; Socket-Sends sind die einzige Nutzdatenausgabe |
| Logging | StandardInput/Output/Error ohne Nutzdaten (null), LimitCORE=0; keine DBus-Bibliotheksdebugausgabe oder Core-/Rohfehlerweitergabe |

Der Readerroot enthält keine anderen Hostpfade, Shells oder Unix-Sockets. Die
beiden Busaliase liegen **außerhalb** des durch ProtectHome verborgenen /run/user.
Bindziele müssen vom festen Root bereitgestellt sein; keine Bindung unter einen
unzugänglichen Elternpfad. Die Hostquelle und UID müssen im Managerkontext geprüft
werden. Read-only-Bind eines Unix-Sockets unterbindet dessen Kommunikation nicht;
er ist ausdrücklich kein D-Bus-Methodenfilter. Der Listener kommt per FD und
braucht im Readerroot keinen sichtbaren Clientsocketpfad.

Laut [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
benötigen diese Dateisystemhärtungen im Usermanager passende Usernamespace-
Unterstützung. Nicht überall verfügbare Geräte-/Cgroupkontrollen sind ebenfalls
keine angenommenen Fähigkeiten. Mountreihenfolge, beide Busaliase, UID-Abbildung,
read-only tmp, Host-Abstract-Socket-Isolation durch PrivateNetwork,
Seccomp/Timerverträglichkeit und tatsächlich aktive Controller
bleiben zwingende spätere Abnahmepunkte. Keine Hostprüfung in diesem Auftrag.
[Resource Control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html),
[Socket](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html)
und [Service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
begründen getrennt Controller-, Aktivierungs- und Runtimegrenzen; das sind
Primärquellenlektüre und Designentscheidungen, keine Laufzeitbelege.

## Protokoll v1: vollständiger begrenzter Austausch

AF_UNIX SOCK_STREAM. Header genau16 Bytes in Netzwerkbyteordnung:
Magic4=`HDR1`, Version u16=1, Typ u16, Bodylänge u32, Request-ID u32=1.
Länge vor Bodyallokation gegen Richtungslimit prüfen; Addition überlaufsicher.
Gesamtframe maximal262144 B; Request maximal4096 B. Null-/falsche Version,
unkannte Typen, trailing Bytes, mehr als ein Frame oder EOF mitten im Frame
werden abgelehnt. Keine Kompression, Pickle, generischen RPCs, Pfade oder argv.

Einziger Requesttyp 1=`CAPTURE_IPC`. Body: Clientzahl u8 C (0..16), danach genau
C big-endian u32-PIDs (1..2147483647), eindeutig und keine behauptete Peer-PID.
Datenlänge muss exakt1+4*C sein. Das ist eine deklarierte Konfliktliste, niemals
Clientvollständigkeitsbeweis. Keine andere Quelle wird durch Requestparameter
wählbar; keine Gate-/Profil-/Timeout-/Größenoverrides. Client schreibt Request
unter eigener Deadline vollständig und führt SHUT_WR aus. Reader verlangt EOF
unter derselben Requestfrist, bevor er Quellen befragt; keine Pipeline.

Response 0xffff=`BLOCKED`: Body genau ein u16 aus der folgenden festen Tabelle;
keine Detailfelder oder Teilergebnisse. Response 0x8001=`IPC_CAPTURE_OK` ist nur
vollständige private IPC-Datenübertragung, kein Adapter-/Snapshot-/Preflighterfolg.
Fehlende native Profilfreigabe liefert BLOCKED; SYNTHETIC_V1 ist nie ein
produktionsseitig wählbares Profil. Beide Captures bleiben bis zur vollständigen
Validierung im begrenzten Reader. Reader/Client verwerfen alles bei Abweichung.

Erfolgsbody: Bootstrapzahl u8=4, vier Records, Capturezahl u8=2; je Capture
Recordzahl u16<=53 und genau diese Records. Ein Record hat Querykind u8, Bus u8
(0=system/1=session), Subject u32, Länge u32, exakt so viele Bytes Payload.
Querykind1..9 entspricht AUTH, HELLO, OWNER, OWNER_UID, OWNER_PID,
SESSION_BY_PID, SESSION_PROPERTY, CONFIG, EDID. Subject ist bei Owner/Credentials
0=logind/1=KWin/2=KScreen, bei Sessionlookup0=Peer/1=KWin/2=KScreen/3..18=
Clientordinal, bei Properties0..7=Id/User/Type/Desktop/Remote/Active/Class/State,
Config0, EDID=aus geprüfter Config stammende Output-ID. Keine freie Zieladresse.
Reihenfolge und Kardinalität folgen B0–B6 des alten Designs exakt; Client prüft
Bus/Subject/Querykind und gespiegelte zweite Aufnahme, nicht nur Recordzahl.

AUTH-Payload genau1 Byte bestätigtes ACK (keine rohen AUTH-Zeilen), numerische
UID/PID genau u32, bool genau0/1, ASCII/Objektpfade streng nach altem Schema.
User-Payload: UID u32 plus Pfadlänge u16 plus begrenzter ASCII-Pfad. Config ist
eine begrenzte UTF-8-JSON-Projektion eines separat geprüften echten Versionsprofils,
keine pauschale Kompatibilitätsbehauptung für die synthetische Fixture. EDID
höchstens4096 private Bytes, nur im Speicher und rein validiert; keine Roh-EDID
in Logs/Diagnosen. Variable Records haben zusätzlich die B0–B6-Quellenlimits.
Gesamte Response inklusive Record-/Frameheader bleibt unter262144 B, auch wenn
zulässige einzelne Quellgrößen in Summe deshalb konservativ blockieren müssen.
Decoder begrenzt Tiefe8, Nodes8192, Maps64, Arrays128 (Outputs/Clones16), Strings
128 UTF-8-Bytes; vor Aufbau öffentlicher Container begrenzen. Unbekannte Keys
nicht rendern oder an den Collector reichen. Kein D-Bus-Wireparser im Client.

| Wirecode | Bestehender Reason-Code | Wirecode | Bestehender Reason-Code |
|---|---|---|---|
| 1 | input_invalid | 2 | source_not_allowed |
| 3 | source_unavailable | 4 | source_denied |
| 5 | source_limit | 6 | source_timeout |
| 7 | source_type_invalid | 8 | ipc_invalid |
| 9 | ipc_limit | 10 | owner_missing |
| 11 | owner_invalid | 12 | session_unverified |
| 13 | inventory_changed | 14 | kscreen_profile_unverified |
| 15 | client_inventory_unverified | 16 | reader_deadline_unverified |
| 17 | reader_failed | 18 | edid_invalid |
| 19 | kscreen_unavailable | 20 | kscreen_schema_invalid |

Alle Codes stammen aus host_reader.CODES; ungültiger Wirecode wird lokal
reader_failed. B5-Unverfügbarkeit und ungültiges KScreen-Schema behalten genau
ihre bestehenden Codes19/20. Jeder andere intern nicht ausdrücklich dieser
Tabelle zugeordnete Fehler wird deterministisch reader_failed; keine spontanen
Codes oder impliziten erfolgreichen Fallbacks. Nicht verwendete DRM-/Collector-
Codes eröffnen keine zusätzlichen Servicequellen. Keine neuen dynamischen Codes, Exceptiontexte, Hashes, Pfade,
Personen-/Sessiondaten in Reason-Codes. Kein Responsebody vor vollständiger
Schema-/Grenzprüfung als Facts sichtbar. Client begrenzt seine Empfangsallokation
auch bei bösartigem Server unabhängig, verwirft nach Antwort zusätzliche Bytes
und verlangt EOF bis zur ursprünglichen Deadline. Commitpunkt ist erst der
vollständig validierte Frame plus EOF innerhalb dieser Frist. Ein früher
Disconnect/Abbruch liefert kein Ergebnis. Ein Crash oder Timerablauf nach
vollständiger gültiger Übertragung kann dasselbe EOF wie ein normaler Exit
erzeugen und wird nicht als unterscheidbar behauptet; bereits übertragene,
validierte Capturedaten bleiben in diesem Fall ein Datenbeleg, kein
Servicegesundheits-/Snapshot-/Startbeleg. Kein automatischer Collector-
oder Preflightaufruf aus dem Socketclient; FixtureReader bleibt reine Testklasse.

SCM_RIGHTS wird auf dem Clientsocket abgelehnt und tatsächlich empfangene FDs
werden geschlossen; Ancillary-Truncation ist Fehler. Keine FD-Weitergabe, keine
Credentials aus Nutzdaten. Ein Streamfragment verlängert nie eine Deadline.
Eine Clientverbindung kann nur eine Captureausführung auslösen; parallele oder
queued Verbindungen führen nicht zu Readerpools. Der aktive Reader schließt vor
Erfolg/Fehler den Listener und alle noch eigenen FDs; der Manager hält seinen
Listener getrennt. Managerwarteschlange und Aktivierungsrate werden separat
begrenzt. Hauptprozess reconnectet nicht nach Disconnect oder Serviceabsturz.

## Bedrohungs- und Fehlergrenzen

| Bedrohung/Fehler | Grenze/Reaktion | Verbleibende Grenze |
|---|---|---|
| Fremde UID/Root/Socketaustausch | Runtime-/Socketprüfung, SO_PEERCRED, einmaliger Connect; blockieren | Gleiche kompromittierte UID kann Usermanager/Runtime beeinflussen; keine Binaryattestation |
| SSH/andere grafische Sitzung | Peer-PID nur vom Kernel, Logindbindung plus alle Owner-Sessions | Usermanager-Environment und aktive lokale Sitzung allein sind kein Ausführungsbeweis |
| Slowloris/fehlender Header/EOF | 100/250ms absolute Fristen, kein Quellzugriff vor EOF | CPU-/Schedulerlatenz nicht als harte Echtzeit zusichern |
| Oversize/Overflow/Deserialisierung | Präfix und Recordlimits vor Allokation, begrenzte Decoder, MemoryMax | Bibliotheksinternes Mehrallokieren kann OOM/Abbruch verursachen, nie Erfolg |
| Hängender Connect/AUTH/Librarycall | eigener Timer beendet nur Reader, Manager4s/Stop100ms; Client5s | Frühzeitiger EOF beweist keine konkrete Todesursache |
| Timeout/Disconnect/Crash/OOM vor Commit | keine Teilergebnisse, kein Retry; Deadline -> source_timeout, sonst reader_failed | Nach vollständigem gültigem Frame plus EOF ist Crash nicht vom normalen Exit unterscheidbar; kein Gesundheitsbeleg |
| Missing/wechselnder Owner | owner_missing/owner_invalid/inventory_changed, keine Aktivierung | Kein Beobachtungserfolg aus historischen Ownern oder Namenähnlichkeit |
| Ungültige Signatur/Sender/Serial/EDID | feste Codes, ganze Antwort verwerfen | Kein Raw-DBusError oder Payloadlogging |
| Quellen-/Methodenausweitung | native feste Querytabelle und Clientprüfung, keine RPC-Freitexte | Seccomp/AF_UNIX/Socket-readonly filtern keine D-Bus-Member |
| Host-Abstract-Unix-Socket | PrivateNetwork wirksam erforderlich, keine geerbten fremden Sockets | Nur der Namespace-Vollzugsnachweis, nicht RootDirectory allein, begrenzt diese zusätzliche Reichweite |
| Kompromittierter Reader am Userbus | Root/Device/Netz-/Schreibrechte begrenzt, keine Privilegiensteigerung | Mutierende Busmethoden sind ohne separate Bus-/MAC-Mediation nicht OS-seitig ausgeschlossen; ausdrückliche Threat-Model-Entscheidung vor Freigabe nötig |
| Unitoptionsstilllegung/Usernamespace-/Controllerlücke | kein Deployment ohne tatsächlichen Wirkungsnachweis; kein Fallback | Ein Propertywert/geladene Unit allein ist kein Vollzugsbeleg |
| Rawdaten in Journal/Core | keine Programmstdout/-stderr, feste Diagnosecodes, keine Dumps | systemd darf generische Unit-/Exitmetadaten führen, keine Requestdaten |
| Wiederholte Socketaktivierung/DoS | Listener-/Aktivierungsrate, Hauptprozess ein Versuch, keine Pools | Lokale DoS durch gleiche UID bleibt möglich; nicht unbegrenzt automatisch reparieren |
| Fehlendes KScreen-/DRM-/Vollständigkeitsgate | keine native Profil-/Snapshotfreigabe | Prozesssandbox macht UNKNOWN/BLOCKED niemals zu Erfolg |

## Safety-Migration: einzeln, testgetrieben, keine heutige Lockerung

1. `tests/test_hybrid_display_safety.py::product_violations` bleibt für alle
   bisherigen reinen Module unverändert. Nur die exakte zukünftige
   `reader_service_client.py` erhält einen zusätzlichen engeren Socketchecker:
   kein subprocess/signal/systemd/dbus/ctypes, keine freien Socketpfade/Familien,
   keine Ausführung beim Import. Keine Präfix-/Dateiendungs-Ausnahme.
2. `launcher_violations` darf künftig nur die beiden exakten Reader-Unitpfade
   und das eine Readerartefakt im genehmigten Teilbaum zusätzlich zuordnen.
   Nachbarunit, Template, Zusatz-Exec und Installer bleiben negative Fixtures.
   C-Quellen werden nicht durch einen Python-AST-Checker für sicher erklärt;
   eigener nativer Source-/ABI-/Packagingvertrag erforderlich.
3. `reader_commands.py::reject_command` und seine Null-Spawn-Tests bleiben
   vollständig unverändert. Das neue Socketprotokoll ist keine argv-Allowlist.
4. Native Sessionbindung an den Peer bekommt neue separate Tests; bestehende
   Sessionparser-/Metaklassen-/Collector- und Fixturetests werden nicht abgeschwächt.
   read_inventory/Collector/Preflight/CLI/Runner erhalten keine Startintegration.
5. `ReadmeContracts.test_no_os_adapter_boundary`, non_executable und exakte
   Launcherzuordnung werden erst beim getrennt genehmigten Native-Milestone
   präzisiert. Die heutige reine Foundation bleibt weiter rein, nicht ausführbar.
6. Globale Release-/Payload-/Session-/Focus-Scanner sowie Classifier bleiben
   unverändert. Ein zukünftiger dokumentierter Unitentwurf ist kein Paketinhalt;
   echte Installationspfade/Buildkette erfordern separate Integration und deren
   eigene Klassifizierung. Kein blanket-ignore für .service/.socket/native C.
7. AST-Verbote für kill/spawn/exec bleiben im Hauptprozess bestehen. Native
   Timerbeendigung und Manager-KillMode betreffen ausschließlich Reader und
   müssen als neue eng benannte Ausnahme getestet werden, niemals als generelle
   Freigabe aus dem neuen Helpervertrag abgeleitet werden.

Offen vor Umsetzung mit echten Units: konkrete Native-Runtime inklusive
AUTH-/FD-Eignung, tatsächlicher Usernamespace-/Cgroup-/Seccompvollzug und
Busalias-Kompatibilität; fixierte Syscall-/Loader-BOM und Privacyverhalten;
Same-UID-/Busmethoden-Restbedrohungsmodell oder eigene Bus-/MAC-Policy.
Bis dahin keine Installation, automatische Aktivierung oder Livefunktion.

## Unabhängiger Entwurfsreview

Ein unabhängiger Reviewer las ADR, diesen Vertrag und den gesamten Plan. Drei
wesentliche Präzisierungen wurden übernommen: PrivateNetwork samt negativer
Host-Abstract-Socket-Abnahme; expliziter Frame+EOF-Commitpunkt statt eines
unbeweisbaren crashfreien Serviceendes; feste Wirecodes19/20 für bestehende
KScreen-Fehler. Zugeordnete TDD-Fälle stehen im Plan. Kein Produktcode, keine
Unit, kein Test oder Host-/Buslauf wurde daraus abgeleitet. Offene Deployment-
und Bedrohungsmodellentscheidungen bleiben sichtbar und sperrend.
