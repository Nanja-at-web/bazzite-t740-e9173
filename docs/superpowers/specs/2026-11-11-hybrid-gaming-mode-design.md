# Hybrid Gaming Mode – Design

Date: 2026-11-11

Target repository: `Nanja-at-web/bazzite-t740-e9173`

Planned repository path:
`docs/superpowers/specs/2026-11-11-hybrid-gaming-mode-design.md`

## Intent

Add an optional **Bazzite Hybrid Gaming Mode** session. Steam Gamepad UI and
games run through Gamescope on one user-selected gaming display, while every
other connected display remains an independent Plasma workspace for browsers,
Discord, TeamSpeak, monitoring tools, and other applications.

The feature serves desktop and HTPC systems with two or more displays. It is
not limited to the HP t740 or AMD Polaris: the validated starting hardware is
the HP t740 with Radeon E9173 and the Dell OptiPlex 5080 Micro with Intel UHD
630.

## Goals

- Offer Hybrid Gaming Mode as an additional login/session choice alongside the
  existing Bazzite Gaming Mode and Desktop Mode.
- Let the user select which connected display is the gaming display.
- Run Steam Gamepad UI and games inside a fullscreen nested Gamescope window on
  that display.
- Keep the other displays as normal, independently usable Plasma workspaces.
- Keep applications on secondary displays running while a game starts, stops,
  or changes resolution.
- Preserve the existing conditional Polaris SDL workaround on the HP t740.
- Work with both the tested AMD/Polaris and Intel/i915 systems.
- Fail safely back to a usable Plasma desktop if Gamescope or Steam fails.
- Keep the ordinary direct-DRM Gaming Mode unchanged.

## Agreed product decisions

- Controller input remains assigned to Steam/the running game when mouse and
  keyboard focus moves to an application on another display. The implementation
  may use existing Bazzite input facilities, but it must not require per-device
  seats in the first release.
- Hybrid Mode is opt-in and is not made the default session. In addition to its
  SDDM entry, the image provides a **Switch to Hybrid Gaming Mode** action so
  systems configured for Bazzite autologin can reach it without editing SDDM
  settings manually.
- On the first start with two or more connected displays, the display selector
  opens before Steam starts. With exactly one display, that display is selected
  automatically. If a previously stored display is unavailable later, Plasma's
  current primary output is the safe fallback.
- The first test release may document missing HDR, restricted VRR/direct
  scan-out, or moderately higher latency. Stable multi-workspace operation and
  hardware rendering are its initial release gates; the differences must still
  be measured and reported against direct Gaming Mode.
- Disconnecting the active gaming display does not immediately terminate Steam
  or the game. The controller keeps the processes alive and presents a choice
  on a remaining output to migrate Gamescope or end the game/session.

## Non-goals for the first release

- Implementing native multi-output support inside Gamescope's DRM backend.
- Spanning one game across multiple monitors.
- Mirroring Gamescope to multiple physical outputs.
- Guaranteeing that every game continues rendering when keyboard focus moves to
  another application; some games pause on focus loss by design.
- Matching every direct-DRM feature in the first release, especially HDR, VRR,
  direct scan-out, and Steam Deck-style session power behavior.
- Replacing Desktop Mode or the standard Bazzite Gaming Mode.
- Supporting GNOME in the first release; the current image and validation
  target use KDE Plasma.

## Anti-goals

- Do not globally force the SDL backend on Intel or newer AMD GPUs.
- Do not make a second compositor compete with Gamescope for DRM master on the
  same GPU.
- Do not patch upstream Gamescope with an unmaintainable desktop shell.
- Do not overwrite the user's existing Plasma display layout.
- Do not start a new ISO automatically while this feature is being developed.

## Current constraints

- Gamescope embedded/direct-DRM mode currently selects one physical output and
  is not a general multi-monitor desktop compositor.
- `gamescope-session-plus` deliberately constructs a direct Gamescope session,
  changes session environment variables, clears desktop portal configuration,
  and starts one client. It must remain the implementation for the existing
  Gaming Mode, but it should not be used as the parent of Hybrid Mode.
- Plasma/KWin already detects, arranges, and drives both displays successfully
  on the Dell OptiPlex 5080.
- The repository's current Polaris override is conditional on an AMD device at
  PCI `0000:01:00.0`; it is not activated on the tested Dell.
- Bazzite is an immutable image. System files belong in the custom container;
  per-user choices belong under `~/.config`.

## Approaches considered

### 1. Plasma parent with nested Gamescope – selected

Start a Plasma Wayland session to own every display. Place a nested fullscreen
Gamescope instance on the selected gaming display and launch Steam Gamepad UI
inside it. All other Plasma outputs remain available for ordinary applications.

Benefits:

- Meets the independent-secondary-workspace requirement with components Bazzite
  already ships.
- Reuses KWin/KScreen for monitor arrangement, hotplug handling, panels,
  portals, notifications, and ordinary application windows.
- Does not require an upstream Gamescope multi-output implementation.
- Can coexist with the existing direct Gaming Mode.

Trade-offs:

- Nested Gamescope may lose direct scan-out or have different HDR/VRR behavior.
- Focus, controller routing, fullscreen placement, and session teardown require
  explicit integration and hardware testing.
- Plasma consumes more resources than direct Gaming Mode.

### 2. Native Gamescope multi-output fork – rejected for this project phase

Extend Gamescope's DRM backend and add independent surface routing, focus,
window management, portals, and a desktop shell for secondary outputs. Merely
enumerating a second connector would not provide a usable workspace.

This is upstream-scale work with a large maintenance burden and does not build
on the desktop facilities already present in Bazzite.

### 3. Separate compositors per output – rejected

Run Gamescope on one connector and another compositor on the remaining
connectors using DRM leasing, separate seats, or separate GPUs. This is fragile
on a single GPU, highly driver-dependent, and unsuitable as a general ISO
feature.

## Selected architecture

### Session entry

Install an additional SDDM Wayland session named **Bazzite Hybrid Gaming Mode**.
Its wrapper starts Plasma Wayland with a session marker such as
`BAZZITE_HYBRID_SESSION=1`. It does not replace `plasma.desktop` or the existing
Gamescope session.

The marker is imported into the user systemd and D-Bus environments. A user
service starts the Hybrid controller only when this marker is present.

An additional switch action integrates with Bazzite's session-management path:
it records Hybrid Mode as the next session and logs out of the current session.
It does not silently change the persistent default or replace standard Gaming
Mode. A matching action returns to the ordinary Bazzite Gaming Mode.

Proposed image-owned components:

- `/usr/share/wayland-sessions/bazzite-hybrid.desktop`
- `/usr/libexec/bazzite-hybrid-session`
- `/usr/libexec/bazzite-hybrid-controller`
- `/usr/libexec/bazzite-hybrid-display-select`
- `/usr/lib/systemd/user/bazzite-hybrid-gaming.service`
- `/usr/share/applications/bazzite-hybrid-display-select.desktop`

Names are intentionally hardware-neutral. Existing `t740-*` diagnostics and
metadata remain compatible and can be renamed separately in a later change.

### User configuration

Store only user choices under:

`~/.config/bazzite-hybrid-gaming/config.json`

Schema version 1 records:

- a stable gaming-display identity, preferably an EDID-derived identifier;
- the last known connector name as a fallback;
- whether Hybrid Mode should start Steam automatically;
- optional nested Gamescope render resolution and refresh limit;
- the selected backend policy: `auto`, never a globally forced vendor backend.

The display selector lists connected outputs with manufacturer/model, connector,
resolution, refresh rate, and current Plasma primary status. It writes the file
atomically. The initial UI may use installed KDE facilities, but configuration
parsing and validation must not depend on GUI state.

When no configuration exists and multiple displays are connected, Steam waits
for this selector. Cancelling the selector leaves the Plasma session running
without Steam rather than guessing a gaming output.

### Monitor selection and placement

KScreen/KWin remains authoritative for enabled outputs and their arrangement.
The controller resolves the stored EDID identity to a current connector. If the
stored display is absent, it uses the current Plasma primary display and shows a
notification explaining the fallback.

A generated KWin rule identifies only the Hybrid Gamescope window, places it on
the chosen output, makes it borderless and fullscreen, and prevents ordinary
applications from being captured by that rule. The rule is session-scoped or
cleanly removed during shutdown.

The controller must verify placement after the window appears. Connector names
alone are not treated as stable identities because they can change after BIOS,
GPU, dock, or port changes.

### Gamescope and Steam launch

Hybrid Mode runs Gamescope nested under Plasma rather than as DRM master. The
launcher:

1. reads and validates the user configuration;
2. discovers the chosen output and its current mode;
3. selects the normal nested Gamescope backend by default;
4. applies the existing Polaris compatibility behavior only when the matching
   AMD Polaris device is actually present;
5. starts Gamescope with Steam integration and a unique window identity;
6. launches the Bazzite-provided Steam Gamepad UI client inside Gamescope;
7. publishes clear status and failure information to the journal.

The implementation must reuse the installed Bazzite Steam bootstrap/client
configuration where possible instead of copying an upstream command line that
will drift. It must not invoke the existing direct-session wrapper in a way that
clears Plasma's portal or display environment.

### Input and focus

- Steam retains controller input while Plasma continues to accept mouse and
  keyboard input on the secondary workspaces, including while another window
  owns keyboard focus.
- The Gamescope window must not minimize when focus moves to another display.
- Moving keyboard focus away from a game is allowed. Game-specific pause or
  input behavior is documented rather than hidden.
- The first release does not implement per-device input seats.
- A keyboard shortcut and a desktop launcher refocus the Gamescope/Steam window.

### Secondary workspace behavior

The non-gaming displays remain ordinary Plasma outputs with their existing
wallpaper, panels, launchers, notifications, and application windows. Discord,
TeamSpeak, browsers, terminals, monitoring tools, and Flatpaks use normal
desktop portals.

Starting or stopping a Steam game must not restart Plasma or terminate these
applications. Exiting Steam stops nested Gamescope but leaves the Hybrid Plasma
session running and offers actions to restart Steam, return to Desktop Mode, or
log out.

### Display changes

First release requirements:

- Displays connected before login are detected automatically.
- If only one display exists, Hybrid Mode still starts on that display and
  behaves like a nested single-display gaming session.
- Disconnecting the gaming display ends or suspends nested Gamescope safely and
  keeps Steam/the game alive while a confirmation is shown on a remaining
  output. The user can migrate Gamescope to the current Plasma primary display
  or end the game/session.
- A **Rescan displays** action handles monitors attached after login.

Automatic migration of a running game during hotplug is deferred until the
basic session is stable; silently moving a live fullscreen game is an anti-goal.

## Failure and recovery behavior

- Invalid or corrupt configuration is preserved for diagnostics, ignored for
  startup, and replaced only after explicit user selection.
- If Gamescope fails to create its window, Plasma remains usable and displays a
  notification with a journal command and a retry action.
- If Steam exits immediately, the controller retries at most once and then
  remains in Plasma.
- No automatic reboot or logout occurs after a Hybrid failure.
- Standard Desktop Mode and direct Gaming Mode remain selectable at login.

## Observability

Add a hardware-neutral diagnostic command, provisionally
`bazzite-hybrid-diagnostics`, that reports without modifying the system:

- session type and Hybrid marker;
- connected KScreen/DRM outputs and stable identities;
- selected gaming output and fallback reason;
- Gamescope command, backend, version, PID, window identity, and placement;
- Steam client PID;
- relevant user-service status and bounded journal excerpts;
- GPU/DRM mapping already supplied by the existing diagnostics where possible.

The command must avoid dumping the complete process environment or unrelated
personal application command lines.

## Security and privacy

- No root daemon is introduced.
- Configuration and runtime files are user-owned and written atomically.
- Commands are constructed as arrays, not evaluated shell strings containing
  monitor metadata.
- EDID manufacturer/model data stays local and is included in diagnostics only
  when the user explicitly runs the command.
- Flatpak applications continue using normal Plasma portals.

## Validation and acceptance criteria

### Automated checks

- Shell/static checks for every launcher and service helper.
- Unit tests for configuration parsing, EDID/connector resolution, fallback
  selection, command construction, and the conditional Polaris backend.
- Tests proving that Intel hardware never receives the Polaris SDL override.
- Tests proving existing direct Gaming Mode files remain unchanged.
- Failure tests for missing Gamescope, missing Steam, corrupt config, and a
  disconnected stored output.

### Hardware integration checks

Run the same checklist on the HP t740/Radeon E9173 and Dell OptiPlex 5080/UHD
630:

1. Standard Desktop Mode still works.
2. Existing direct Gaming Mode still works.
3. Hybrid session appears and starts successfully.
4. The selector identifies both attached displays and persists the chosen one.
5. Steam Gamepad UI and a game render on the selected display.
6. Browser, Discord or TeamSpeak, and a monitoring tool remain independently
   usable on the other display while the game runs.
7. Mouse/keyboard focus can move to the secondary display without minimizing
   Gamescope; controller input can return to Steam.
8. Game exit leaves secondary applications running.
9. Missing/disconnected selected display produces the documented safe fallback.
10. Logs and diagnostics identify the selected backend and output.

Performance, frame pacing, input latency, VRR, HDR, capture, suspend/resume, and
audio routing are recorded separately against the existing direct Gaming Mode.
Regressions are documented before deciding whether Hybrid Mode is ready for
default visibility.

Missing HDR, limited VRR/direct scan-out, or moderately increased latency do not
block the first opt-in test build. Software rendering, unreliable startup,
secondary-workspace termination, or loss of controller control while using the
secondary display do block it.

## Rollout

1. Develop on a feature branch; no ISO build trigger.
2. Add automated tests and verify the container build without moving the locked
   installation payload.
3. Publish an opt-in test container revision only after review.
4. Update `image-lock.json` to the validated digest.
5. Build an ISO only by explicit manual authorization.
6. Test first on the Dell, then on the HP t740 while retaining the currently
   working deployment for rollback.

Hybrid Mode remains opt-in until both machines pass the acceptance checklist.

## Builder-owned implementation choices

- Exact implementation language for the controller and selector, provided it
  uses dependencies already suitable for the immutable KDE image and has unit
  tests.
- Exact KWin rule API or script mechanism, provided placement is deterministic
  and cleanup is reliable.
- Exact notification implementation using existing KDE facilities.
- Internal configuration library and logging format.

