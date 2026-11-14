# Dell-Hybrid-Nur-Lese-Audit, 2026-11-14

Dieser Bericht bewahrt die vollständige inhaltliche Bestandsaufnahme der ersten
Sitzung einschließlich ihrer damaligen Entwürfe und Messgrenzen. Er wurde in
Stufe 2 gespeichert; es wurden dafür keine Hardwaremessungen wiederholt.
Repositorylinks wurden relativiert; unnötige persönliche Pfade werden als `~`
angegeben. Quellzeilen beziehen sich auf Commit
`31caaaaef2317fb2207350ad3b121c843159cdfe`.

Der lokale Linux-Benutzername ist in Pfaden und historischen Befehlsbelegen
als `<local-user>` redigiert. Die redigierten Befehlszeilen geben das
ursprüngliche argv nicht bytegenau wieder.

**Zeitliche Abgrenzung:** Die Abschnitte O–S sind historische Entwürfe, keine
heutigen Ausführungsfreigaben. Maßgebliche anschließende Stufe-2-Entscheidung:
Endziel bleibt **normaler Bazzite Gaming Mode auf Monitor 1 plus eigenständiges
Plasma auf Monitor 2**, technisch **nicht nachgewiesen**. Nested Gamescope ist nur
Diagnose, Entwicklung oder möglicher Fallback. Echte Button-Glyphen sind das Ziel;
Familientext reicht nicht. Physische Verkabelung bleibt zu bestätigen. Bei
unklarem Routing keine aggressive Wiederherstellung und keine Deinstallation
ohne bestätigten sicheren Ausgangszustand. Aktuelle Regeln:
[AGENTS.md](../../AGENTS.md) und [Hardwarebaselines](../agent-guidance/hardware-baselines.md).

## A. Kurzfazit

**Der vorhandene Stand ist ein installierter Controller-Fokus-Prototyp, kein
implementierter Hybrid Gaming Mode mit parallelem normalem Gaming Mode und Plasma.**

- Lokaler Branch, lokaler HEAD und live abgefragter Remote-HEAD stimmen überein:
  `design/hybrid-gaming-mode`, Commit
  `31caaaaef2317fb2207350ad3b121c843159cdfe`.
- Der Worktree war sauber. Keine uncommitteten oder unversionierten Dateien gefunden.
- Keine `AGENTS.md` im untersuchten Verzeichnisbaum oder den geprüften Vorfahren.
- GitHub-Zugang als `Nanja-at-web` funktioniert außerhalb der Netzwerksandbox.
  Schreibrechte wurden nicht getestet.
- Dell OptiPlex 5080, i5-10500T und UHD Graphics 630 mit `i915` sind nachgewiesen.
- Plasma läuft unter Wayland. Steam läuft; Gamescope läuft in der erfassten
  Prozessliste nicht.
- Der Hybrid-Focus-Dienst ist installiert und aktiviert, aber **inaktiv**.
  Sein Control-Socket fehlt.
- Nur **ein verbundener physischer DRM-Ausgang**, `DP-1`, erkannt. Eine aktuell
  angeschlossene zweite Anzeige ist **nicht nachgewiesen**.
- Zehn erfolgreiche Fokuszyklen, ausschließliche Eingabezustellung und funktionierende
  Controller-Glyphen auf Hardware sind **nicht nachgewiesen**.
- Ursache des früher schwarzen zweiten Monitors und von „Primary child shut down“ offen.

**Unbeabsichtigte Nebenwirkung:** Die angeforderte lesende Abfrage
`kscreen-doctor -o` brach mit Exit `134` ab. Das System erzeugte automatisch einen
Core-Dump. Die Vorgabe „keine Dateien erstellen“ blieb damit nicht vollständig
nebenwirkungsfrei. Keine Bereinigung vorgenommen.

Keine Implementierungen, Dienststeuerungen, Profilwechsel, Sitzungswechsel,
Builds oder Git-Schreiboperationen wurden ausgeführt.

## B. Repository-, Branch- und Worktree-Zustand

| Merkmal | Nachgewiesener Zustand |
|---|---|
| Shell-Arbeitsverzeichnis | `/home/<local-user>/bazzite-t740-e9173` |
| Git-Toplevel | `/var/home/<local-user>/bazzite-t740-e9173` |
| Pfadauflösung | `/home/<local-user>` verweist auf `/var/home/<local-user>` |
| Branch | `design/hybrid-gaming-mode` |
| HEAD | `31caaaaef2317fb2207350ad3b121c843159cdfe` |
| Commit-Nachricht | `fix: harden hybrid focus handoff` |
| Upstream | `origin/design/hybrid-gaming-mode` |
| Origin, Fetch und Push | `https://github.com/Nanja-at-web/bazzite-t740-e9173.git` |
| Worktrees | Ein aufgelisteter Worktree auf diesem Branch |
| Staged/unstaged | Keine Änderungen |
| Unversionierte Dateien | Keine |
| Ignorierte Dateien im Status | Keine ausgegeben |
| AGENTS.md | Keine gefunden |

Belege: `pwd`, `readlink -f /home/<local-user>`, `git rev-parse --show-toplevel`,
`git branch -vv`, `git worktree list --porcelain`, Status und abschließende Diffs.

Geprüfte Vorfahren:

```text
/AGENTS.md
/var/AGENTS.md
/var/home/AGENTS.md
/var/home/<local-user>/AGENTS.md
/home/AGENTS.md
/home/<local-user>/AGENTS.md
```

Alle nicht vorhanden; auch `find .. -name AGENTS.md -print` ohne Treffer.

Vom Commit vor dem Hybrid-Design, `9d27d33`, bis HEAD keine Änderungen an:

```text
Containerfile
system_files/
image-lock.json
.github/workflows/
installer/
build_files/
```

Dies ist ein Quellcodevergleich, keine erneute Hardwarevalidierung.

## C. GitHub- und gh-Zugriff

| Prüfung | Ergebnis |
|---|---|
| gh installiert | `/home/linuxbrew/.linuxbrew/bin/gh` |
| Authentifizierung auf dem Host | Erfolgreich, Nanja-at-web, Keyring |
| Benutzer über API | `Nanja-at-web` |
| Repository lesbar | Ja |
| Repository-URL | `https://github.com/Nanja-at-web/bazzite-t740-e9173` |
| Default-Branch | `main` |
| Live-HEAD des Arbeitsbranches | `31caaaaef2317fb2207350ad3b121c843159cdfe` |
| Offene PRs mit diesem Head-Branch | Keine, `[]` |
| Schreibrechte | Nicht geprüft |
| Issues | Nicht abgefragt |

Live-HEAD stimmt mit lokalem HEAD und gespeichertem Remote-Tracking-Stand überein.
Kein Fetch durchgeführt.

**Messgrenze:** In der Sandbox scheiterten zunächst DNS/API-Zugriffe;
`gh auth status` meldete dort ungültigen Zugang. Ausdrücklich freigegebene
Wiederholungen außerhalb der Sandbox erfolgreich. Der erste Befund belegt keine
tatsächlich ungültigen Zugangsdaten. Geheimniswerte wurden nicht dokumentiert.

## D. Verfügbare Werkzeuge

| Werkzeug | Befund/Verwendung |
|---|---|
| Superpowers | Verfügbar; using-superpowers, systematic-debugging und verification-before-completion gelesen und verwendet |
| Context7 | In verfügbarer Werkzeugliste nicht vorhanden; nicht installiert |
| GitHub/gh | Vorhanden und erfolgreich lesend verwendet |
| GitHub-MCP | Verfügbar, nicht benötigt und nicht verwendet |
| REA | Kein entsprechendes Werkzeug in der Werkzeugliste gefunden; nicht ausgeführt |
| Weitere | Git, Python, RPM, systemctl, journalctl, loginctl, lspci, sysfs, coredumpctl |

Keine Umsetzungsmethodik ausgeführt. Implementierungspläne nur als
Untersuchungsgegenstand gelesen. Kein begründeter REA-Anwendungsfall: offene
Fragen benötigen zuerst Laufzeitbelege und Hardwaremessungen.

## E. System- und Hardwarezustand

| Merkmal | Befund | Beleg |
|---|---|---|
| Hersteller/Modell | Dell Inc., OptiPlex 5080 | DMI-sysfs |
| Micro-Gehäusevariante | Nicht unabhängig nachgewiesen; Chassistyp 3 | DMI-sysfs |
| CPU | Core i5-10500T @ 2,30 GHz | lscpu |
| Kerne/Threads | 6 / 12 | lscpu |
| Nutzbarer RAM | 16064456 kB, etwa 15,3 GiB | /proc/meminfo |
| Exakt verbaute 16 GiB | Nicht vollständig nachgewiesen; Messwert damit vereinbar | Messgrenze |
| OS | Bazzite 45.20261105, Kinoite, bazzite-deck | /etc/os-release |
| Kernel | 7.2.15-ogc1.1.fc45.x86_64 | uname -a |
| Plasma | plasma-workspace-6.8.2-1.fc45 | RPM |
| KWin | kwin-6.8.2-3.fc45 | RPM |
| Grafische Sitzung | KDE/Wayland, seat0, lokal, aktiv | loginctl show-session 3 |
| SSH | Aktiv und aktiviert | systemctl status sshd.service |
| RDP | krdpserver läuft, KRDP 6.8.2 installiert | Host-Prozessliste/RPM |
| RDP-Verbindungsfunktion | Nicht getestet | Messgrenze |
| Codex lokal | Prozesse UID 1000, darunter in SSH-Prozesskette | Host-Prozessliste |

`xrdp`/`xrdp.service` nicht installiert/vorhanden. Das widerspricht einer
RDP-Einrichtung über KRDP nicht.

Gebootetes Image laut `rpm-ostree status`:

```text
ghcr.io/nanja-at-web/bazzite-t740-e9173@sha256:93dc4bb0199798624851db25908a922fe42826efee5f61f990bfe6443ff1d4fa
```

Zustand `idle`, Version `45.20261105.2-polaris-sdl`, zwei aufgeführte Deployments
mit demselben Image-Digest.

Installierte Metadaten aus `/usr/share/t740/build-info.json`:

```text
source_revision: 393bd6676f5f1c45403d73ef7c87378c145110a0
created:         2026-11-08T20:21:07Z
```

„HP t740“ im Zielhardwaretext ist Image-Metadatum, keine Dell-Hardwareerkennung.

**Messgrenze:** `bootc status` scheiterte ohne Root und meldete „Preparing for
write“. Kein Root-Wiederholungsversuch. Deploymentbelege daher aus rpm-ostree und
installierten Build-Metadaten.

## F. Erkannte Monitore, Grafikgeräte und Treiber

```text
PCI:     0000:00:02.0
GPU:     Intel UHD Graphics 630 [8086:9bc8]
Treiber: i915
DRM:     /dev/dri/card1
Render:  /dev/dri/renderD128
```

Belege: `lspci -nnk`, `/dev/dri/by-path`,
`/sys/class/drm/card1/device/driver`.

| Connector | Verbindung | Erste Messung | Spätere Host-Messung |
|---|---|---|---|
| DP-1 | connected | enabled, DPMS On | disabled, DPMS Off |
| DP-2, DP-3 | disconnected | disabled, Off | disabled, Off |
| HDMI-A-1 bis HDMI-A-3 | disconnected | disabled, Off | disabled, Off |

Spätere Host-Messung: **2026-11-14 00:58:46 CET**.

DP-1: EDID 256 Bytes, Hersteller `ACI`, Modell `VG248`, detaillierter Modus
1920×1080. EDID-SHA-256:

```text
958965c347deac54eed45598087870390a0167f806657f1a99655916d63aa197
```

Keine Seriennummern ausgegeben. Unterstützte EDID-Modi sind kein Beweis eines
bestimmten aktuell gescannten Modus.

`~/.config/kwinoutputconfig.json` enthält 1920×1080-Konfigurationen,
Zwei-Ausgang-Anordnungen bei x=0 und x=1920 sowie Ein-Monitor-Anordnungen.
Das belegt gespeicherte Konfigurationen, keine aktuelle Zwei-Monitor-Ausgabe.

Ursache des Wechsels DP-1 von enabled/On zu disabled/Off **nicht nachgewiesen**.
Kein Beweis eines Gamescope-Fehlers. `kscreen-doctor -o` lieferte keine
Monitorinformationen und brach ab. Keine Sessionvariablen geraten/verändert.

## G. Architektur des aktuellen Hybrid-Focus-Prototyps

Tatsächliche Struktur:

```text
prototype/hybrid-focus/
├── src/bazzite_hybrid_focus/
│   ├── model.py
│   ├── controller.py
│   ├── inputplumber.py
│   ├── protocol.py
│   ├── server.py
│   └── client.py
├── bin/                       drei Programme
├── systemd/                   User-Service
├── inputplumber/              Desktop-Profil
├── applications/              zwei Launcher
├── decky/BazziteHybridFocus/   Backend und Frontend-Quellen
├── install-user.sh
└── uninstall-user.sh
```

Installer/Deinstaller liegen direkt dort, nicht in eigenen install/uninstall-
Verzeichnissen. `__init__.py` ist zusätzlich vorhanden.

### Zustände und Ziele

`game`/`desktop` sind Enum-Werte, keine konkreten Spiel-, Fenster-, Monitor- oder
Plasma-Sitzungsobjekte. `game` lädt zuvor ermittelte Profilpfade; `desktop` lädt
das Desktop-Profil auf alle erkannten CompositeDevices.

Belege: [model.py](../../prototype/hybrid-focus/src/bazzite_hybrid_focus/model.py),
Zeilen 11–13;
[controller.py](../../prototype/hybrid-focus/src/bazzite_hybrid_focus/controller.py),
Zeilen 115–219.

### InputPlumber

Argumentbasierte busctl-Aufrufe listen CompositeDevices, lesen `Name`,
`ProfileName`, `SourceDevicePaths`, ermitteln Identität über `udevadm info`, lösen
Profilnamen eindeutig auf YAML auf und rufen `LoadProfilePath` auf. Kein eigener
physischer Geräte-Open/Grab im Prototyp; Kontrolle wird InputPlumber überlassen.
Beleg: [inputplumber.py](../../prototype/hybrid-focus/src/bazzite_hybrid_focus/inputplumber.py),
Zeilen 167–230.

### Gleichzeitige Eingabe

Desktop-Profil verlangt nur `keyboard` und `mouse`, kein Gamepad-Ziel. Dies ist
die implementierte Strategie zur Gamepad-Unterdrückung, kein gemessener Beweis.
Keine ausdrückliche Zustellung der emulierten Tastatur/Maus an Monitor 2 oder
ein bestimmtes Plasma-Fenster. Anleitung verlangt manuelles Zeigerparken und
Fokus per Klick.

Belege: [Profil](../../prototype/hybrid-focus/inputplumber/bazzite-hybrid-desktop.yaml),
Zeilen 7–9; [Prototyp-README](../../prototype/hybrid-focus/README.md), Zeilen 89–93.

### Transaktionen und Recovery

Durch Code belegt: alle Originalprofile vor erstem Wechsel auflösen,
Recoveryabsicht vor erstem Laden speichern, Zustandsdatei atomar ersetzen mit
0600, erfolgreich geänderte Geräte rückwärts zurücksetzen, Recovery beim
Start und normalen Serverabschluss versuchen. `controller.py`, Zeilen 32–46,
115–219; [server.py](../../prototype/hybrid-focus/src/bazzite_hybrid_focus/server.py),
Zeilen 100–126.

Grenzen:

- Geräte nacheinander, keine atomare Mehrgeräteoperation auf Hardwareebene.
- Profilpfade statt unveränderlicher Profilkopien gespeichert.
- `status()` prüft keine vollständige tatsächliche Eingabezustellung.
- Kein expliziter Subprozess-Timeout für Profil-Ladeaufrufe im Adapter.
- Teilweise Wirkung eines fehlgeschlagenen Ladeaufrufs ist durch Tests nicht abgesichert.
- Hotplug/Pfadwiederverwendung nicht durch stabile Geräteidentität abgesichert.

### Socket und Start-Race

Verzeichnis 0700, Socket 0600, UID-Prüfung SO_PEERCRED, vier erlaubte Kommandos,
4096-Byte-Limit, Empfangstimeout, serielle Verarbeitung und Transition-Lock.
Server stellt zuerst Profile wieder her und erstellt danach den Socket.
`Type=simple`; Installer/CLI warten nicht auf Bereitschaft. Client versucht
connect einmal.

Schlussfolgerung aus Code: sofortige Statusabfrage kann vor Socket-Erstellung
scheitern. Das erklärt eine mögliche Start-Race, beweist aber nicht jeden
früheren Statusfehler. Belege: server.py Zeilen 93–106;
[client.py](../../prototype/hybrid-focus/src/bazzite_hybrid_focus/client.py),
Zeilen 10–20; [Unit](../../prototype/hybrid-focus/systemd/bazzite-hybrid-focus.service),
Zeilen 6–12.

### Familien, Glyphen und UI

Vendor 045e → Xbox, 054c → PlayStation, 057e → Nintendo; unbekannte, fehlende oder
gemischte Familien → neutral. `model.py`, Zeilen 34–64.
Decky zeigt Familiennamen als Text. Keine eigenen passenden Button-Glyphen oder
grafischen Confirm/Back-Prompts implementiert.
[Frontend](../../prototype/hybrid-focus/decky/BazziteHybridFocus/src/index.tsx),
Zeilen 25–30 und 80–89.

Vorhanden: Decky-Panel mit Zielanzeige, Toast nach Decky-Aktion, zwei Launcher,
CLI. Nicht vorhanden: dauerhaftes Plasma-Fokusoverlay, globale Rückmeldung bei
jedem CLI-/Launcher-Wechsel, Chord, automatische Monitor-/Fensterfokussierung.

### Installation/Deinstallation

Alle 14 verglichenen installierten Dateien entsprechen Repository oder korrekt
gerenderter Vorlage: sieben Module, Profil, drei Programme, Unit, zwei Launcher.
Vorhandene pycache-Dateien nur aufgelistet; Status mit Bytecodeunterdrückung.
Kein Plugin am dokumentierten Ziel `~/homebrew/plugins/BazziteHybridFocus`;
Installation anderswo nicht nachgewiesen.

Rollback nicht vollständig garantiert: Deinstaller ignoriert Fehler bei
`focusctl game` und `systemctl disable --now` und entfernt trotzdem Dateien.
Keine Sicherung vorher vorhandener gleichnamiger Dateien; Decky separat zu
entfernen. [Deinstaller](../../prototype/hybrid-focus/uninstall-user.sh), Zeilen 11–20.

### Display/Compositor

Keine Connector-Konfiguration, KWin-Regel, Displayselector, Gamescope-Launcher,
zusätzliche SDDM-Sitzung, zweite Plasma-Sitzung oder Plasma-Arbeitsfläche im
normalen Gaming Mode implementiert. Prototyp-README Zeilen 150–158 bestätigt
den begrenzten Umfang.

## H. Was nachweislich funktioniert

Aktuell gemessen:

- GitHubauth und Repository-Lesezugriff; lokaler/Remote-HEAD identisch; Worktree sauber.
- Intel-GPU/i915 erkannt; aktive KDE-Wayland-Sitzung.
- Steam, InputPlumber, SSH und KRDP laufen als Prozesse beziehungsweise Dienste.
- Installierte Prototypdateien stimmen mit untersuchtem Quellstand überein.
- Gespeicherte KWin-Zwei-Monitor-Konfigurationen existieren.

Nur durch Code belegt, nicht hardwarevalidiert: Zustandsmodell, Profilwechsel/
Recoveryversuche, Protokoll-Allowlist/Zugriffsschutz, Familienklassifikation,
Decky-Oberfläche.

Historischer HP-Beleg: Besitzer bestätigte ISO Build #4, Installation und
Gaming-Mode-Bildausgabe nach Neustart über E9173-DisplayPort. Kein heutiger Test.
[README](../../README.md), Zeilen 9–45. Frühere gemeldete Dell-Erfolge im normalen
Gaming Mode in dieser Sitzung nicht erneut getestet.

## I. Was nachweislich noch nicht funktioniert

1. `focusctl status` erreicht keinen Socket, Exit 3.
2. Hybrid-Dienst inactive/dead, letzter Hauptprozess Exit 0/SUCCESS.
3. `kscreen-doctor -o` ohne verwertbare Ausgabe, SIGABRT.
4. Zweite aktuell verbundene physische Anzeige nicht in DRM-Messung vorhanden.

Keine bewiesenen Funktionsfehler daraus ableiten: zehn Zyklen, Leakagefreiheit
und erfolgreicher Nested-Abschluss **nicht nachgewiesen**. Langfristiger
Hybridbetrieb nicht implementiert und **nicht nachgewiesen**.

## J. Dokumentiertes, aber noch nicht implementiertes Verhalten

Die damalige Spezifikation beschreibt zusätzliche Plasma-geführte Sitzung mit
nested Gamescope, keine fertig implementierte Erweiterung des direkten Gaming
Mode. Fehlend: Sitzungseintrag/Wrapper, stabile Monitorwahl, Konfiguration und
Validierung, Fensterplatzierung, Steam-/Gamescope-Lebenszyklus, Hotplug/Fallback,
Chord, dauerhaft erreichbares Desktop-Rückkehrcontrol, umfassende Diagnose.

Beleg: [Design](../superpowers/specs/2026-11-11-hybrid-gaming-mode-design.md),
Zeilen 148–238 und 240–338.

Damals offene Architekturentscheidung: Benutzerziel normaler Gaming Mode plus
Plasma gegenüber spezifizierter Plasma-Nested-Architektur; nicht gleichsetzen.
Die nachfolgende Stufe 2 entschied das Endziel ausdrücklich zugunsten des normalen
Gaming Mode; Machbarkeit bleibt offen (siehe Vorspann).

## K. Annahmen, Widersprüche, veraltete Dokumentation

| Aussage | Kategorie | Bewertung |
|---|---|---|
| Beide Monitore aktuell angeschlossen | Fehlender Beleg | Nur DP-1 connected |
| Normaler Gaming Mode plus Plasma funktioniert | Technisch unbekannt | Kein Implementierungs-/Laufzeitbeleg |
| Profilwechsel verhindert jede Spieleingabe | Hypothese | Tastatur-/Mausfokus und Steam Input prüfen |
| Zielstatus entspricht Routing | Unbewiesene Annahme | Gespeichertes Ziel/Geräteliste statt Zustellprüfung |
| Primary child shut down benennt Ursache | Unzulässige Schlussfolgerung | Vollständiger damaliger Ablauf fehlt |
| Controller glyphs bedeutet echte Glyphen | Widerspruch zur Umsetzung | Familiennamen angezeigt |
| Deinstallation garantiert Ausgangszustand | Durch Code widerlegte Garantie | Restorefehler ignoriert |
| Type=simple bedeutet Socket bereit | Falsche Bereitschaftsannahme | Socket erst nach Recovery |
| validation-2026-11-08 beschreibt aktuelle Eingaben | Veraltete Momentaufnahme | Revision 1/Legacy-Payload gegenüber aktueller Revision 2 |
| Planaufgaben alle noch offen | Veralteter Planstatus | Offene Checkboxen trotz vorhandener Komponenten |

Weitere Unstimmigkeiten: Plan Zeile 29 fordert Diagnose bei zero/more-than-one
CompositeDevice, Code verarbeitet mehrere gemeinsam (`controller.py` 117–147).
Globale Wechselrückmeldung fehlt für CLI/Launcher. Hotplugziel „Gamescope
beenden/anhalten und Spiel erhalten“ ohne konkrete Architektur unbewiesen.
Historisches Validierungsdokument bleibt nützlich, ist keine aktuelle Anleitung.

## L. Risiken

| Bereich | Risiko/offene Grenze |
|---|---|
| Gamescope | Nested-Start, Backend, Frame-Pacing und Lebenszyklus auf Dell nicht vollständig belegt |
| Steam Gaming Mode | Normaler Wrapper verändert Portal-/Sessionumgebung; kein nachgewiesener Plasma-Unterbau |
| KWin/Plasma/Wayland | Virtuelle Tastatur/Maus nicht automatisch am gewünschten Fenster |
| DRM/zwei Monitore | Zweiter connected-Ausgang fehlt; Ownership/Leases im Fehlerzustand nicht gemessen |
| InputPlumber | Aktuell kein CompositeDevice; reale Wechsel/Berechtigungen nicht prüfbar |
| Fokus | Gespeichertes Ziel kann von Routing abweichen |
| Leakage | Fehlendes Gamepad-Ziel schließt Tastatur/Maus im Spiel nicht aus |
| Mehrere Controller | Sequentielle Zwischenzustände, keine hardwareweite Atomarität |
| Glyphen | Nur Vendorfamilientext; Drittanbieter/Betriebsmodi nicht validiert |
| Installation | Überschreibt ohne Backup; Reinstall aktualisiert Dateien bei bestehendem Dienst |
| Rollback | Löscht trotz Restorefehler; Decky separat |
| HP-Referenz | Dell/Revision 2 darf nicht als Build-#4-Revalidierung gelten |
| Build/Release | PR/Main-Push kann Containerworkflow starten; ISO manuell |
| Provenance | Build #4 nicht vollständig digestfixiert; Rekonstruktion nicht garantiert |
| ISO-Signatur | continue-on-error: true; Workflowerfolg beweist keine Signatur |

Belege: `/usr/bin/gamescope-session-plus` 13–30 (Portal-/Displayumgebung);
`/usr/share/gamescope-session-plus/gamescope-session-plus` 248–268
(--prefer-output); [.github/workflows/build.yml](../../.github/workflows/build.yml)
3–12 (Trigger); [build-disk.yml](../../.github/workflows/build-disk.yml) 4–5,
112–114 (manuell/Signierfehlerbehandlung).

## M. Ursachenbaum schwarzer zweiter Monitor

Ausgangspunkt: frühere Benutzerbeobachtung schwarz im Gaming Mode, beide im
Desktop nutzbar; heute nicht reproduziert.

| Zweig | Belegstand | Fehlende Messwerte | Falsifikation |
|---|---|---|---|
| Physisch nicht erkannt | Heute außer DP-1 disconnected | damaliger Anschluss/EDID/Kabel/Monitorzustand | Zweiter Connector im Fehler connected mit EDID |
| Gamescope wählt nur einen Ausgang | Spezifikation; Wrapper --prefer-output | damaliges Backend/Connectorlog/KMS | Zwei aktive Ausgänge im damaligen Gamescope |
| Gaming-Sitzung startet kein Plasma | Sitzungseintrag startet Gamescope-Wrapper | damalige Prozesse/Sitzung | KWin/Plasma bedienen tatsächlich zweiten Ausgang |
| DRM-Master-/Lease-Konflikt | Hypothese | Besitzer/Leases/Fehler | Saubere Ownership trotz schwarzem Ausgang |
| KWin endet beim Wechsel | Hypothese | Sitzungs-/KWin-Verlauf | KWin bleibt aktiv und bedient Ausgang |
| Layout/Energiesparen | Hypothese; heutiger DP-1 wechselte Off | Layout-/Power-Zeitverlauf | enabled/On ohne nutzbares Bild |
| Treiber/Link/Modeset | Hypothese | i915-/DRM-Logs im Fehler | Erfolgreicher Link/Modeset ohne relevante Fehler |
| Hybrid-Focus verursacht Displayfehler | Kein Beleg | zeitliche Korrelation | Fehler ohne laufenden Fokusdienst |

**Keine Hypothese als historische Ursache bewiesen.** Installierte Gamescope-Doku
unterscheidet embedded DRM/KMS und nested unter Desktop (`/usr/share/doc/terra-gamescope/README.md`,
3–14), beweist keine lokale Ursache.

Controller-Routing und Multi-Monitor-Ausgabe sind getrennte Probleme. Prototyp
adressiert nur ersteres; „Desktop 2“/„Hybrid Display Control“ sind kein Displaybeleg.

## N. Bewertung vorhandener Tests

Statisch 54 Testmethoden in acht Dateien gezählt:

| Bereich | Zahl | Aussagekraft |
|---|---:|---|
| Controller | 8 | Sequenzen/Zustandsdatei mit FakeAdapter |
| InputPlumber | 11 | argv/Parsing/Auflösung/Identität/Profiltext |
| Modell | 8 | Zustände/Vendorfamilien |
| Protokoll | 7 | Requests/Fehler |
| Service | 7 | Socket/Lock-Verträge, überwiegend Fakes |
| Installer | 5 | Temporärverzeichnisse, gemocktes systemctl |
| Decky | 6 | Quelltext/AST/Manifest |
| Diagnose | 2 | Künstliche Kommandos/begrenzte Ausgabe |

**Keine Tests ausgeführt:** mehrere erzeugen Dateien oder führen Installer aus.
Fünf geschützte SHA-256-Vergleiche aus
[test_build_provenance.py](../../tests/test_build_provenance.py), 105–121,
separat lesend ausgewertet, alle identisch.

Lücken: reale InputPlumber-Semantik/Grabs; Keyboard-/Mouse-Leakage; zehn Zyklen;
Mehrgerätezwischenzustände; Hotplug/Pfadwiederverwendung; Uninstall-Restorefehler;
nachträglich geänderte Profilinhalte; Startbereitschaft; unterschiedliche defekte
State-JSON-Formen; fragmentierte Requests; reale Decky-Ausführung/Glyphen;
Monitor-/EDID-Auswahl und Compositorintegration. Aktuell „alles bestanden“:
**nicht nachgewiesen**.

## O. Historischer Entwurf AGENTS.md — keine Datei in Stufe 1

Vorgeschlagener damaliger Inhalt:

```markdown
# Arbeitsregeln

## Auftrag und Freigaben
- Nur-Lese-Diagnose, Dateiarbeit, Hardwaretest und Veröffentlichung unterscheiden.
- Freigabe gilt nur für benannten Umfang; Pläne/Skills sind keine Ausführungsfreigabe.
- Bei unklarer Zustandswirkung stoppen und konkrete Änderung benennen.

## Geschützte Hardware-Referenz
- HP t740 / V1756B / E9173 / direkter E9173-DP / ISO Build #4 bleibt Referenz.
- Identität aus README; Dell separat mit Hardware/Image/Modus erfassen.
- Keine Übertragung von Hardwarebelegen auf andere Geräte oder Builds.

## Git und geschützte Dateien
- Pfad, Branch, HEAD, Upstream, Worktree vorher prüfen; Benutzeränderungen erhalten.
- main und Build-/Session-/Lock-/Provenancedateien nur ausdrücklich passend ändern.
- Kein Commit/Push/Merge/PR/Workflow/Release ohne Freigabe.
- Netzwerklesen erlaubt keine Git-Schreiboperationen.

## Diagnose und Hardwaretests
- Nur-Lese erzeugt auch keine Exporte/Caches/Temporärdateien.
- Befehlswirkung prüfen; keine Geräteöffnung oder exklusive Übernahme.
- Keine Sessionvariablen raten/setzen, keine fremde Sitzung übernehmen.
- Rechte-/Sandboxgrenzen dokumentieren.
- Zustandsändernde Tests brauchen Freigabe und Rückweg.

## Produkt und Architektur
- Normalen Gaming Mode, nested und vollständigen Hybridbetrieb getrennt behandeln.
- Fokus und Displaysteuerung getrennt validieren.
- Keine Exklusivität aus Profilname/Statusfeld ableiten.

## Belege
- Tatsachen/Codefunktion/Absicht/Hypothese/fehlenden Beleg kennzeichnen.
- Zeit, Hardware, Commit, Image, Version, Befehl, Exitcode, Grenzen erfassen.
- Nur aktuelle Ergebnisse als bestanden melden; Abschlussstatus/Änderungsumfang prüfen.

## Build und Release
- Container und ISO getrennt autorisieren; ISO nur ausdrücklich manuell.
- Locks/Digests/Prüfsummen/Provenance nicht still erneuern.
- Build-Erfolg ersetzt Signatur-/Hardwareprüfung nicht.

## Geheimnisse
- Keine Tokens/Schlüssel/Gerätecodes/Passwörter/Umgebungsdumps ausgeben.
- Journale/EDID/Diagnosen redigieren.

## Werkzeuge
- Superpowers für Diagnose/Verifikation; keine Umsetzung gegen Auftragsgrenzen.
- Context7 nur konkrete restliche Versions-/API-Frage mit Version/Quelle.
- REA nur freigegebenes Artefakt und anders nicht beantwortbare Frage.
- Fehlende Werkzeuge nicht ungefragt installieren.

## Skills
- bazzite-hybrid-diagnostics: Bestandsaufnahme.
- hybrid-focus-hardware-validation: freigegebener Hardwaretest.
- bazzite-build-release-safety: Vorbereitung/Freigaben.
```

Globale Grenzen gehören in AGENTS, konkrete Befehle/Zyklus-/Releaseprotokolle in
Skills/Referenzen. Dieser Entwurf ist nicht identisch mit dem anschließend
autorisierten Stufe-2-Inhalt.

## P. Historischer Blueprint bazzite-hybrid-diagnostics

| Feld | Entwurf |
|---|---|
| Name | bazzite-hybrid-diagnostics |
| Trigger | Diagnose Bazzite-Hybrid/Gamescope/Plasma/DRM/InputPlumber/Fokus, keine automatische Reparatur |
| Zweck | Reproduzierbarer Istzustand und falsifizierbare Hypothesen |
| Geltung | Steam/Gamescope, KWin/Plasma/Wayland, DRM/Monitore, Controller/InputPlumber, Userdienste/Journale |
| Nicht-Ziele | Implementierung, Hardwareabnahme, Profiländerung, Build/Release |
| Sicherheitsgrenzen | AGENTS, keine Geräteöffnung/Sessionübernahme/implizite Änderungen |
| Lesend | Git/Pakete/sysfs/Prozessnamen/Konfiguration/Status/begrenzte Logs/geprüfter status-Request |
| Freigabe | Export, Instrumentierung, Privilegien, Reproduktion, Start/Stop/Konfiguration |
| Verboten | Unautorisierte Reparatur, Grabs, Sessionvariablenmanipulation, Secrets |
| Referenzen | README, Design, Dell-Checkliste, Provenance, gemeinsame Befehls-/Belegreferenz |
| Hilfsmittel | Später read-only-snapshot.py: stdout, keine lokalen Imports/Caches/automatisches sudo |
| Eingaben | Auftrag, Hardware, Commit, Modus, Fehlerzeitraum, Messumfang |
| Ausgabe | Inventar, Soll/Ist, Grenzen, Ursachenbaum, nächster Schritt |
| Belegformat | Zeit, Hardware, Commit/Image, argv, Host/Sandbox, Exit, redigierte Ausgabe, Kategorie |
| Redaktion | Allowlist; keine Umgebungen/EDID-Seriennummern/fremden Anwendungsargumente |
| Abbruch | Unklare Wirkung, Geräteöffnung, GUI-Absturz, unbekannte Sitzung, nötige Änderung |
| Validierung/Rollback | Quelle gegen Laufzeit, Git vorher/nachher; Nebenwirkung stoppen, nicht automatisch bereinigen |
| Struktur | SKILL.md, references/command-map.md, gemeinsame Verweise |

KScreen-SIGABRT als konkrete Grenze dokumentieren: keine GUI-Abfrage über SSH
ohne belegten geeigneten Kontext; Kontext nicht erraten.

## Q. Historischer Blueprint hybrid-focus-hardware-validation

| Feld | Entwurf |
|---|---|
| Name | hybrid-focus-hardware-validation |
| Trigger | Ausdrücklich autorisierte Hardwarevalidierung auf benannter Hardware/im benannten Modus |
| Zweck | Abnahme von Exklusivität, Rückkehr, Wiederherstellung |
| Geltung | Zunächst Dell 5080/UHD630, zwei nachgewiesen aktive Monitore |
| Nicht-Ziele | Endarchitekturbeweis durch nested, HP-Revalidierung, Implementierung |
| Sicherheit | Physische Tastatur/Maus, gesicherte Arbeit, geprüfter Rückweg, autorisierter Umfang |
| Lesend | Vorher/Nachher, Profile, Dienst/Socket, Versionen, Logs/Hashes |
| Freigabe | Installation, Dienste/Steam/Gamescope/Profil/Modus, Export, Uninstall, Reboot |
| Verboten | Ungeplante Fixes, normaler Gaming Mode ändern, HP-Installation, Build/Release |
| Referenzen | Dell-Checkliste, README, bekannte Risiken, Controller-/Versionsmatrix |
| Hilfsmittel | Zyklus-CSV, Aktionsliste, Diagnosemanifest, manuelle Recoverykarte |
| Eingaben | Geräte, Controllerfamilie/Verbindung, Image/Commit/Modus/Spiel, Originalprofile/Freigaben |
| Ausgabe | Baseline/Nested/Fokus/Rollback separat, PASS/FAIL/BLOCKED |
| Belegformat | Zykluszeit/Übergänge/Aktion/beide Ziele/Profile/Sichtbarkeit/Ergebnis |
| Redaktion | Keine Seriennummern/privaten Inhalte; Logs prüfen |
| Abbruch | Leakage, Kontrollverlust, fehlender Monitor, degraded, Rückkehr unerreichbar, Software-Rendering |
| Validierung | Zehn vollständige Zyklen, beide Ziele, gehaltene Tasten/Übergänge |
| Rollback | Originalprofile bestätigen; keine blinde Deinstallation bei Fehler; autorisierte Rückkehr/Baseline |
| Struktur | SKILL.md, references/acceptance.md, templates/cycles.csv, templates/run.md |

Weitere Kriterien: Zeiger/Rand/Fadenkreuz ohne Wechsel; Gamepad/Keyboard/Mouse-
Leakage separat; Rückkehr controllerbedienbar; jede Familie eigener Beleg;
Familienname getrennt von Button-Glyphen; Export/Rollback eigene Schritte;
Nested-Erfolg nur in diesem Modus gültig.

## R. Historischer Blueprint bazzite-build-release-safety

| Feld | Entwurf |
|---|---|
| Name | bazzite-build-release-safety |
| Trigger | Änderung an Container/ISO/Payloadlock/Workflow/Provenance/Publikation vorbereiten oder prüfen |
| Zweck | Referenz bewahren, Veröffentlichungsstufen nachvollziehbar freigeben |
| Geltung | Quellen/Workflows/Digests/Signaturen/Prüfsummen/Releases |
| Nicht-Ziele | Automatische Publikation, Hardwarebeweis durch Build, unbekannte Build-#4-Eingaben rekonstruieren |
| Sicherheit | HP-Referenz, Dell separat, keine automatischen Stufenübergänge |
| Lesend | Diffs/Trigger/Logs/Metadaten/Digest-/Checksum-/Signaturprüfung ohne Installation/Schreibexport |
| Freigabe | Dateiarbeit/Lockrefresh/Build/Push/Merge/Workflow/ISO/Signierung/Release |
| Verboten | Stilles Tagverschieben, historische Belege ersetzen, ISOautomatik/Secrets |
| Referenzen | README-Baseline, Provenance, Lock/Version, Workflows, Containerfile/Installer |
| Hilfsmittel | Freigabevorlage, Provenancemanifest, Schutzhashliste, Artefaktcheckliste |
| Eingaben | Commit/sauberer Branch/Stufe/Digests/Version/Zielhardware/Rollbackartefakt |
| Ausgabe | Stufenreview mit Freigaben/IDs/Belegen/offenen Gates |
| Belegformat | Commit/Workflow-ID/Eingabedigests/Ausgabedigest/ISO-SHA/Signatur/Hardware separat |
| Redaktion | Nur öffentliche Schlüssel/Fingerprints; keine privaten Keys/Credentials |
| Abbruch | Dirty Worktree, unbekannter Payload, Versionskonflikt, Signaturfehler, fehlende Freigabe, Schutzdatei außerhalb Scope |
| Validierung | Container, Publikation, Payloadwahl, ISO, Hardware separat |
| Rollback | Gutes Deployment/getestetes Artefakt erhalten; Ausführung nur autorisiert |
| Struktur | SKILL.md, references/stage-gates.md, templates/release-review.md, templates/provenance.json |

Workflowerfolg allein genügt wegen tolerierter Teilschrittfehler nicht als Signaturbeleg.

## S. Historische gemeinsame Strukturempfehlung

```text
AGENTS.md
.agents/
├── references/
│   ├── safety-and-authorization.md
│   ├── hardware-baselines.md
│   ├── evidence-format.md
│   ├── command-effects.md
│   └── known-limitations.md
├── templates/
│   ├── diagnostic-report.md
│   ├── hardware-run.md
│   └── focus-cycles.csv
└── skills/
    ├── bazzite-hybrid-diagnostics/
    │   ├── SKILL.md
    │   └── references/command-map.md
    ├── hybrid-focus-hardware-validation/
    │   ├── SKILL.md
    │   └── references/acceptance.md
    └── bazzite-build-release-safety/
        ├── SKILL.md
        └── references/stage-gates.md
```

AGENTS: globale Grenzen/Routing; gemeinsame Referenzen: Belege/Befehlswirkungen/
Hardwareidentitäten; Skills: Trigger/Ablauf/Abbruch/Gates; Vorlagen: Protokollfelder;
Skripte erst später prüfen. Keine Referenzsammlung ist Ausführungsfreigabe.
Historische Baselines referenzieren, keine zweite unabhängig gepflegte Wahrheit.
Die spätere Stufe 2 beschränkte gemeinsame Referenzen auf drei Dateien unter
docs/agent-guidance; obige Struktur wurde in Stufe 1 nicht erstellt.

## T. Kleinster nächster reversibler Diagnoseschritt

Zuerst fehlenden zweiten verbundenen Ausgang klären, ohne Sitzung/Konfiguration:
Benutzer benennt Monitore/physische Anschlüsse; dann zeitgestempelt status,
enabled, dpms, modes, EDID genau dieser Connectoren lesen, Sitzung/Prozessnamen
korrelieren. So „nicht erkannt“ von „erkannt, aber nicht genutzt“ trennen.
Kein Gamescope-Start/Fokuswechsel erforderlich. Gaming-Vergleich erst mit
belegter Zwei-Monitor-Lage und eigener Freigabe.

## U. Benötigte Informationen/Freigaben

- Sind zwei Monitore tatsächlich physisch angeschlossen und eingeschaltet?
- Welcher Monitor an welchem Anschluss/Adapter, welcher Gaming-Monitor?
- Welcher Controller/Verbindung aktuell vorhanden?
- Vollständige frühere Nested-Ausgabe bereits als Datei vorhanden?

Fortsetzung benötigte neuen ausdrücklichen Auftrag. Damals zusätzlich zu
entscheiden: Plasma-nested als Ziel oder normaler Gaming Mode plus Plasma auf
Machbarkeit untersuchen. Diese Architekturfrage wurde erst durch Stufe 2 im
Sinne des normalen Gaming Mode entschieden, nicht technisch validiert.
Core-Dump-Löschung, Dienste, neue Exporte, Tests/Dateien waren nicht freigegeben.

## V. Ausgeführte Befehle und Messgrenzen

S = Sandbox; H = ausdrücklich freigegebener Hostzugriff. Bei kombinierten
Shell-Aufrufen ist nur der Gesamtcode erfasst; keine Einzelcodes erfunden.
Wiederholte identische Lesebefehle zusammengefasst.

### Repository/GitHub

| Befehl | Kontext | Exit/Einschränkung |
|---|---|---|
| pwd | S | 0 |
| find .. -name AGENTS.md -print | S | 0, kein Treffer |
| Vorfahrenprüfung mit test -f, gegebenenfalls cat | S | 0, keine Dateien |
| git --no-optional-locks status --short --branch | S | 0, mehrfach |
| git status --short --branch | S | 0 |
| git branch --show-current | S | Leseblock 0 |
| git rev-parse HEAD | S | Leseblock 0 |
| git rev-parse --show-toplevel | S | Leseblock 0 |
| git remote -v | S | Leseblock 0 |
| git branch -vv | S | Leseblock 0 |
| git log --oneline --decorate -n 20 | S | Leseblock 0 |
| git diff --stat | S | Leseblock 0 |
| git diff | S | Leseblock 0 |
| git diff --cached | S | Leseblock 0 |
| git ls-files | S | Leseblock 0 |
| git worktree list --porcelain | S | Leseblock 0 |
| git ls-files --others --exclude-standard | S | 0, mehrfach |
| git status --short --ignored | S | Leseblock 0 |
| git diff 4f135d0..HEAD --stat | S | Leseblock 0 |
| git diff 4f135d0..HEAD -- Containerfile system_files image-lock.json .github/workflows installer build_files | S | 0, leer |
| git diff 9d27d33..HEAD -- Containerfile system_files image-lock.json .github/workflows installer build_files | S | 0, leer |
| git diff --exit-code | S | 0 |
| git diff --cached --exit-code | S | 0 |
| git ls-remote origin refs/heads/design/hybrid-gaming-mode | S → H | 128 DNS → 0 |
| command -v gh | S | 0 |
| gh auth status | S → H | 1 → 0 |
| gh api user --jq .login | S → H | 1 Netzwerk → 0 |
| gh repo view Nanja-at-web/bazzite-t740-e9173 --json nameWithOwner,url,defaultBranchRef | S → H | 1 Netzwerk → 0 |
| gh pr list --repo Nanja-at-web/bazzite-t740-e9173 --state open --head design/hybrid-gaming-mode --json number,title,url,headRefName,baseRefName | S → H | 1 Netzwerk → 0 |

### System/Laufzeit

| Befehl | Kontext | Exit/Einschränkung |
|---|---|---|
| cat /etc/os-release | S | 0 |
| uname -a | S | 0 |
| bootc status | S | 1, Root erforderlich; nicht wiederholt |
| rpm-ostree status | S → H | 1 Bus → 0 |
| lscpu | S | 0 |
| free -h | S | 0 |
| cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name /sys/class/dmi/id/chassis_type | S | 0 |
| lspci -nnk | S | 0 |
| ls -l /dev/dri /dev/dri/by-path | S → H | 2 unsichtbar → 0 |
| rpm -q gamescope inputplumber plasma-workspace kwin kscreen xrdp openssh-server | S | 2, gamescope/xrdp Paketnamen nicht installiert |
| ps -eo pid,ppid,uid,comm | S → H | 0 → 0, S eingeschränkt |
| loginctl list-sessions --no-legend | S → H | 1 Bus → 0 |
| systemctl status inputplumber.service sshd.service xrdp.service --no-pager -l | S → H | 1 Bus → 4, xrdp fehlt |
| systemctl --user status bazzite-hybrid-focus.service --no-pager -l | H | 3, inaktiv |
| systemctl --user show bazzite-hybrid-focus.service | H | 0 |
| journalctl --user -u bazzite-hybrid-focus.service -b --no-pager | H | 0, keine Einträge |
| PYTHONDONTWRITEBYTECODE=1 bazzite-hybrid-focusctl status | H | 3, Socket fehlt |
| busctl --system --auto-start=no tree org.shadowblip.InputPlumber --list | H | 0, keine CompositeDevices |
| journalctl -u inputplumber.service -b --no-pager -n 100 | H | 0, keine Einträge |
| loginctl show-session 3 -p Type -p Class -p State -p Desktop -p Service -p Active -p Seat -p Remote | H | 0 |
| kscreen-doctor -o | H | 134/SIGABRT, automatischer Core-Dump |
| rpm -qa '*gamescope*' '*krdp*' | H | Leseblock 0 |
| command -v gamescope | H | Leseblock 0 |
| readlink -f /usr/bin/gamescope | H | Leseblock 0 |
| rpm -qf /usr/bin/gamescope | H | Leseblock 0 |
| cat /usr/share/t740/build-info.json | H | Leseblock 0 |
| journalctl --user -b --no-pager -n 100 --grep=gamescope\|Primary child shut down | H | 1, keine Einträge; einzelnes argv-Argument mit Pipezeichen, keine Shell-Pipeline |
| systemctl --user status plasma-krdp_server.service --no-pager | H | 4, Unit fehlt |
| coredumpctl --no-pager list /usr/bin/kscreen-doctor | H | 0, Core vorhanden |
| readlink -f /home/<local-user> | S | Leseblock 0 |
| date --iso-8601=seconds | S | Leseblock 0 |
| find /home/<local-user> -maxdepth 2 -type f (Namensfilter *hybrid* oder *gamescope*.log) -print | S | Leseblock 0, kein Treffer |

Letzter find-Aufruf, mit redigiertem lokalem Benutzernamen:

```bash
find /home/<local-user> -maxdepth 2 -type f \( -iname '*hybrid*' -o -iname '*gamescope*.log' \) -print
```

### Datei-/Quelltextlesungen

Alle folgenden Leseblöcke in S mit Gesamt-Exit 0; teilweise mehrfach:

- cat der drei verwendeten Superpowers-SKILL.md und using-superpowers/references/codex-tools.md.
- wc -l der sieben Pflichtdokumente, Module und Hybrid-Testdateien.
- nl -ba README.md, ergänzend 350–470.
- nl -ba docs/hybrid-focus-dell-test.md.
- nl -ba prototype/hybrid-focus/README.md.
- nl -ba docs/build-provenance.md, ergänzend 86–130.
- nl -ba docs/validation-2026-11-08.md.
- nl -ba Design-Spezifikation, ergänzend 1–110 und 110–416.
- nl -ba Implementierungsplan, ergänzend 1–38 und 38–320.
- nl -ba aller sieben Module unter prototype/hybrid-focus/src/bazzite_hybrid_focus/.
- nl -ba aller drei Programme unter prototype/hybrid-focus/bin/.
- nl -ba Unit, Installer, Deinstaller, Desktop-Profil, beider Launcher.
- nl -ba Decky main.py, plugin.json, package.json, rollup.config.js, tsconfig.json, .gitignore, src/index.tsx.
- nl -ba aller acht tests/test_hybrid_focus_*.py.
- rg -n 'hybrid|sha256|workflow|polaris|Protected|protected' tests/test_build_provenance.py.
- nl -ba tests/test_build_provenance.py, 100–135.
- nl -ba system_files/etc/gamescope-session-plus/sessions.d/steam.
- nl -ba .github/workflows/build.yml, 1–120 und 135–240.
- nl -ba .github/workflows/build-disk.yml, 1–100 und 94–155.
- rg --files in installierten Gamescope-/InputPlumber-/Wayland-Verzeichnissen,
  nach relevanten Pfaden gefiltert; Fehler fehlender Suchverzeichnisse unterdrückt.
- nl -ba /usr/share/doc/terra-gamescope/README.md, 1–220.
- rg -n zu Backend/DRM/Output/Sessionumgebung/Gamescope/KWin/Plasma in Gamescope-Skripten.
- nl -ba /usr/share/wayland-sessions/gamescope-session-steam.desktop.
- nl -ba /etc/gamescope-session-plus/sessions.d/steam.
- nl -ba /usr/share/inputplumber/profiles/default.yaml.
- nl -ba /usr/share/inputplumber/profiles/mouse_keyboard_wasd.yaml, 1–150.
- rg -n 'LoadProfile|TargetDevice|ProfileName|intercept|grab|exclusive|D-Bus|profile' /usr/share/doc/inputplumber/README.md.
- nl -ba /usr/share/gamescope-session-plus/gamescope-session-plus, 248–269.
- nl -ba /usr/bin/gamescope-session-plus.
- nl -ba /usr/lib/systemd/user/gamescope-session-plus@.service.
- nl -ba /usr/share/inputplumber/devices/65-generic_gamepad.yaml.
- nl -ba /usr/share/inputplumber/devices/69-ignore_generic.yaml.

Fünf nicht gespeicherte Python-Leseblöcke `python3 -B -`, jeweils Exit 0:

1. Installationsabgleich: Bytes/SHA-256 der 14 installierten Dateien, Vorlagen im
   Speicher gerendert, Baum/Decky-Pfad/Variablenpräsenz/Runtimeeinträge aufgelistet.
2. Grafik/Input: sysfs Status/Modi/EDID gelesen, Modell/Hash berechnet, KWin-JSON
   ohne EDID-/Serialfelder ausgegeben, Inputnamen und Vendor-/Product-IDs gelesen.
3. Statische Tests/Schutz: AST-Zählung, fünf Schutzhashes, lokales Schema gelesen/
   gehasht, Sessionoverride-Pfade, MemTotal, Lockfile-Anfang.
4. Hostabschluss: Zeit/DRM und drei oben aufgeführte Journal-/KRDP-/Core-Aufrufe
   mit separat erfassten Exitcodes.
5. Abschluss: sechs AGENTS-Vorfahren und Runtime geprüft; 0700, UID 1000, leer.

Werkzeugverfügbarkeit durch Filtern bereitgestellter Metadaten geprüft, kein
Shell-Exitcode. Heredoc-Inhalte wurden im ursprünglichen Bericht nach Funktion
und Eingabepfaden dokumentiert, nicht als eigenständige Skriptdateien archiviert.
Das begrenzt eine bytegenaue Rekonstruktion der damaligen Befehlsfolge.

**Protokollgrenzen:** Erste kombinierte Dateilesungen vom Werkzeug gekürzt;
betroffene Dokumentbereiche anschließend gezielt erneut vollständig gelesen.
Kein vollständiges Befehlsprotokoll als Datei angelegt. Journale ohne Einträge;
Dienststatus warnte vor Rotation seit Start. Frühere Ereignisse dadurch nicht
ausgeschlossen. Kein damaliger Live-Rendering-/Fokus-/Zwei-Monitor-Test.

## W. Entscheidungsgrenze am Ende von Stufe 1

Nach ausdrücklicher Freigabe vorbereitbar: AGENTS und drei kurze Skills,
gemeinsame Beleg-/Sicherheitsreferenzen, Diagnose-/Abnahmevorlagen, klarere
Trennung von Fokus und Displayarchitektur.

Zuerst Entscheidungen nötig: normaler Gaming Mode plus Plasma oder Plasma-nested;
tatsächliche Verkabelung; späterer Testumfang; Familienanzeige versus echte Glyphen;
sichere Restorefehlerbehandlung vor Deinstallation.

Weiter verboten: unautorisierte Dateien/Dienste/Profile/Displays/Sitzungen/Builds/
Git/Publikation, besonders HP-Referenz, Polaris, main, Workflows, Lock/Provenance.
Die erste Sitzung endete mit Stopp und Warten auf Freigabe. Dieser historische
Abschluss erteilt keine Freigabe für weitere Maßnahmen.
