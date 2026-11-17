# ADR: ein fest begrenzter Hybrid-Display-Reader-Service

Datum: 2026-11-17. Entscheidung: separater Reader als Architektur zugelassen;
Ausführung und Deployment bleiben gesperrt. Designbasis:
`27cb019fb85f6799b196e657c9b6b91521a4ecb9`.

## Anlass und Entscheidung

Die abgeschlossene IPC-/libdbus-Machbarkeitsdiagnose fand unter dem bisherigen
Kein-Helper-Vertrag keinen vollständig belegten Transport für Connect, AUTH,
Nachrichtengröße, gesamten Speicher, Unix-FDs und Gesamtdeadline. Vorhandene
Setter sind kein solcher Gesamtbeleg. Quellen sind die historischen lokalen
Berichte `/tmp/hybrid-display-ipc-transport-gate-report.md` und
`/tmp/hybrid-display-libdbus-transport-feasibility.md`; sie sind keine dauerhaft
versionierten Hardware- oder Bibliotheksbelege. Keine Diagnose wird fortgesetzt.

Genau **ein** fest installiertes natives Readerprogramm darf künftig durch genau
einen fest benannten systemd-User-Service isoliert werden. Der Hauptprozess
startet keinen Befehl: Er verbindet sich ausschließlich mit dessen festem Socket.
Keine Shell, argv, Helperwahl, systemctl-/StartUnit-Aufrufe, generische subprocess-
API, Templates, Workerpools oder zusätzlichen Hilfsprogramme. Socketaktivierung
ist später ausschließlich für diesen bereits installierten Reader vorgesehen.
Heute werden weder Unit noch Programm, Installer oder Aktivierung erstellt.

Die zusätzliche Prozessgrenze verlagert den maximalen Schaden eines hängenden
oder speicherhungrigen Bibliotheksaufrufs in einen begrenzten Reader-Cgroup.
Der Hauptprozess hält unabhängig seine eigene endliche Socketdeadline ein und
verwirft Fehler atomar. Eine Sandbox ersetzt weder die Methoden-Allowlist noch
den Nachweis des tatsächlichen Sandboxvollzugs.

## Feste Identitäten und Protokoll

- Service: `hybrid-display-reader-v1.service`.
- Socketunit: `hybrid-display-reader-v1.socket`, ausschließlich `Accept=no`.
- Clientsocket: `%t/hybrid-display-reader-v1.sock`, eigener Usermanager,
  eigene UID, Modus `0600`; `%t` muss der geprüfte eigene Runtimepfad sein.
- Ein einziges ExecStart-Programm ohne Argumente, innerhalb eines minimalen
  schreibgeschützten Readerroots `/usr/libexec/hybrid-display-reader-v1`.
- Pro Verbindung ein Request `CAPTURE_IPC`, Protokollversion 1, längenpräfixiert,
  maximal 4096 Requestbytes und 262144 Responsebytes einschließlich Header.
- Keine freien Pfade, Methoden, Busadressen, Kommandos, Profil-/Gateoverrideflags.

Der [Sicherheitsvertrag](2026-11-17-hybrid-display-reader-service-security.md)
legt Ownership, Schema, Deadlines, Sandboxprüfung und Fehlergrenzen vollständig
fest. Der [TDD-Plan](../plans/2026-11-17-hybrid-display-reader-service-implementation.md)
plant ausschließlich spätere getrennt freizugebende Umsetzung.

## Eng begrenzte Änderung der bisherigen Verträge

Der alte [Adapterentwurf](2026-11-16-hybrid-display-linux-adapter-design.md) und
sein [Plan](../plans/2026-11-16-hybrid-display-linux-adapter-implementation.md)
bleiben historische Quellen. Für diesen neuen Pfad werden künftig nur ersetzt:
Kein-Helper/Kein-Launcher durch die zwei exakten Unitidentitäten; Hostrechte nur
in linux_reader.py durch Readerprozess plus einzigen Socketclient; eigene
Session-PID des Readers durch kernelbelegten Client-Peer und dessen Logindbindung.
Der Usermanager-Reader darf sich selbst nicht als grafische Sitzung ausgeben.

Managergesteuerte Beendigung **nur dieser Reader-Cgroup** und ein ausschließlich
reader-eigener monotoner Deadline-Timer mit terminierendem Signal werden als
neue Recoverygrenze entworfen. Der Hauptprozess sendet keine Signale. Kein Signal
an Steam, Gamescope, KWin, KScreen, Focus oder andere Sitzungen/Prozesse.
Keine automatische Restart-/Reconnect-/Recovery-/Serviceaktivierungs-Schleife.

Unverändert bleiben: Quellen-/Methoden-Allowlist, Nichtautostart von D-Bus-
Diensten, keine Konfigurations-/Display-/Controlleraktionen, kein subprocess im
Hauptprozess, keine Rohwerte in Diagnosen, unveränderte reine Parser/Collector/
Preflight-Grenzen und keine Produkt-/Releaseintegration. AUTH EXTERNAL-only,
keine Cookiequelle und kein FD-Handshake werden **nicht** still aufgehoben.
libdbus ist darum noch keine ausgewählte Implementierung des Readerprogramms.

## Folgen, Alternativen und offene Freigabegates

In-Process-Extension, ctypes/cffi, dbus-python und Gio lieferten keinen belegten
Gesamtpfad. Ein beliebiger externer Helper würde den Auftrag überschreiten.
Der fest isolierte Service ermöglicht eine andere Fehlergrenze, belegt sie aber
noch nicht. systemd-Usernamespaces, Controllerdelegation, Busalias und wirksame
Syscall-/Schreibsperren sowie Isolation von Host-Abstract-Sockets durch
PrivateNetwork sind Abnahmevoraussetzungen, keine Hostannahmen.

Ein kompromittierter Reader mit Benutzerbuszugang besitzt ohne zusätzliche
Bus-/MAC-Mediation grundsätzlich mehr Methodenautorität als seine Code-Allowlist.
Diese Restgrenze sowie Angriffe durch bereits kompromittierte gleiche UID sind
vor produktiver Freigabe ausdrücklich zu entscheiden; keine Sandboxvollständigkeit
behaupten. Gleiche UID und Socketmodus attestieren keine bestimmte Binary.

Alle vier Gates bleiben: kscreen_profile **BLOCKED**, ipc_transport **UNKNOWN**,
drm_read_deadlines **UNKNOWN**, client_completeness **BLOCKED**. Auch ein später
erfolgreicher IPC-Request ist kein vollständiger Hostsnapshot, keine Startfreigabe
und kein Nachweis realer KWin-, Display- oder Hardwarefunktion. Keine heutige
Implementierungs-, Installations-, Build-, Live-, Git- oder Workflowfreigabe.
