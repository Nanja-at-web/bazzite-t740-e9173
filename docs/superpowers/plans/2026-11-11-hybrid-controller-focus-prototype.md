# Hybrid Controller Focus Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a user-installable, reversible prototype that explicitly transfers controller control between Steam/Gamescope and a secondary Plasma workspace without creating a container image or ISO.

**Architecture:** A Python user service owns a two-state `game`/`desktop` state machine and talks to InputPlumber only through argv-based `busctl` calls. A mode-0600 Unix socket accepts four allowlisted commands from a CLI, a Decky QAM plugin, and a Plasma return launcher. The prototype lives entirely under `prototype/hybrid-focus/`; its installer writes only into the current user's home and can be removed without changing the immutable Bazzite deployment.

**Tech Stack:** Python 3 standard library, systemd user units, InputPlumber D-Bus API, Decky Loader TypeScript/React plugin, freedesktop desktop entry, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-11-hybrid-gaming-mode-design.md`

## Global Constraints

- Prototype only: do not modify `Containerfile`, `system_files/`, `image-lock.json`, the direct Gamescope session, or either ISO workflow.
- Do not start a container build, publish an image, move the payload lock, or start an ISO build.
- Ordinary pointer movement or monitor-edge contact never changes controller ownership.
- HUD crosshairs and captured relative game pointers are not inputs to this prototype.
- Only `game`, `desktop`, `toggle`, and `status` are accepted control requests.
- No root daemon, `sudo`, shell evaluation, or arbitrary command execution.
- InputPlumber profile changes must be rolled back on partial failure and restored on normal service stop.
- If the original profile cannot be resolved uniquely, switching to Desktop must fail before changing any device.
- Unknown or mixed controller families use neutral Confirm/Back labels instead of guessed glyphs.
- Decky failure must not disable the CLI and Plasma return launcher.
- All installation is user-local and reversible.

## Review Focus

- InputPlumber exposes zero or more than one composite controller: return a diagnostic result and never guess silently.
- Two devices have different original profiles and the second profile load fails: restore the first device before reporting failure.
- The daemon crashes or is stopped while Desktop control is active: restart recovery must restore every recorded original profile before accepting new transitions.
- A client with another UID reaches the socket or sends malformed/oversized JSON: reject it without state change.
- Xbox, PlayStation, Nintendo, unknown, and mixed-device identity sets: select the correct family or neutral fallback deterministically.

---

### Task 1: Focus state model and controller-family classification

**Files:**
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/__init__.py`
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/model.py`
- Create: `tests/test_hybrid_focus_model.py`

**Interfaces:**
- Produces: `FocusTarget(str, Enum)` with `GAME` and `DESKTOP`.
- Produces: immutable `ControllerDevice(path, name, vendor_id, product_id, profile_name)`.
- Produces: immutable `FocusStatus(target, devices, glyph_family, degraded, message)`.
- Produces: `classify_glyph_family(devices: Sequence[ControllerDevice]) -> Literal["xbox", "playstation", "nintendo", "neutral"]`.
- Consumes: no earlier task interfaces.

- [ ] **Step 1: Write the failing model tests**

Cover exact enum values, Microsoft VID `045e` → `xbox`, Sony VID `054c` → `playstation`, Nintendo VID `057e` → `nintendo`, unknown → `neutral`, and mixed known families → `neutral`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_model -v`  
Expected: FAIL because `bazzite_hybrid_focus.model` does not exist.

- [ ] **Step 3: Implement the immutable model and pure classifier**

Tests add `prototype/hybrid-focus/src` to `sys.path`. Normalize hexadecimal IDs case-insensitively and without guessing from product names when VID is absent.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_model -v`  
Expected: all model tests PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat: add hybrid focus state model"`

### Task 2: InputPlumber adapter and transactional transitions

**Files:**
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/inputplumber.py`
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/controller.py`
- Create: `prototype/hybrid-focus/inputplumber/bazzite-hybrid-desktop.yaml`
- Create: `tests/test_hybrid_focus_inputplumber.py`
- Create: `tests/test_hybrid_focus_controller.py`

**Interfaces:**
- Consumes: model types from Task 1.
- Produces: `InputPlumberAdapter(command_runner, profile_roots, desktop_profile)`.
- Produces: `InputPlumberAdapter.discover() -> list[ControllerDevice]`.
- Produces: `InputPlumberAdapter.resolve_profile(profile_name: str) -> pathlib.Path`, requiring exactly one matching YAML `name:`.
- Produces: `InputPlumberAdapter.load_profile(device_path: str, profile_path: Path) -> None`.
- Produces: `FocusController(adapter, state_store)` with `set_target(FocusTarget) -> FocusStatus`, `toggle() -> FocusStatus`, `status() -> FocusStatus`, and `restore() -> FocusStatus`.

- [ ] **Step 1: Write failing adapter tests**

Use a fake command runner. Assert argv arrays for `busctl tree`, `get-property ... ProfileName`, and `LoadProfilePath s <path>`; test no device, malformed bus output, unique profile resolution, missing profile, and duplicate profile names.

- [ ] **Step 2: Run the adapter tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_inputplumber -v`  
Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement the minimal adapter**

Never invoke a shell. Discover only `/org/shadowblip/InputPlumber/CompositeDeviceN` paths. Read controller metadata when exposed; absent identity remains neutral.

- [ ] **Step 4: Add and validate the Desktop profile**

The YAML declares `target_devices: [keyboard, mouse]` and no gamepad target. Map right stick to pointer, South to left click/activate, East to Escape/Back, D-pad to arrow keys, bumpers to vertical scrolling, and triggers to mouse buttons. Contract tests parse the relevant keys without adding a YAML dependency.

- [ ] **Step 5: Write failing transactional controller tests**

Cover game→desktop capture of every original profile, idempotent requests, desktop→game restoration, partial-load rollback, unresolved original profile fail-closed behavior, state-file mode `0600`, and restart recovery from a stale Desktop state file.

- [ ] **Step 6: Run controller tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_controller -v`  
Expected: FAIL because `FocusController` does not exist.

- [ ] **Step 7: Implement transactional transitions**

Write state atomically beneath `$XDG_RUNTIME_DIR/bazzite-hybrid-focus/state.json`. Resolve every original profile before changing the first device. On failure, restore already changed devices in reverse order and return degraded status if rollback itself fails.

- [ ] **Step 8: Run Task 2 tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_inputplumber tests.test_hybrid_focus_controller -v`  
Expected: all Task 2 tests PASS.

- [ ] **Step 9: Commit**

`git commit -m "feat: add transactional InputPlumber focus switching"`

### Task 3: Local daemon, allowlisted protocol, and CLI

**Files:**
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/protocol.py`
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/server.py`
- Create: `prototype/hybrid-focus/src/bazzite_hybrid_focus/client.py`
- Create: `prototype/hybrid-focus/bin/bazzite-hybrid-focusd`
- Create: `prototype/hybrid-focus/bin/bazzite-hybrid-focusctl`
- Create: `prototype/hybrid-focus/systemd/bazzite-hybrid-focus.service`
- Create: `tests/test_hybrid_focus_protocol.py`
- Create: `tests/test_hybrid_focus_service_contract.py`

**Interfaces:**
- Consumes: `FocusController` from Task 2.
- Produces: newline-delimited JSON request `{"version":1,"command":"game|desktop|toggle|status"}`.
- Produces: response `{"ok":bool,"target":str,"glyph_family":str,"degraded":bool,"message":str}`.
- Produces: `serve(socket_path, controller, stop_event) -> None`.
- Produces: CLI exit 0 for successful requests, 2 for rejected requests, and 3 for unavailable service.

- [ ] **Step 1: Write failing protocol tests**

Test all four commands, unknown keys, unknown commands, invalid UTF-8, invalid JSON, payloads above 4096 bytes, and exact response fields.

- [ ] **Step 2: Run protocol tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_protocol -v`  
Expected: FAIL because protocol functions do not exist.

- [ ] **Step 3: Implement the pure protocol parser/serializer**

Reject extra fields and never convert input into executable code or argv.

- [ ] **Step 4: Write failing socket/service contract tests**

Use a temporary Unix socket. Assert mode `0600`, peer-UID rejection through an injectable credential checker, one response per request, concurrent requests serialized by one transition lock, and service shutdown calling `restore()`.

- [ ] **Step 5: Run service tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_service_contract -v`  
Expected: FAIL because server/client entry points do not exist.

- [ ] **Step 6: Implement daemon, client, entry points, and user unit**

The service uses `%t/bazzite-hybrid-focus/control.sock`, `Restart=on-failure`, and an `ExecStop`/signal path that restores Game state. The CLI accepts only the four positional commands.

- [ ] **Step 7: Run Task 3 tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_protocol tests.test_hybrid_focus_service_contract -v`  
Expected: all Task 3 tests PASS.

- [ ] **Step 8: Commit**

`git commit -m "feat: add hybrid focus user service and CLI"`

### Task 4: Reversible user installer and Plasma return action

**Files:**
- Create: `prototype/hybrid-focus/install-user.sh`
- Create: `prototype/hybrid-focus/uninstall-user.sh`
- Create: `prototype/hybrid-focus/applications/bazzite-hybrid-return-game.desktop`
- Create: `prototype/hybrid-focus/applications/bazzite-hybrid-send-desktop.desktop`
- Create: `tests/test_hybrid_focus_installer.py`

**Interfaces:**
- Consumes: Task 2 profile and Task 3 service/CLI.
- Produces: user-local installation beneath `~/.local/share/bazzite-hybrid-focus`, `~/.local/bin`, `~/.config/systemd/user`, and `~/.local/share/applications`.
- Produces: uninstall that restores Game state before removing files.
- Produces: controller-operable launchers named **Controller to Desktop 2** and **Return Controller to Game**.

- [ ] **Step 1: Write failing installer contract tests**

Run installers against temporary HOME/XDG directories with mocked `systemctl`. Assert no `sudo`, no writes outside allowlisted user paths, executable modes, service reload/enable, idempotent reinstall, uninstall restoration before deletion, and preservation of unrelated files.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_installer -v`  
Expected: FAIL because installer files do not exist.

- [ ] **Step 3: Implement installer, uninstaller, and desktop entries**

The installer checks for `busctl`, InputPlumber service visibility, the Desktop profile schema header, and Python 3 before enabling the service. It prints how to pin the return launcher to the secondary Plasma panel/desktop.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_installer -v`  
Expected: all installer tests PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat: add reversible hybrid focus prototype installer"`

### Task 5: Decky QAM control and neutral fallback

**Files:**
- Create: `prototype/hybrid-focus/decky/BazziteHybridFocus/plugin.json`
- Create: `prototype/hybrid-focus/decky/BazziteHybridFocus/package.json`
- Create: `prototype/hybrid-focus/decky/BazziteHybridFocus/pnpm-lock.yaml`
- Create: `prototype/hybrid-focus/decky/BazziteHybridFocus/tsconfig.json`
- Create: `prototype/hybrid-focus/decky/BazziteHybridFocus/src/index.tsx`
- Create: `prototype/hybrid-focus/decky/BazziteHybridFocus/main.py`
- Create: `tests/test_hybrid_focus_decky_contract.py`

**Interfaces:**
- Consumes: Task 3 socket protocol and `DECKY_USER_HOME`.
- Produces: backend call `set_target("desktop")` and `get_status()`.
- Produces: QAM panel title **Hybrid Display Control**, action **Controller to Desktop 2**, current target, and glyph-family label.
- Produces: no-root Decky plugin; `plugin.json` must not include `_root`.

- [ ] **Step 1: Write failing Decky contract tests**

Assert no root flag, no `shell=True`/`os.system`, only the two backend methods, use of the mode-0600 socket through the shared protocol, and neutral label for unknown/mixed family.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_decky_contract -v`  
Expected: FAIL because plugin files do not exist.

- [ ] **Step 3: Implement backend and QAM source**

The Python backend runs as the Decky user and connects directly to `$XDG_RUNTIME_DIR/bazzite-hybrid-focus/control.sock`; it never invokes the CLI or a shell. The frontend uses Decky's `ButtonItem` and displays a toast after the state response.

- [ ] **Step 4: Build the plugin bundle**

Run from the plugin directory: `corepack pnpm install --frozen-lockfile && corepack pnpm run build`  
Expected: exit 0 and `dist/index.js` exists. Do not publish or install automatically.

- [ ] **Step 5: Run contract tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_decky_contract -v`  
Expected: all Decky contract tests PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat: add Decky hybrid focus control"`

### Task 6: Diagnostics, documentation, and Dell hardware test package

**Files:**
- Create: `prototype/hybrid-focus/bin/bazzite-hybrid-focus-diagnostics`
- Create: `prototype/hybrid-focus/README.md`
- Create: `docs/hybrid-focus-dell-test.md`
- Create: `tests/test_hybrid_focus_diagnostics.py`
- Modify: `tests/test_build_provenance.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: read-only diagnostics containing service state, focus target, controller paths/names, original and active profile names, glyph family, and bounded service journal.
- Produces: Dell checklist and rollback steps.
- Produces: repository guard proving container, direct Gaming Mode, payload lock, and ISO workflows remain unchanged relative to the plan base commit.

- [ ] **Step 1: Write failing diagnostics/privacy tests**

Assert diagnostics contain the allowlisted fields, cap journal output, omit the complete process environment, and do not use `sudo`.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_hybrid_focus_diagnostics -v`  
Expected: FAIL because diagnostics do not exist.

- [ ] **Step 3: Implement diagnostics and README**

Document installation from the feature branch, Decky plugin placement, service start, QAM/launcher operation, expected notifications, log collection, uninstall, and recovery command.

- [ ] **Step 4: Add repository non-regression guards**

Record SHA-256 fixtures for `system_files/etc/gamescope-session-plus/sessions.d/steam`, `image-lock.json`, and `.github/workflows/build-disk.yml`; tests fail if this prototype changes them. Assert no workflow in the branch can publish an ISO automatically.

- [ ] **Step 5: Write the Dell two-monitor checklist**

Order: verify ordinary Gaming Mode, install prototype in Desktop Mode, start nested Gamescope manually, switch Game→Desktop through QAM, verify game receives no controller actions, operate Plasma with the controller, return through the Plasma launcher, repeat ten cycles, collect diagnostics, uninstall, and verify ordinary Gaming Mode again.

- [ ] **Step 6: Run the complete suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`  
Expected: all tests PASS.

- [ ] **Step 7: Commit**

`git commit -m "docs: add Dell hybrid focus prototype test package"`

## Prototype completion gate

The branch is ready for the user's Dell test only when:

1. the complete Python suite passes;
2. the Decky TypeScript bundle builds;
3. no image, container, payload lock, or ISO file changed;
4. no workflow has published anything;
5. install/uninstall succeeds in temporary user directories;
6. a fresh whole-branch review finds no Critical or Important issue.

The Dell test is successful only when ten Game↔Desktop cycles complete without controller input reaching both targets, the return launcher remains reachable, and uninstall restores the pre-test controller profile.
