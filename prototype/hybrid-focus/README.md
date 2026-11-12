# Bazzite Hybrid Focus prototype

This is an optional, user-local prototype for transferring controller ownership
between a nested Gamescope/Steam session and a second KDE Plasma workspace.
It does **not** replace Bazzite Gaming Mode, change the direct Gamescope session,
or build an ISO.

The controller has exactly two targets:

- `game`: restores the exact InputPlumber profiles that were active before the
  transfer;
- `desktop`: exposes only a virtual keyboard and mouse, so the game should no
  longer receive gamepad actions.

State changes are transactional. A failed desktop transition rolls already
changed devices back to their original profiles. The service also attempts to
restore `game` at startup and shutdown.

## Prerequisites

- Bazzite with KDE Plasma and InputPlumber running;
- Python 3, `busctl`, `systemctl`, `udevadm`, and a user systemd session;
- two connected displays for the intended test;
- a physical keyboard and mouse kept available for recovery;
- Decky Loader only if the QAM control is being tested.

Run the first validation on the Dell OptiPlex 5080 test system. Do not install
this prototype on the HP t740 production setup until the Dell checklist passes.

## Install the user service

From the checked-out `design/hybrid-gaming-mode` branch:

```bash
./prototype/hybrid-focus/install-user.sh
systemctl --user status bazzite-hybrid-focus.service --no-pager
bazzite-hybrid-focusctl status
```

The installer writes only below the current user's XDG data, config, binary,
and application directories. It does not request root access. Running it again
updates the same files.

The following fallback launchers are installed:

- **Controller to Desktop 2**
- **Return Controller to Game**

Pin **Return Controller to Game** to the second Plasma desktop or panel before
testing the transfer.

## Build and place the Decky plugin

Build dependencies are locked to pnpm 9.15.9. From the repository root:

```bash
cd prototype/hybrid-focus/decky/BazziteHybridFocus
corepack pnpm install --frozen-lockfile
corepack pnpm run build
test -s dist/index.js
```

For a local developer test, copy only the runtime files into Decky's plugin
directory:

```bash
plugin_source="$PWD"
plugin_target="$HOME/homebrew/plugins/BazziteHybridFocus"
install -d "$plugin_target"
cp -a "$plugin_source/dist" "$plugin_source/main.py" \
  "$plugin_source/package.json" "$plugin_source/plugin.json" "$plugin_target/"
```

Reload plugins from Decky's developer menu. The plugin has no `_root` flag and
talks directly to the mode-0600 user socket. Its panel is named **Hybrid Display
Control**.

## Operation

CLI equivalents are useful during recovery and tests:

```bash
bazzite-hybrid-focusctl desktop
bazzite-hybrid-focusctl game
bazzite-hybrid-focusctl toggle
bazzite-hybrid-focusctl status
```

For this first prototype, park the real desktop pointer on the second monitor
before opening QAM. The QAM closes after a successful transfer; the first South
button click can then focus the Plasma window under that pointer. Automatic
pointer placement on the selected display belongs to the later full Hybrid
session and is not claimed by this prototype.

The desktop profile currently maps:

| Controller input | Plasma action |
|---|---|
| Right stick | Pointer |
| South button | Primary click / activate |
| East button | Escape / back |
| D-pad | Arrow keys |
| Bumpers | Scroll |
| Right trigger | Primary click |
| Left trigger | Secondary click |

Controller prompts are classified from InputPlumber's source device paths and
udev vendor IDs: Microsoft/Xbox (`045e`), Sony/PlayStation (`054c`), and
Nintendo (`057e`). Unknown, unavailable, or mixed identities intentionally use
the neutral label.

## Diagnostics

Create a bounded JSON report with:

```bash
bazzite-hybrid-focus-diagnostics > "$HOME/hybrid-focus-diagnostics.json"
```

The report contains only service state, focus target, controller paths/names,
active and saved profile names, glyph family, and at most 100 service journal
lines. It does not dump the complete process environment.

## Recovery and removal

First request the game profile explicitly:

```bash
bazzite-hybrid-focusctl game
```

If the socket is unavailable, restart the user service; startup recovery reads
the saved original profile and restores it:

```bash
systemctl --user restart bazzite-hybrid-focus.service
bazzite-hybrid-focusctl game
```

Then remove the prototype:

```bash
./prototype/hybrid-focus/uninstall-user.sh
```

The uninstaller requests `game` before disabling the service and removes only
the files installed by this prototype. Remove the local Decky plugin directory
separately after reloading Decky.

## Prototype limits

- This package validates controller focus only; it does not yet install the
  complete optional Hybrid Gaming Mode session or automated display selector.
- Nested Gamescope must be started and placed on the gaming display manually.
- HDR, VRR, direct scan-out, latency, display hotplug, and automatic controller
  chords are outside this first controller-focus test.
- Controller exclusivity and the InputPlumber profile schema must pass the Dell
  ten-cycle hardware test before any container or ISO integration is proposed.

Use [the Dell checklist](../../docs/hybrid-focus-dell-test.md) for the
required validation order and acceptance criteria.
