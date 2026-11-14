# Hardwarebaselines und Architekturentscheidung

## HP t740: geschützte historische Referenz

HP t740 Thin Client, Ryzen Embedded V1756B, Radeon E9173/Polaris, Monitor direkt
am E9173-DisplayPort. Für ISO Build #4 bestätigte der Besitzer Installation und
Gaming-Mode-Bildausgabe nach Neustart. Quelle und Identitäten:
[README.md](../../README.md), Zeilen 9–45.

- Quellcommit: `0c0787abb0eb697a368c36acc561dcd6eba972b9`.
- ISO: `bazzite-t740-e9173-polaris-amd64.iso`.
- SHA-256: `2a4da2b2fcc82fbd398a94efdd45181d84bfdbebabf7326db7416d39df5e9ef4`.
- Exakter damaliger eingebetteter Container-Digest: nicht nachgewiesen.

Kein heutiger Dell-Test, späterer Build oder erfolgreicher CI-Lauf erneuert diesen
Hardwarebeleg. Polaris-/Gamescope-Referenz nicht für Intel umdeuten.

## Dell: getrennte Momentaufnahme

Quelle: [Nur-Lese-Audit 2026-11-14](../audits/2026-11-14-dell-hybrid-readonly-audit.md).
Nachgewiesen: OptiPlex 5080, i5-10500T, UHD630/i915, etwa 15,3 GiB nutzbarer RAM,
Bazzite 45.20261105 und Plasma/Wayland. Die Micro-Gehäusevariante und exakt
verbaute 16 GiB wurden dadurch nicht unabhängig vollständig bestätigt.

Zum Audit nur DP-1 mit ACI/VG248-EDID verbunden, andere Connectoren disconnected;
DP-1 wechselte zwischen Messungen von enabled/On zu disabled/Off, Ursache offen.
Gespeicherte Zwei-Monitor-Layouts beweisen keine aktuelle Verkabelung.
Hybrid-Focus installiert, damals inaktiv, Socket fehlend; zehn Zyklen,
Input-Exklusivität und echte Glyphen nicht nachgewiesen. Das sind historische
Messwerte, vor späterem Test neu zu erfassen, keine dauerhaften Systemannahmen.

## Verbindliche Entscheidung aus Stufe 2

Endziel: **normaler Bazzite Gaming Mode mit Steam/Gamescope auf Monitor 1 und
gleichzeitig eigenständiges Plasma auf Monitor 2**. Technische Machbarkeit nicht
nachgewiesen. Nested Gamescope ist nur Diagnose, Entwicklung oder möglicher
Fallback. Die ältere [Design-Spezifikation](../superpowers/specs/2026-11-11-hybrid-gaming-mode-design.md)
wählte Plasma mit nested Gamescope; diese Architekturentscheidung ist durch den
Stufe-2-Auftrag überholt, die Datei bleibt als historische Quelle unverändert.

Vor Tests zwingend physische Verkabelung, tatsächliche Connectoren und Rollen
erfassen, nichts aus dem Audit raten. Echte Xbox-/PlayStation-/Nintendo-Glyphen
mit neutralem Fallback sind das Ziel; Familiennamen als Text reichen nicht.
Controller-Routing und Display-/Compositorbetrieb sind getrennte Abnahmegebiete.
