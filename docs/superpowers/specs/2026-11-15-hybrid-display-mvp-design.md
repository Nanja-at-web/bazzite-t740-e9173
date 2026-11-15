# Hybrid-Display-MVP unter Plasma Wayland

Datum: 2026-11-15. Status: freigegebene Architektur, dokumentierter Entwurf;
Implementierung und Hardwareabnahme ausstehend.

## Auftrag und Verbindlichkeit

Die Freigabe umfasst ausschließlich dieses Dokument und den
[Implementierungsplan](../plans/2026-11-15-hybrid-display-mvp-implementation.md),
deren statische Prüfung sowie den ausdrücklich beauftragten Review-Patch und
seine temporäre Anwendbarkeitsprüfung. Sie erlaubt keine Produktimplementierung,
schreibenden Produkttests, Starts von Gamescope/Steam/vkcube, Display-, Dienst-
oder Sitzungsänderungen. Alle folgenden Laufzeitabläufe sind zukünftige
Anforderungen, keine Ausführungsfreigaben.

Maßgeblich bleiben [AGENTS.md](../../../AGENTS.md),
[Sicherheitsgrenzen](../../agent-guidance/safety-boundaries.md),
[Belegformat](../../agent-guidance/evidence-format.md) und
[Hardwarebaselines](../../agent-guidance/hardware-baselines.md). Die aktuelle
Architekturfreigabe erlaubt nested Gamescope als begrenztes Display-MVP. Sie
ändert das langfristige Endziel aus den Hardwarebaselines nicht.

## Motivation und Definition

Ein Spiel beziehungsweise Steam Gamepad UI soll einen gewählten Gaming-Monitor
nutzen, während ein zweiter Monitor als eigenständiger Plasma-Arbeitsbereich für
Browser, Terminal und später weitere Anwendungen verfügbar bleibt.

Minimum Viable Product bedeutet die kleinste manuell startbare, reversible und
messbar testbare Version dieser gleichzeitigen Nutzung. Plasma/KWin bleibt
Eigentümer beider physischen Ausgänge. Gamescope ist darin ein verschachteltes
Wayland-Fenster, anschließend manuell auf einem Monitor im Vollbild.

Die Nachweisfolge ist verbindlich: kleiner Grafikclient, beispielsweise vkcube;
erst nach bestandenem Grafikclient-Test Steam Gamepad UI; erst danach ein
benanntes Spiel mit eigenem Hardware-Rendering-Nachweis. Ein Grafikclient-Test
allein erfüllt die vollständige MVP-Abnahme nicht.

## Ziele, Nichtziele und Anti-Ziele

Ziele sind zwei gleichzeitig aktive erweiterte Plasma-Ausgänge, begrenzte
Gamescope-Ausgabe auf dem gewählten Monitor, bedienbarer Desktop auf Monitor 2,
Hardware-Rendering des Spiels und Rückkehr zu vollständig benutzbarem Plasma
ohne Neustart. Der normale Gaming Mode bleibt unverändert.

Nichtziele: Controller-Fokus-Routing, virtuelle Profile, automatische
Fokusumschaltung, Controller-Glyphen, Decky/QAM, OutputManager, Mauszeiger-HUD,
Audioauswahl, automatische Fensterplatzierung, Hotplug-Migration,
Suspend/Resume-Abnahme, automatische Anmeldung, neue Standardsitzung,
systemweite Installation, Container-, ISO- oder Releaseintegration.

Anti-Ziele und unverhandelbare Grenzen:

- Kein zweiter direkter Compositor, der um dieselbe GPU konkurriert.
- Kein Fallback auf den direkten DRM-Modus, auch nicht nach Startfehlern.
- `gamescope-session-plus` darf innerhalb von Plasma weder als MVP-Launcher
  wiederverwendet noch gesourct werden.
- `--prefer-output` wird im nested-MVP nicht zur Fensterplatzierung verwendet.
- OutputManager wird nicht ausgeführt und darf keine force- oder
  Hotplug-Operationen ausführen. Auch vermeintliche Statusfunktionen sind nicht
  als nebenwirkungsfrei vorauszusetzen.
- Keine Shellauswertung benutzergesteuerter Werte; argv als Liste.
- Keine globalen Umgebungsänderungen, geratenen Sessionvariablen,
  Displayreparaturen, automatischen Wiederholungen oder Monitorumschaltungen.
- Keine Signale an vorher vorhandene Steam-/Gamescope-Prozesse. Bei unklarer
  Eigentümerschaft keine automatische Prozessbeendigung.
- Keine Eingabegeräte öffnen, grabben oder Controllerprofile ändern.
- Keine vollständigen Prozessumgebungen oder Roh-EDIDs in Berichten.

## Belegte Ausgangslage und Messgrenzen

### Neuprüfung für diesen Dokumentationsauftrag

Vor Dateierstellung wurden `pwd`, `git status --short --branch`,
`git rev-parse HEAD` und `git worktree list --porcelain` gelesen:

| Feld | Ergebnis |
|---|---|
| Worktree | `/var/home/nanja/bazzite-hybrid-main-integration` |
| Branch | `integrate/main-into-hybrid-gaming-mode` |
| HEAD | `c61d0a4e821cc9984343b70bb471d9320510dc95` |
| Zustand vor Erstellung | sauber; bestehender verknüpfter Worktree |

`gh pr view 8 --repo Nanja-at-web/bazzite-t740-e9173 --json state,isDraft,headRefOid,headRefName,baseRefName,url`
bestätigte [PR #8](https://github.com/Nanja-at-web/bazzite-t740-e9173/pull/8)
als offenen Draft mit diesem HEAD und Zielbranch `design/hybrid-gaming-mode`.
Der PR wird separat behandelt; weder Änderung noch Merge sind freigegeben.

### Übernommene Bestandsaufnahme vom 2026-11-15

Die folgenden Messwerte stammen aus dem vorherigen Nur-Lese-Bericht derselben
Unterhaltung, Messfenster ungefähr 08:43–09:02 CET. Sie wurden für diesen
Dokumentationsauftrag **nicht erneut gemessen**. Der Bericht ist kein zusätzlich
im Repository gespeichertes Messartefakt. Befehle und Bootidentität ermöglichen
die Einordnung, ersetzen aber keine spätere frische Hardwareaufnahme.

| Gegenstand | Übernommener Befund und Quelle |
|---|---|
| Dell | DMI OptiPlex 5080, i5-10500T, rund 15 GiB nutzbarer RAM; DMI/lscpu/free |
| Grafik | UHD 630, PCI `0000:00:02.0`, `8086:9bc8`, i915; `lspci -nnk` |
| OS/Kernel | Bazzite 45.20261105; `7.2.15-ogc1.1.fc45.x86_64`; os-release/uname |
| Deployment | `45.20261105.2-polaris-sdl`; `rpm-ostree status --json` |
| Image-Digest | `sha256:93dc4bb0199798624851db25908a922fe42826efee5f61f990bfe6443ff1d4fa`; gleiche Abfrage |
| Software | Gamescope laufend `3.17.0-ogc1+`, Plasma 6.8.2, KWin 6.8.2-3.fc45, Mesa 26.2.6; Journal/RPM |
| Sitzung | SDDM-Autologin, gamescope, Wayland; `loginctl show-session 1` |
| Prozesse | Gamescope PID 2982 und Steam Gamepad UI; kein KWin/plasmashell; `ps` und ausgewählte `/proc`-Felder |
| DRM | `card1` und `renderD128` gehören zur Intel-GPU; `/dev/dri/by-path` |
| Dienste | Decky disabled/inactive; Hybrid-Focus active/running; gezielte `systemctl show`-Abfragen |
| InputPlumber | laufend, keine CompositeDeviceN in der abgefragten D-Bus-Struktur; `busctl --auto-start=no` |
| Audio | PipeWire/WirePlumber aktiv, analoger Stereo-Standardsink, 48 kHz, IDLE; Status/pactl; keine Wiedergabeabnahme |
| CI | Lauf 43687907354, workflow_dispatch, gleicher Quellcommit, classify/tests/container/result success, publish skipped, kein ISO-Job; `gh run view` |

Micro-Gehäuse und exakt verbaute 16 GiB wurden durch diese Befunde nicht
unabhängig bestätigt. Image-Digest, Quellcommit, Signatur und Hardwaretest sind
getrennte Belege. Der CI-Erfolg beweist keine lokale Grafikfunktion und keine
in dieser Sitzung geprüfte Signatur.

### Physische Monitore, DRM und gespeichertes KWin-Layout

Die folgenden EDID-Hashes wurden zuvor aus `/sys/class/drm/card1-*/edid`
berechnet; Seriennummern und Rohbytes wurden nicht ausgegeben:

| Physischer Monitor nach EDID | Damaliger Connector | Damaliger Status | Gespeicherter KWin-Ausgang |
|---|---|---|---|
| ACI/VG248, SHA-256 `958965c347deac54eed45598087870390a0167f806657f1a99655916d63aa197` | `card1-DP-1` | connected, disabled, DPMS Off | Index 3, Name DP-1 |
| ACI/VG248, SHA-256 `07105abd44674077ceaadc25e0e190e017d2e45ad4b865c4660ad5549a4bf721` | `card1-DP-2` | connected, enabled, DPMS On | Index 2, Name DP-2 |

Die Zuordnung zum gespeicherten `~/.config/kwinoutputconfig.json` wurde anhand
der dortigen EDID-Hashes verglichen. Ein gespeichertes erweitertes Layout lag
für Index 2 bei `(0,0)` und Index 3 bei `(1920,0)` vor. Da KWin damals nicht
lief, beweist das keinen aktuellen Zweimonitorbetrieb.

Die Gaming-Rolle und physische Kabel-/Adapterzuordnung müssen vor dem Versuch
erneut vom Bediener bestätigt werden. `connected`, aktivierter Ausgang und
sichtbares Bild sind verschiedene Nachweise.

### Direkter Gaming Mode und i915-Risiko

Das frühere Startjournal von PID 2982, abgefragt mit
`journalctl -b _PID=2982 -o short-monotonic`, enthält:

```text
[10.269407] drm: opening DRM node '/dev/dri/card1'
[10.428586] drm: selecting connector DP-2
[10.428628] drm: selecting mode 1920x1080@60Hz
```

Die Prozessargumente enthielten `--prefer-output *,eDP-1 --xwayland-count 2`.
Zwei Xwayland-Server bedeuten keine zwei physischen Ausgänge. Zusammen mit dem
fehlenden Plasma erklärt der ausgewählte direkte Ausgabepfad den damaligen
Einmonitorbetrieb. Der genaue lokale Deaktivierungspfad wurde nicht instrumentiert.

Im Boot `16314fdf-01c1-4668-90a9-8df7243a958d` wurden zuvor mit
`journalctl -b -k -o short-monotonic --grep 'Atomic update failure'` drei
i915-Fehler auf pipe A bei 2964.114072, 3144.131078 und 4725.099121 Sekunden
gemessen. Ein Zusammenhang mit dem deaktivierten DP-1 ist **nicht nachgewiesen**.
Wanduhrzeiten im Journal waren uneinheitlich; künftige Vergleiche benötigen
Boot-ID, monotone Zeit und Vorher-/Nachhermarker. Keine Fehlerfreiheit behaupten.

## Architekturvergleich

Bewertungen sind technische Schlussfolgerungen, keine Hardwareabnahme.

| Kriterium | 1: KWin plus nested Gamescope | 2: Direkter Gamescope plus separater Compositor | 3: Gamescope-DRM-Backend erweitern |
|---|---|---|---|
| Bazzite | vorhandene Komponenten, manuell untersuchbar | Ressourcenaufteilung/Leasing/Seats ungelöst | umfangreiche neue Compositorfunktion |
| Intel/i915 | grundsätzliche Unterstützung; lokaler Nested-Beleg fehlt | unabhängige Ausgabe auf derselben GPU nicht belegt | KMS-/Plane-/Treiberarbeit; bestehende Fehler separat |
| AMD/Polaris | eigener Test; keine blinde SDL-Übernahme | ebenfalls Ownership-/Lease-Fragen | zusätzliche Polaris-/Modifier-Risiken |
| Stabilität | KWin bleibt bestehender Displaymanager | komplexe Ressourcenübergaben | große Regressionsfläche |
| Latenz | zusätzliche Komposition möglich, messen | direkter Spielpfad potenziell günstig | direkter Pfad potenziell günstig |
| VRR/HDR | Host-/Backend-/Monitorabhängig, kein MVP-Gate | pro Ausgang denkbar, unbewiesen | explizite Mehroutputimplementierung |
| Hardware-Rendering | erwartbar, pro Spiel belegen | erst nach GPU-Aufteilung belegbar | Renderer löst Desktopverwaltung nicht |
| Steam-Overlay | separat prüfen, backendabhängig | näher am Bestand möglich | Integration erneut prüfen |
| Controller | ausgeschlossen, spätere separate Validierung | sitzungsübergreifend komplex | eigenes exklusives Routing nötig |
| Sitzung | eine Plasma-Sitzung | mehrere Lebenszyklen, Seats/Leases | neue Desktop-/Shellintegration |
| Fehler/Rückkehr | eigene Kinder beenden, KWin bleibt | DRM-Rückgabe kritisch | Fehler können beide Ausgänge betreffen |
| Wartung | niedrig bis mittel | hoch | sehr hoch |
| Kurzfristiges MVP | gewählt | ungeeignet | ungeeignet |
| Langfristig | optionaler Modus bei akzeptablen Messwerten | Forschungsoption | Upstream-orientiertes Forschungsprojekt |

Ansatz 1 wurde vom Benutzer ausdrücklich gewählt. Er vermeidet die bislang
unbewiesene Aufteilung physischer Ausgänge zwischen zwei direkten Compositors.
Er bietet mit KWin eine vorhandene Desktopverwaltung und einen kleinen,
begrenzten Test. Ein erfolgreicher nested-Test validiert keine echte
Mehrbildschirmausgabe des direkten Gamescope-DRM-Backends.

## Quellen und Wiederverwendungsgrenzen

Die zuvor gelesene lokale `/usr/share/doc/terra-gamescope/README.md` dokumentiert
Nesting und Intel-/AMD-Unterstützung. `-w/-h` bestimmen die interne Auflösung,
`-W/-H` die nested-Ausgabegröße, `-r` ein Framelimit, `-f` Vollbild.
Die zusätzliche Optionsbasis ist
[Gamescope 3.17.0 main.cpp](https://github.com/ValveSoftware/gamescope/blob/3.17.0/src/main.cpp).
Sie ist kein Nachweis aller Optionen des lokal installierten OGC-Builds.
Vor einem Start müssen benötigte Optionen für genau das lokale Binary bestätigt
werden; das darf im jetzigen Dokumentationsauftrag keinen Binary-Start auslösen.

Die zuvor gelesenen lokalen Wrapper `/usr/bin/gamescope-session-plus`,
`/usr/share/gamescope-session-plus/gamescope-session-plus` und dessen
`sessions.d/steam` verändern Benutzer-Systemd-/Portalumgebung, erzeugen Dateien
und enthalten Recoverylogik. Sie sind kein wiederverwendbarer Plasma-Launcher.
Die vorhandene Polaris-Regel unter
`system_files/etc/gamescope-session-plus/sessions.d/steam` bleibt unverändert;
sie darf nicht global auf Intel oder ungeprüft auf nested AMD übertragen werden.

OutputManager wurde zuvor ausschließlich als Quelltextvergleich untersucht,
Commit `dca8b12123f5ad9f73b400fe1bd0400c5fdd47bd`:
[Code](https://github.com/joeatethebeans/OutputManager/blob/dca8b12123f5ad9f73b400fe1bd0400c5fdd47bd/main.py),
[Kompatibilität](https://github.com/joeatethebeans/OutputManager/blob/dca8b12123f5ad9f73b400fe1bd0400c5fdd47bd/README.md).
Er verwendet Kartenindex/Connector als ID, force und Hotplug; selbst eine
Statusfunktion kann schreiben. Dokumentierte Unterstützung ist AMDGPU, nicht
i915. Wiederverwendbar ist nur das Auswahlkonzept, keine operative Integration.

## Prozess-, Sitzungs- und Displaytopologie

```text
Bestehende Plasma-Wayland-Sitzung
  KWin -> i915/amdgpu -> Gaming-Monitor
                     -> Desktop-Monitor
  Plasma-Terminal -> manueller MVP-Launcher -> nested Gamescope
                                             -> Grafikclient
                                             ODER Steam -> Spiel
  Browser/Terminal -> KWin -> Desktop-Monitor
```

Die Skizze beschreibt Display-Ownership und Prozesszugehörigkeit, nicht zwingend
die endgültigen Eltern-PIDs nach Steam-Runtime-Reexec. GPU-Rendering innerhalb
von Gamescope bedeutet keine eigene physische Connectorverwaltung.

## Monitoridentifikation und Preflight

Ein physischer Monitor wird vorrangig durch EDID-SHA-256 plus Hersteller/Modell
beschrieben. GPU-PCI-Pfad, aktueller DRM-Connector, logischer KWin-Ausgang und
Gaming-Rolle werden getrennt geführt. Connectornamen wie DP-1 und DP-2 sind
keine dauerhaften Monitoridentitäten. EDID-Hashes können ebenfalls fehlen,
doppelt vorkommen oder nach Hardware-/Adapteränderungen wechseln; dann abbrechen
und manuell neu zuordnen, keinen stillen Primärmonitor-Fallback verwenden.

Vor jedem später freigegebenen Versuch muss ein lesender Preflight bestätigen:

1. Eigene lokale Plasma-Wayland-Sitzung und bereits laufendes KWin; keine aus
   anderen Prozessen übernommene oder geratene GUI-Umgebung.
2. Zwei aktive, nicht gespiegelte Ausgänge, passende aktuelle EDIDs und vom
   Bediener bestätigte physische Rollen; Sichtprüfung zusätzlich zu Statusdaten.
3. Benötigte Programme/Optionen vorhanden; ausgewähltes Backend eindeutig nested.
4. Keine kollidierende Steam-/Gamescope-Instanz. Bereits laufende Instanzen
   führen zur Ablehnung, nicht zum automatischen Beenden.
5. Decky inaktiv; keine operative OutputManager-Abhängigkeit. Bestehendes
   Hybrid-Focus-Routing darf den Test nicht unbemerkt beeinflussen. Bei aktivem
   Fokusdienst Start blockieren, bis dessen Umgang separat sicher freigegeben
   und belegt ist; Preflight ändert daran nichts.
6. Tastatur/Maus, gesicherte Arbeit, genehmigter Rückweg und Versionsinventar.
7. Frische fünfminütige Plasma-Baseline, Boot-ID und monotone Fehlergrenze.

GUI-Abfragen nur im passenden eigenen Sitzungskontext. Insbesondere
`kscreen-doctor -o` nicht blind aus TTY/SSH wiederholen: der historische Audit
dokumentiert SIGABRT/Core-Dump. Unklare oder unzugängliche Daten sind BLOCKED.

## Start, Platzierung und Stop

Alle Schritte benötigen später passende Freigaben einschließlich Sitzung und
Recovery. Der Launcher setzt keine globale Umgebung und startet keine Dienste.

1. Manuell in Plasma wechseln und beide Ausgänge bestätigen, sofern separat
   genehmigt. Vorhandenes Steam durch den Bediener regulär schließen.
2. Preflight aus einem Plasma-Terminal ausführen; bei Ablehnung nichts starten.
3. Grafikmodus mit explizitem Wayland-Nested-Backend starten. Ausgangskandidat:
   `gamescope --backend wayland --expose-wayland -w 1920 -h 1080 -W 1920 -H 1080 -r 60 -- vkcube`.
   Dieser Befehl ist ungeprüfter Laufzeitkandidat, keine aktuelle Freigabe.
4. Fenster manuell über KWin auf den gewählten Monitor bewegen, Vollbild
   herstellen und Platzierung bestätigen. Keine KWin-Regel schreiben; keine
   `--prefer-output`-Platzierung und keine ungeprüfte Displayindex-Garantie.
5. Erst ab bestätigter Platzierung beginnt die Displayabnahme. Monitor 2 bedienen,
   Grafikclient regulär beenden, Gamescope-Ende und beide Plasma-Ausgänge prüfen.
6. Nur nach bestandenem Grafik-Gate separat Steam-Nested starten. Vorgesehener
   Steam-Client ist der vorhandene normale Launcher mit `-gamepadui`; keine
   ungeprüften Deck-/SteamOS-Sitzungsflags oder Bootstrap-Skripte übernehmen.
7. Bereits für den Grafiktest und danach für Steam/Spiel müssen interne Xwayland-
   und Wayland-Clientziele zu Gamescope gehören. `--expose-wayland` ist für beide
   Startmodi erforderlich und erst nach lokaler Optionsbestätigung nutzbar.
   Gamescope muss seinen inneren Wayland-Socket an den Client übergeben; auch ein
   nativ Wayland verwendendes vkcube darf nicht am äußeren KWin erscheinen.
   Fehlende Unterstützung oder unklarer Clientpfad blockiert den Versuch.
   Kein geratener Socket und kein automatischer Backendwechsel.
8. Erst nach Steam-Gate benanntes Spiel starten und dessen Hardware-Renderer
   belegen. Overlayfunktion getrennt erfassen; `--steam` allein beweist sie nicht.
9. Spiel regulär beenden, Steam vollständig schließen, Gamescope-Ende abwarten.
   Beide Plasma-Ausgänge und die Desktopanwendung erneut prüfen.

Vollbild darf bei Desktopinteraktion nicht minimieren. Kein globaler
Keyboard-Grab; spielinternes Pausieren bei Fokusverlust wird gesondert notiert.
Die anfängliche manuelle Platzierung ist erlaubt. Nach ihrer Bestätigung dürfen
Steam/Spiel keine Fenster auf den Desktop-Monitor auslagern.

## Fehlerbehandlung und exakter begrenzter Rollback

Fehlende Voraussetzung: Start verweigern. Startfehler: Exitcode und redigierte
Fehlerklasse melden, kein Retry und kein DRM-Fallback. Bei Ausgangsverlust,
KWin-Absturz oder unklarem Routing Testeingaben sofort einstellen.

Rückweg: Spiel über seine Oberfläche schließen, Steam regulär vollständig
beenden, Gamescope beziehungsweise den eigenen Vordergrundlauncher schließen.
Nur falls ausdrücklich genehmigt und nötig: eigene noch laufende Prozesse anhand
erfasster Prozessidentität erneut prüfen, dann einmalig TERM an diese Instanz.
Keine Namenssuche mit anschließendem killall/pkill. PID allein genügt nicht.
Launcher soll direkte Kinder bevorzugt über stabile Prozesshandles (unter Linux
pidfd) verwalten; keine ungeschützte Check-then-kill-PID-Race. Nicht belegbare oder
aus der eigenen Gruppe entkommene Steam-Kinder nur melden, nicht automatisch
beenden. Kein automatisches KILL, keine Neustart-/Profilwechsel-Schleifen.

Erfolgreicher Rollback bedeutet: KWin läuft weiter, beide Ausgänge sind aktiv
und sichtbar, Desktopanwendung bleibt benutzbar, alle MVP-eigenen Prozesse sind
beendet. Vorher vorhandene Prozesse und Konfigurationen bleiben erhalten.
Bleibt ein Monitor schwarz oder ein Kind unklar, ist Rollback fehlgeschlagen:
keine Displayreparatur und keine Erfolgsmeldung, manuellen Bedarf dokumentieren.

Ein Sitzungswechsel zurück zum normalen Gaming Mode ist ein eigener freizugebender
Schritt. Das absichtliche Wiederherstellen eines schwarzen DP-1 durch Abschalten
ist kein MVP-Rollback. Eine separat genehmigte Neutralisierung des Fokusdienstes
braucht ebenfalls ihren eigenen sicheren Rückweg; keine Deinstallation.

## Diagnose und Datenschutz

Standard: redigierte Ausgabe nach stdout, keine Exportdateien. Berichte enthalten
nur Zeit/Bootkontext, Versionen, EDID-Hashes und Modell, aktuelle Zuordnung,
gewählte Rolle, eigene Prozessidentitäten, Backend, Exitcodes und begrenzte
relevante Fehler. Keine vollständigen Prozessumgebungen, Roh-EDIDs, Seriennummern,
Cookies, Kontoinhalte oder fremden Anwendungsargumente. Synthetische Geheimnisse
für spätere Datenschutztests; keine echten Zugangsdaten verwenden.

Einträge höchstens 100 je abgefragter relevanter Journalquelle, Zeilen höchstens
512 Zeichen; Kürzung/fehlende Zugriffe explizit markieren. Rohes Steam-stdout ist
kein automatisch teilbares Diagnoseartefakt. Keine unkontrollierte Weiterleitung
von Kindausgaben in den strukturierten Bericht. Export, zusätzliche
Instrumentierung und Speicherziel sind gesondert freizugeben.

## Akzeptanzvertrag

### Funktionale Akzeptanz

- F1: Zwei anhand EDID und Sichtprüfung identifizierte aktive Plasma-Ausgänge,
  erweitert, nicht gespiegelt; explizite Gaming-/Desktoprolle.
- F2: Manueller Start in derselben Plasma-Wayland-Sitzung, ohne neue Standardsitzung.
- F3: Nach manueller Bestätigung Gamescope vollständig auf dem Gaming-Monitor;
  Steam Gamepad UI und Spiel nur innerhalb dieser Instanz auf diesem Monitor.
- F4: Monitor 2 bleibt eigenständiger Desktop; mindestens Terminal oder Browser
  lässt sich mit physischer Tastatur/Maus bedienen.
- F5: Desktopfokus minimiert Gamescope nicht und beendet keine Desktopanwendung;
  spielbedingte Pause wird getrennt dokumentiert.
- F6: Testspiel meldet Intel UHD 630 beziehungsweise später Radeon E9173 als
  Hardware-Renderer, nicht llvmpipe/softpipe/lavapipe. Gamescopes eigene
  Vulkan-Gerätewahl allein genügt nicht.
- F7: Spielende lässt Steam/Plasma benutzbar; Steam- und Gamescope-Ende hinterlassen
  beide Plasma-Ausgänge vollständig benutzbar.
- F8: Fehlstart lässt sich ohne Neustart im begrenzten genehmigten Rückweg auflösen.
- F9: Keine DRM-force-Werte, Hotplug-, KWin-Ausgangs-, Dienst- oder Sitzungsänderungen
  durch das MVP; insbesondere keine dauerhaft veränderten force-Werte.
- F10: Kein Plugin/OutputManager/Fokusprototyp erforderlich; normaler Gaming Mode
  und geschützte Releaseeingaben unverändert.
- F11: Diagnoseartefakte sind begrenzt und redigiert; keine Geheimnisse.
- F12: Grafik-Gate bestanden, dann Steam-Gate, dann Spiel-Gate; keine Abkürzung.

### Stabilität, Performance und Abbruch

Nach den einzelnen Gates drei vollständige Start-/Stopdurchläufe; davon einer
mit mindestens 30 Minuten Spiel und wiederholter Desktopbenutzung. Keine
schwarzen/verlorenen Ausgänge, KWin-Abstürze oder nötigen Neustarts. Neue
i915-/DRM-Fehler seit dem Startmarker unterbrechen den Versuch; ihre Ursache
bleibt separat zu untersuchen. Eine fehlerhafte Plasma-Baseline blockiert den
Start, statt den vorhandenen Fehler dem MVP zuzuschreiben.

Auflösung, physische Frequenz, Framelimit, FPS, Framezeiten soweit verfügbar,
GPU-/CPU-Last und Fokusverhalten beobachten. Ohne Messgerät keine quantifizierte
Eingabelatenz behaupten. VRR, HDR und Direct Scanout sind Beobachtungen, keine
MVP-Gates. Software-Rendering ist dagegen ein Abnahmefehler.

Abbruch auch bei unbekanntem Backend, nicht eindeutiger EDID-/Fensterzuordnung,
falschem Displayziel, fehlendem Rückweg, unklarer Prozesseigentümerschaft oder
unzulässigen Diagnoseinhalten. Kein endlicher Test beweist universelle Stabilität
oder Input-Exklusivität; Controller-Routing ist hier nicht abgenommen.

## Testmatrix und Abgrenzung

| System/Stufe | Prüfungen | Grenze |
|---|---|---|
| Dell/Intel, Grafik | frische Plasma-Baseline, zwei Displays, nested vkcube, manuelles Vollbild, Desktop, Stop | erste Hardwarefreigabe erforderlich |
| Dell/Intel, Steam | erst nach Grafik-Gate; Gamepad UI, interne Clientziele, Desktop, Stop, Overlaybeobachtung | eigene Start-/Stopfreigabe |
| Dell/Intel, Spiel | erst nach Steam-Gate; benanntes Spiel, Renderer, drei Zyklen/30 Minuten | eigene Spiel-/Recoveryfreigabe |
| HP/AMD später | gesamte Abnahme erneut, eigener Software-/EDID-/Kabelbeleg | Dell-Erfolg validiert HP t740 nicht |
| Beide später | begrenzter Fehlerfall, weitere Spiele/Frequenzen/Skalierung | getrennte Freigaben; kein Hotplug in erster Abnahme |

HP t740/E9173 am direkten E9173-DisplayPort und ISO Build #4 bleibt die historische
Referenz, **nicht in dieser Sitzung neu gemessen**. Ein späteres HP-Nested-MVP
darf diese Referenz nicht überschreiben oder als deren Revalidierung gelten.

Der [Hybrid-Focus-Prototyp](../../../prototype/hybrid-focus/README.md) ist nicht
Teil des Display-MVP: keine Imports, Profile, Socketbefehle, Installer oder
Decky-Abhängigkeiten. Die ältere
[Spezifikation](2026-11-11-hybrid-gaming-mode-design.md) und der
[Fokusplan](../plans/2026-11-11-hybrid-controller-focus-prototype.md) bleiben
historische Quellen; deren Installations-/Recoveryanweisungen sind keine aktuelle
Freigabe. Display- und Controllerabnahme bleiben getrennt.

## Spätere Entwicklungsstufen

Nach separater Freigabe: reine Modelle/Preflight, Launcher und Schutztests;
dann Grafik-, Steam- und Spiel-Gates auf Dell. Danach gegebenenfalls separater
HP-Test und belastbarer Performancevergleich. Automatische Platzierung,
benutzerfreundliche Integration, Controller-Routing und echte Glyphen benötigen
jeweils eigenes Design und Abnahme. Direkte Gamescope-Mehrbildschirmarchitektur
bleibt ein unbewiesenes separates Forschungsziel. Classifier-, Container-, ISO-
und Releaseänderungen sind keine automatische Folge dieser Planung.
