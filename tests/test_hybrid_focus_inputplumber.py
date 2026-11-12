import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-focus/src"))
DESKTOP_PROFILE = (
    ROOT
    / "prototype/hybrid-focus/inputplumber/bazzite-hybrid-desktop.yaml"
)

from bazzite_hybrid_focus.inputplumber import (  # noqa: E402
    InputPlumberAdapter,
    InputPlumberError,
    resolve_source_identity,
)


class FakeRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class InputPlumberAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.desktop = self.root / "desktop.yaml"
        self.desktop.write_text("version: 1\nkind: DeviceProfile\nname: Desktop\n")

    def adapter(self, runner, identity_resolver=lambda _paths: (None, None)):
        return InputPlumberAdapter(
            runner, [self.root], self.desktop, identity_resolver=identity_resolver
        )

    def test_discover_uses_system_bus_and_reads_name_and_profile(self):
        runner = FakeRunner([
            "/org/shadowblip/InputPlumber\n"
            "/org/shadowblip/InputPlumber/CompositeDevice0\n",
            's "Xbox Controller"\n',
            's "Default"\n',
            'as 1 "/dev/input/event9"\n',
        ])
        devices = self.adapter(
            runner,
            identity_resolver=lambda paths: (
                ("045e", "0b13") if paths == ("/dev/input/event9",) else (None, None)
            ),
        ).discover()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Xbox Controller")
        self.assertEqual(devices[0].profile_name, "Default")
        self.assertEqual(devices[0].vendor_id, "045e")
        self.assertEqual(devices[0].product_id, "0b13")
        self.assertEqual(
            runner.calls[0],
            ["busctl", "--system", "tree", "org.shadowblip.InputPlumber", "--list"],
        )
        self.assertIn("Name", runner.calls[1])
        self.assertIn("ProfileName", runner.calls[2])
        self.assertIn("SourceDevicePaths", runner.calls[3])

    def test_discover_returns_empty_when_no_composite_device_exists(self):
        runner = FakeRunner(["/org/shadowblip/InputPlumber\n"])
        self.assertEqual(self.adapter(runner).discover(), [])

    def test_discover_rejects_malformed_string_property(self):
        runner = FakeRunner([
            "/org/shadowblip/InputPlumber/CompositeDevice0\n",
            "unexpected output",
        ])
        with self.assertRaises(InputPlumberError):
            self.adapter(runner).discover()

    def test_discover_rejects_malformed_source_path_property(self):
        runner = FakeRunner([
            "/org/shadowblip/InputPlumber/CompositeDevice0\n",
            's "Controller"\n',
            's "Default"\n',
            'as 2 "/dev/input/event9"\n',
        ])
        with self.assertRaisesRegex(InputPlumberError, "SourceDevicePaths"):
            self.adapter(runner).discover()

    def test_udev_identity_prefers_one_known_controller_family(self):
        responses = {
            "/dev/input/event9": "ID_VENDOR_ID=045e\nID_MODEL_ID=0b13\n",
            "/dev/hidraw3": "ID_VENDOR_ID=045e\nID_MODEL_ID=0b13\n",
        }
        calls = []

        def runner(argv):
            calls.append(argv)
            return responses[argv[-1]]

        self.assertEqual(
            resolve_source_identity(
                ("/dev/input/event9", "/dev/hidraw3"), command_runner=runner
            ),
            ("045e", "0b13"),
        )
        self.assertTrue(all(call[:4] == ["udevadm", "info", "--query=property", "--name"] for call in calls))

    def test_udev_identity_fails_neutral_for_mixed_known_families(self):
        responses = iter([
            "ID_VENDOR_ID=045e\nID_MODEL_ID=0b13\n",
            "ID_VENDOR_ID=054c\nID_MODEL_ID=0ce6\n",
        ])
        self.assertEqual(
            resolve_source_identity(
                ("/dev/input/event9", "/dev/input/event10"),
                command_runner=lambda _argv: next(responses),
            ),
            (None, None),
        )

    def test_resolve_profile_requires_one_unique_name(self):
        (self.root / "default.yaml").write_text("name: Default\n")
        adapter = self.adapter(FakeRunner([]))
        self.assertEqual(adapter.resolve_profile("Default"), self.root / "default.yaml")

    def test_resolve_profile_rejects_missing_name(self):
        with self.assertRaisesRegex(InputPlumberError, "not found"):
            self.adapter(FakeRunner([])).resolve_profile("Missing")

    def test_resolve_profile_rejects_duplicate_name(self):
        (self.root / "one.yaml").write_text("name: Default\n")
        (self.root / "two.yaml").write_text('name: "Default"\n')
        with self.assertRaisesRegex(InputPlumberError, "ambiguous"):
            self.adapter(FakeRunner([])).resolve_profile("Default")

    def test_load_profile_calls_dbus_method_without_shell(self):
        runner = FakeRunner([""])
        adapter = self.adapter(runner)
        device = "/org/shadowblip/InputPlumber/CompositeDevice0"
        adapter.load_profile(device, self.desktop)
        self.assertEqual(
            runner.calls,
            [[
                "busctl", "--system", "call", "org.shadowblip.InputPlumber",
                device, "org.shadowblip.Input.CompositeDevice",
                "LoadProfilePath", "s", str(self.desktop),
            ]],
        )

    def test_desktop_profile_has_only_keyboard_and_mouse_targets(self):
        source = DESKTOP_PROFILE.read_text()
        target_block = source.split("target_devices:", 1)[1].split("mapping:", 1)[0]
        self.assertIn("- keyboard", target_block)
        self.assertIn("- mouse", target_block)
        self.assertNotIn("- gamepad", target_block)
        for mapping in (
            "name: Pointer",
            "name: Activate",
            "name: Back",
            "name: Scroll Up",
            "name: Scroll Down",
        ):
            self.assertIn(mapping, source)
        self.assertIn("button: WheelUp", source)
        self.assertIn("button: WheelDown", source)
        self.assertNotIn("wheel:", source)


if __name__ == "__main__":
    unittest.main()
