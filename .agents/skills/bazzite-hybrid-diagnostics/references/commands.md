# Lesende Befehle und Messgrenzen

Nur innerhalb eines Diagnoseauftrags und nach Wirkungsprüfung verwenden.
Diese Liste ist kein auszuführendes Gesamtskript. Platzhalter erst durch
belegte Werte ersetzen; niemals Sessionvariablen setzen. Keine Umleitungen in
Dateien ohne Exportfreigabe. Jeder Befehl bekommt eigenen Exitcode.

## Repository

```bash
pwd
git --no-optional-locks status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse --show-toplevel
git branch -vv
git remote -v
git diff --stat
git diff
git diff --cached
git ls-files --others --exclude-standard
```

Remote-URLs vor Ausgabe auf eingebettete Zugangsdaten prüfen und redigieren.
`git ls-remote` und `gh repo view` lesen Remoteobjekte, übernehmen aber keine
Daten in den Branch. Authstatus nur ohne Tokens ausgeben. Kein fetch/pull/login.

## System und Grafik

```bash
cat /etc/os-release
uname -a
lscpu
free -h
lspci -nnk
ls -l /dev/dri /dev/dri/by-path
rpm -qa '*gamescope*' '*inputplumber*' '*plasma*' '*kwin*'
```

`gamescope` kann als RPM `terra-gamescope` installiert sein. Paketname und
Programmexistenz getrennt prüfen. `bootc status`/`rpm-ostree status` nur im
gegebenen Rechtekontext und mit dokumentierter Bus-/Autostartwirkung; bei
Privilegien- oder Schreibvorbereitungsanforderung stoppen, kein automatisches sudo.

Unter `/sys/class/drm` nur `status`, `enabled`, `dpms`, `modes`, Geräte-/Treiberlinks
und EDID lesen. EDID lokal für Hersteller/Modell, Modi und Hash auswerten, keine
Seriennummern oder Rohbytes ausgeben. `connected` beweist kein sichtbares Bild.
Aktuellen Modus nicht aus einer Liste unterstützter Modi ableiten.

Bestehende `~/.config/kwinoutputconfig.json` beziehungsweise KScreen-Dateien lesen,
aber Seriennummern/EDID und private Pfade redigieren. Historische Layouts nicht
als aktuellen Ausgangszustand interpretieren. Keine `kscreen-doctor`-Änderungen.
Über SSH ohne geeigneten GUI-Kontext auch `kscreen-doctor -o` auslassen: Audit
2026-11-14 dokumentiert SIGABRT mit automatisch erzeugtem Core-Dump.

## Sitzung und Dienste

```bash
ps -eo pid,ppid,uid,comm
loginctl list-sessions --no-legend
systemctl --user status bazzite-hybrid-focus.service --no-pager -l
systemctl --user show bazzite-hybrid-focus.service -p LoadState -p ActiveState -p SubState -p MainPID -p Result -p ExecMainStatus -p FragmentPath
systemctl status inputplumber.service --no-pager -l
journalctl --user -u bazzite-hybrid-focus.service -b -n 100 --no-pager
journalctl -u inputplumber.service -b -n 100 --no-pager
```

Nur belegte Sitzungs-ID mit `loginctl show-session` und gezielten Eigenschaften
abfragen. Keine vollständigen Prozessumgebungen oder beliebigen argv ausgeben.
KWin, plasmashell, Steam, Gamescope und InputPlumber getrennt zuordnen. Keine
DRM-Gerätenodes zur Ownershipmessung öffnen; unzugängliche Besitzer-/Lease-Daten
als fehlenden Beleg erfassen. Logs vor Weitergabe redigieren.

## InputPlumber und installierter Fokusprototyp

Nur falls InputPlumber bereits läuft:

```bash
busctl --system --auto-start=no tree org.shadowblip.InputPlumber --list
```

Nur tatsächlich gefundene CompositeDevice-Pfade gezielt per `get-property`
(`Name`, `ProfileName`, `SourceDevicePaths`) lesen, ebenfalls ohne Autostart.
`LoadProfilePath` ist eine zustandsändernde Methode und hier nicht erlaubt.
Controller-Metadaten unter `/sys/class/input/input*/name` und `id/{vendor,product}`
lesen. Kein evtest, jstest, libinput-debugging oder Zugriff auf `/dev/input/*`.

Vor CLI-Aufruf installierten Client statisch prüfen. Wenn sein `status`-Pfad
nur liest und keinen Dienst startet:

```bash
PYTHONDONTWRITEBYTECODE=1 bazzite-hybrid-focusctl status
```

Runtimepfad nur aus bereits vorhandener eigener Umgebung verwenden. Fehlt er:
Messgrenze, nicht raten. Verzeichnis-/Socketmodus und bestehende Zustandsdatei
lesen; keine Dateien anlegen. Fehlender Socket kann Inaktivität oder noch
fehlende Bereitschaft bedeuten; zeitlich korrelierte Statusdaten unterscheiden.

Installationsorte aus `prototype/hybrid-focus/install-user.sh` ableiten; XDG-Werte
und gerenderte Vorlagen berücksichtigen. Bytes/Hashes mit `python3 -B` ohne
Produktimport vergleichen. Diagnoseprogramm vor Ausführung auf Cache-/D-Bus- und
Exportwirkungen prüfen. Installer/Deinstaller niemals als Diagnose ausführen.
