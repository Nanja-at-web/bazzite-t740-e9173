import json
import os
import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-focus/src"))

from bazzite_hybrid_focus.controller import (  # noqa: E402
    FocusController,
    JsonStateStore,
)
from bazzite_hybrid_focus.inputplumber import InputPlumberError  # noqa: E402
from bazzite_hybrid_focus.model import ControllerDevice, FocusTarget  # noqa: E402


class FakeAdapter:
    def __init__(self, devices, profiles, fail_on=None, desktop_profile=None):
        self.devices = devices
        self.profiles = profiles
        self.fail_on = fail_on
        self.loads = []
        self.desktop_profile = desktop_profile or Path("/profiles/desktop.yaml")

    def discover(self):
        return list(self.devices)

    def resolve_profile(self, name):
        if name not in self.profiles:
            raise InputPlumberError(f"profile {name} not found")
        return Path(self.profiles[name])

    def load_profile(self, device_path, profile_path):
        call = (device_path, Path(profile_path))
        self.loads.append(call)
        if call == self.fail_on:
            raise InputPlumberError("load failed")


class FocusControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "state.json"
        self.store = JsonStateStore(self.state_path)
        self.devices = [
            ControllerDevice("/device0", "One", "045e", None, "Default"),
            ControllerDevice("/device1", "Two", "045e", None, "Custom"),
        ]
        self.profiles = {
            "Default": "/profiles/default.yaml",
            "Custom": "/profiles/custom.yaml",
        }

    def controller(self, adapter=None):
        adapter = adapter or FakeAdapter(self.devices, self.profiles)
        return FocusController(adapter, self.store), adapter

    def test_game_to_desktop_captures_all_original_profiles(self):
        controller, adapter = self.controller()
        status = controller.set_target(FocusTarget.DESKTOP)
        self.assertEqual(status.target, FocusTarget.DESKTOP)
        self.assertEqual(
            adapter.loads,
            [
                ("/device0", Path("/profiles/desktop.yaml")),
                ("/device1", Path("/profiles/desktop.yaml")),
            ],
        )
        state = json.loads(self.state_path.read_text())
        self.assertEqual(state["target"], "desktop")
        self.assertEqual(
            state["original_profiles"],
            {
                "/device0": "/profiles/default.yaml",
                "/device1": "/profiles/custom.yaml",
            },
        )
        self.assertEqual(os.stat(self.state_path).st_mode & 0o777, 0o600)

    def test_desktop_to_game_restores_exact_original_profiles(self):
        controller, adapter = self.controller()
        controller.set_target(FocusTarget.DESKTOP)
        adapter.loads.clear()
        status = controller.set_target(FocusTarget.GAME)
        self.assertEqual(status.target, FocusTarget.GAME)
        self.assertEqual(
            adapter.loads,
            [
                ("/device0", Path("/profiles/default.yaml")),
                ("/device1", Path("/profiles/custom.yaml")),
            ],
        )

    def test_idempotent_target_does_not_reload_profiles(self):
        controller, adapter = self.controller()
        controller.set_target(FocusTarget.DESKTOP)
        adapter.loads.clear()
        controller.set_target(FocusTarget.DESKTOP)
        self.assertEqual(adapter.loads, [])

    def test_unresolved_original_fails_before_any_profile_load(self):
        adapter = FakeAdapter(self.devices, {"Default": "/profiles/default.yaml"})
        controller, adapter = self.controller(adapter)
        status = controller.set_target(FocusTarget.DESKTOP)
        self.assertEqual(status.target, FocusTarget.GAME)
        self.assertTrue(status.degraded)
        self.assertEqual(adapter.loads, [])

    def test_partial_desktop_load_rolls_back_changed_devices(self):
        adapter = FakeAdapter(
            self.devices,
            self.profiles,
            fail_on=("/device1", Path("/profiles/desktop.yaml")),
        )
        controller, adapter = self.controller(adapter)
        status = controller.set_target(FocusTarget.DESKTOP)
        self.assertEqual(status.target, FocusTarget.GAME)
        self.assertTrue(status.degraded)
        self.assertEqual(
            adapter.loads,
            [
                ("/device0", Path("/profiles/desktop.yaml")),
                ("/device1", Path("/profiles/desktop.yaml")),
                ("/device0", Path("/profiles/default.yaml")),
            ],
        )

    def test_toggle_switches_between_targets(self):
        controller, _ = self.controller()
        self.assertEqual(controller.toggle().target, FocusTarget.DESKTOP)
        self.assertEqual(controller.toggle().target, FocusTarget.GAME)

    def test_restore_recovers_stale_desktop_state(self):
        self.store.save({
            "version": 1,
            "target": "desktop",
            "original_profiles": {
                "/device0": "/profiles/default.yaml",
                "/device1": "/profiles/custom.yaml",
            },
        })
        controller, adapter = self.controller()
        status = controller.restore()
        self.assertEqual(status.target, FocusTarget.GAME)
        self.assertEqual(
            adapter.loads,
            [
                ("/device0", Path("/profiles/default.yaml")),
                ("/device1", Path("/profiles/custom.yaml")),
            ],
        )


if __name__ == "__main__":
    unittest.main()
