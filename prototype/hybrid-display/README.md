# Hybrid-Display-MVP: Entwicklungsstand

Ziel ist eine spätere gleichzeitige Nutzung eines Gaming-Monitors mit nested
Gamescope und eines unabhängigen Plasma-Arbeitsbereichs auf einem zweiten
Monitor. Plasma/KWin soll beide physischen Ausgänge verwalten.

Aktuell besteht der Prototyp aus reinen, nicht ausführbaren Bibliotheksbausteinen.
Es gibt keinen ausführbaren Launcher und keine Installation.

Es gibt keinen Betriebssystemadapter und keine Hostdatenerhebung. Alle Daten
müssen ausdrücklich als bereits erhobene Eingaben übergeben werden.

Unit-Tests sind keine Hardwarevalidierung. Ein Gamescope-Start und ein
Dual-Monitor-Betrieb durch diesen Code sind nicht validiert.

Es gibt keine Release-, Container-, Image- oder ISO-Integration.

Es gibt keine Controller-Fokusfunktion, Controllerprofile, Glyphen oder
Quick-Access-Menü-Funktion. Hybrid-Focus bleibt ein eigenständiger Prototyp.

Dell-/Intel- und HP-t740-/AMD-Hardwaretests und Abnahmen bleiben getrennt.
Ein Dell-Erfolg validiert den HP t740 nicht. Auch ein späterer nested-Erfolg
beweist keine gleichzeitige Mehrbildschirmausgabe des direkten DRM-Backends.

## Vorhandene Bausteine

| Modul | Gegenwärtiger Umfang |
| --- | --- |
| `model` | Unveränderliche Datenmodelle für übergebene Sitzungs- und Ausgangsdaten. |
| `preflight` | Reine, strukturierte Startverweigerung anhand eines Snapshots. |
| `outputs` | Eindeutige Zuordnung des vollständigen EDID-SHA-256; Connectornamen sind keine dauerhafte Identität. |
| `command` | Validierte argv-Sequenz und begrenzte Kindumgebung als Daten; explizite Wayland-Capability erforderlich. |
| `runner` | Begrenzte Zustandsübergänge mit injizierten Prozess-/Zeitprotokollen und expliziter Eigentümerschaft; kein echter Adapter. |
| `cli` | Reine Auswertung übergebener Argumente für `preflight` oder `plan`; kein ausführbarer Entrypoint. |
| `diagnostics` | Festes, begrenztes Diagnoseschema mit redigierten Berichtsstrings; keine Ausgabe und kein Export. |

Es bestehen keine systemd-, Desktop-, SDDM-, Plasma-Autostart-, Decky- oder
InputPlumber-Integrationen. Die Standardsitzung und der normale Gaming Mode
werden durch diese Bibliothek nicht verändert. OutputManager ist keine
Abhängigkeit; force- und Hotplug-Operationen gehören nicht zum Prototyp.
Audioauswahl und automatische Fensterplatzierung sind ebenfalls nicht enthalten.

## Sicherer Entwicklungsablauf

Vor Änderungen werden Worktree, Branch, HEAD, Freigabe und Benutzerdateien
geprüft. Neue Anforderungen werden mit reinen Daten und kontrollierten
In-Memory-Fixtures getestet. Prozessprotokolle verwenden ausschließlich Fakes.
Bereits erfüllte Repositoryverträge werden als Regression nachgewiesen;
es werden keine Produktverletzungen zur Erzeugung roter Tests eingebaut.

Die hardwareunabhängigen Display-Tests können aus dem Repository geprüft werden:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -p 'test_hybrid_display_*.py' -v
```

Diese Tests ersetzen keine Hardwareabnahme. Größere Regressionstests benötigen
ihren passenden Freigabeumfang, da bestehende Tests temporäre Dateien und
simulierte Dienstumgebungen verwenden können. Laufzeitadapter, Launcher,
Installation und Hardwareversuche erfordern eine eigene konkrete Freigabe.

Der aktuelle Change-Classifier ordnet `prototype/hybrid-display/**`
(einschließlich dieses README) und `tests/test_hybrid_display_*.py` der
Kategorie H für den isolierten Hybrid-Display-Prototyp und seine Repositorytests zu.
H-only bedeutet Tests-only: kein Containerbau, kein Publish und kein ISO-Lauf,
auch bei manuellem Dispatch.
Die Aufnahme in den Classifier bedeutet keine Produkt-, Session- oder
Releaseintegration und keine Hardwarevalidierung.
Unbekannte andere Pfade bleiben Kategorie G und fail-closed blockiert;
H+G bleibt blockierend.
Diese Dokumentation erteilt keine Build-, Veröffentlichungs- oder ISO-Freigabe.

## Verbindliche Grundlage

- [MVP-Design](../../docs/superpowers/specs/2026-11-15-hybrid-display-mvp-design.md)
- [Implementierungsplan](../../docs/superpowers/plans/2026-11-15-hybrid-display-mvp-implementation.md)
- [Eigenständiger Hybrid-Focus-Prototyp](../hybrid-focus/README.md)
