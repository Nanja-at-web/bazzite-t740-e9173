import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototype/hybrid-focus"
INSTALL = PROTOTYPE / "install-user.sh"
UNINSTALL = PROTOTYPE / "uninstall-user.sh"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.bin_home = self.root / "bin-home"
        self.runtime = self.root / "runtime"
        self.fake_bin = self.root / "fake-bin"
        for directory in (
            self.home,
            self.data,
            self.config,
            self.bin_home,
            self.runtime,
            self.fake_bin,
        ):
            directory.mkdir()
        self.systemctl_log = self.root / "systemctl.log"
        self.make_fake("systemctl", f'printf "%s\\n" "$*" >> "{self.systemctl_log}"\n')
        self.make_fake("busctl", "exit 0\n")
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_BIN_HOME": str(self.bin_home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "PATH": f"{self.fake_bin}:{os.environ['PATH']}",
        })

    def make_fake(self, name, body):
        path = self.fake_bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_script(self, script):
        result = subprocess.run(
            ["bash", str(script)],
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"{script.name} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def test_scripts_never_request_root(self):
        for script in (INSTALL, UNINSTALL):
            self.assertNotIn("sudo", script.read_text())

    def test_entry_points_follow_xdg_data_home(self):
        for executable in (
            "bazzite-hybrid-focusd",
            "bazzite-hybrid-focusctl",
            "bazzite-hybrid-focus-diagnostics",
        ):
            source = (PROTOTYPE / "bin" / executable).read_text()
            self.assertIn("XDG_DATA_HOME", source)

    def test_install_is_user_local_and_idempotent(self):
        self.run_script(INSTALL)
        self.run_script(INSTALL)
        install_root = self.data / "bazzite-hybrid-focus"
        self.assertTrue((install_root / "src/bazzite_hybrid_focus/model.py").is_file())
        self.assertTrue(
            (install_root / "inputplumber/bazzite-hybrid-desktop.yaml").is_file()
        )
        for executable in (
            "bazzite-hybrid-focusd",
            "bazzite-hybrid-focusctl",
            "bazzite-hybrid-focus-diagnostics",
        ):
            path = self.bin_home / executable
            self.assertTrue(path.is_file())
            self.assertTrue(stat.S_IMODE(path.stat().st_mode) & stat.S_IXUSR)
        self.assertTrue(
            (self.config / "systemd/user/bazzite-hybrid-focus.service").is_file()
        )
        installed_unit = (
            self.config / "systemd/user/bazzite-hybrid-focus.service"
        ).read_text()
        self.assertIn(str(self.bin_home / "bazzite-hybrid-focusd"), installed_unit)
        self.assertIn(str(self.bin_home / "bazzite-hybrid-focusctl"), installed_unit)
        self.assertNotIn("@BIN_HOME@", installed_unit)
        for launcher in (
            "bazzite-hybrid-send-desktop.desktop",
            "bazzite-hybrid-return-game.desktop",
        ):
            installed_launcher = self.data / "applications" / launcher
            self.assertTrue(installed_launcher.is_file())
            self.assertIn(
                str(self.bin_home / "bazzite-hybrid-focusctl"),
                installed_launcher.read_text(),
            )
        log = self.systemctl_log.read_text()
        self.assertIn("--user daemon-reload", log)
        self.assertIn("--user enable --now bazzite-hybrid-focus.service", log)
        self.assertFalse((self.root / "usr").exists())

    def test_uninstall_restores_before_disabling_and_preserves_unrelated_files(self):
        self.run_script(INSTALL)
        unrelated = self.data / "applications/unrelated.desktop"
        unrelated.write_text("keep")
        source = UNINSTALL.read_text()
        self.assertLess(
            source.index('"${bin_home}/bazzite-hybrid-focusctl" game'),
            source.index("systemctl --user disable --now"),
        )
        self.run_script(UNINSTALL)
        self.assertEqual(unrelated.read_text(), "keep")
        self.assertFalse((self.data / "bazzite-hybrid-focus").exists())
        self.assertFalse((self.bin_home / "bazzite-hybrid-focusd").exists())
        self.assertFalse(
            (self.bin_home / "bazzite-hybrid-focus-diagnostics").exists()
        )
        self.assertFalse(
            (self.config / "systemd/user/bazzite-hybrid-focus.service").exists()
        )

    def test_desktop_entries_have_expected_actions_and_no_shell(self):
        entries = {
            "bazzite-hybrid-send-desktop.desktop": (
                "Controller to Desktop 2",
                '"@BIN_HOME@/bazzite-hybrid-focusctl" desktop',
            ),
            "bazzite-hybrid-return-game.desktop": (
                "Return Controller to Game",
                '"@BIN_HOME@/bazzite-hybrid-focusctl" game',
            ),
        }
        for filename, (name, command) in entries.items():
            source = (PROTOTYPE / "applications" / filename).read_text()
            self.assertIn(f"Name={name}", source)
            self.assertIn(f"Exec={command}", source)
            self.assertNotIn("sh -c", source)
            self.assertNotIn("Terminal=true", source)


if __name__ == "__main__":
    unittest.main()
