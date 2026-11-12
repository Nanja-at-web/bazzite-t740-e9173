# Dell OptiPlex 5080 Hybrid Focus hardware test

This checklist validates only the controller-focus prototype on the Dell
OptiPlex 5080 Micro with Intel UHD 630 and two monitors. It does not authorize a
container build, ISO build, merge to `main`, or installation on the HP t740.

## Test prerequisites

- Two monitors are enabled as independent Plasma workspaces.
- Ordinary Bazzite Gaming Mode and hardware rendering already work.
- A test controller is connected.
- A physical keyboard and mouse remain connected for recovery.
- The repository branch is `design/hybrid-gaming-mode`.
- No important game or document is left unsaved.

Record before starting:

| Item | Value |
|---|---|
| Bazzite build | |
| Kernel | |
| InputPlumber version | |
| Decky version | |
| Controller model | |
| Expected glyph family | Xbox / PlayStation / Nintendo / Neutral |
| Gaming monitor | |
| Desktop monitor | |

## A. Verify the unchanged baseline

1. Start ordinary Gaming Mode.
2. Confirm Steam Gamepad UI appears on the intended gaming monitor.
3. Start a small test game and confirm hardware rendering and controller input.
4. Exit the game and return to Desktop Mode.
5. Confirm both Plasma monitors still work independently.

Stop if this baseline fails; the prototype cannot explain a pre-existing fault.

## B. Install in Desktop Mode

From the repository root:

```bash
./prototype/hybrid-focus/install-user.sh
systemctl --user status bazzite-hybrid-focus.service --no-pager
bazzite-hybrid-focusctl status
```

Pin **Return Controller to Game** to the secondary Plasma desktop or panel.
Build and place the Decky plugin exactly as described in
`prototype/hybrid-focus/README.md`, then reload Decky plugins.

Expected:

- the service is `active`;
- status is `game` and not degraded;
- QAM contains **Hybrid Display Control**;
- the controller family matches the connected device, or safely shows Neutral
  if the identity is unavailable or ambiguous.

## C. Start nested Gamescope manually

Close any existing Steam instance cleanly, then start a disposable nested test
session from Plasma. Adjust resolution and refresh rate to the gaming monitor:

```bash
gamescope -W 1920 -H 1080 -r 60 -f -- steam -gamepadui
```

Use Plasma's window-to-screen shortcut or window menu to place the Gamescope
window on the chosen gaming monitor. Keep the second monitor as the ordinary
Plasma workspace. Start a small test game and confirm hardware rendering.

If nested Gamescope itself fails, collect its terminal output and stop. Do not
continue by changing the ordinary Bazzite Gamescope session.

## D. Perform one complete focus cycle

1. Use the physical mouse to park the real pointer over a harmless test window
   on the second Plasma monitor; do not click inside the game again.
2. While the game is running, open Decky QAM with the controller.
3. Select **Controller to Desktop 2** and confirm QAM closes.
4. Press South once over the parked pointer to focus the Plasma test window.
5. Press D-pad, South/East, bumpers, triggers, and move the right stick.
6. Confirm the game receives **none** of those actions.
7. Confirm the second Plasma workspace receives pointer, click, back, arrow, and
   scroll actions according to the mapping.
8. Activate **Return Controller to Game** on the Plasma workspace using the
   controller.
9. Confirm Steam/the game receives controller input again.
10. Confirm Plasma no longer receives the emulated desktop actions.

Any simultaneous action on both targets is an immediate failure. Use the
physical keyboard/mouse and run `bazzite-hybrid-focusctl game` to recover.

## E. Repeat ten cycles

Repeat section D without restarting the service or reconnecting the controller.

| Cycle | Game→Desktop | No game leakage | Plasma usable | Desktop→Game | No desktop leakage | Result/notes |
|---:|---|---|---|---|---|---|
| 1 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 2 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 3 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 4 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 5 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 6 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 7 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 8 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 9 | ☐ | ☐ | ☐ | ☐ | ☐ | |
| 10 | ☐ | ☐ | ☐ | ☐ | ☐ | |

Also record whether the QAM labels match the Xbox, PlayStation, Nintendo, or
neutral layout actually in use.

## F. Collect diagnostics

Collect one report in `game`, one in `desktop`, and one after returning to
`game`:

```bash
bazzite-hybrid-focusctl game
bazzite-hybrid-focus-diagnostics > "$HOME/hybrid-focus-game.json"
bazzite-hybrid-focusctl desktop
bazzite-hybrid-focus-diagnostics > "$HOME/hybrid-focus-desktop.json"
bazzite-hybrid-focusctl game
bazzite-hybrid-focus-diagnostics > "$HOME/hybrid-focus-restored.json"
```

Preserve the nested Gamescope terminal output separately if an error occurred.

## G. Uninstall and verify rollback

```bash
bazzite-hybrid-focusctl game
./prototype/hybrid-focus/uninstall-user.sh
```

Remove the local Decky plugin directory and reload Decky. Reboot once, start
ordinary Gaming Mode, run the same test game, and verify normal controller input
and image output. Confirm both displays still work in Desktop Mode.

## Acceptance gate

The prototype passes only when all of the following are true:

- all ten cycles complete;
- controller events never reach both targets at once;
- the desktop return launcher remains controller-operable;
- each return restores the exact original InputPlumber profile;
- diagnostics show the expected target and active/original profiles;
- uninstall and reboot restore unchanged ordinary Gaming Mode;
- no container, payload lock, direct Gamescope session, workflow, image, or ISO
  changed during the test.

If any item fails, keep the work on the feature branch and attach the three JSON
reports plus the cycle number and exact controller action that failed.
