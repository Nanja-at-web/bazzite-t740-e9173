import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototype/hybrid-focus"
DIAGNOSTICS = PROTOTYPE / "bin/bazzite-hybrid-focus-diagnostics"


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fake_bin = self.root / "bin"
        self.runtime = self.root / "runtime"
        self.data = self.root / "data"
        for directory in (self.fake_bin, self.runtime, self.data):
            directory.mkdir()

        self.make_fake("systemctl", 'printf "active\\n"\n')
        self.make_fake(
            "journalctl",
            'i=1; while [ "$i" -le 150 ]; do printf "journal-%03d\\n" "$i"; i=$((i+1)); done\n',
        )
        self.make_fake(
            "busctl",
            'case "$*" in\n'
            '  *" tree "*) printf "/org/shadowblip/InputPlumber/CompositeDevice0\\n" ;;\n'
            '  *" Name") printf "s \\\"Test Controller\\\"\\n" ;;\n'
            '  *" ProfileName") printf "s \\\"Game Profile\\\"\\n" ;;\n'
            '  *" SourceDevicePaths") printf "as 0\\n" ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n',
        )
        state_dir = self.runtime / "bazzite-hybrid-focus"
        state_dir.mkdir()
        (state_dir / "state.json").write_text(
            json.dumps({
                "version": 1,
                "target": "desktop",
                "original_profiles": {
                    "/org/shadowblip/InputPlumber/CompositeDevice0":
                        "/usr/share/inputplumber/profiles/game.yaml",
                },
            })
        )

    def make_fake(self, name, body):
        path = self.fake_bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def test_output_is_allowlisted_and_journal_is_bounded(self):
        environment = os.environ | {
            "PATH": f"{self.fake_bin}:{os.environ['PATH']}",
            "PYTHONPATH": str(PROTOTYPE / "src"),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_DATA_HOME": str(self.data),
            "DO_NOT_LEAK_THIS_SECRET": "diagnostics-secret",
        }
        result = subprocess.run(
            [str(DIAGNOSTICS)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            set(report),
            {"schema_version", "service_state", "focus", "controllers", "journal"},
        )
        self.assertEqual(
            set(report["focus"]),
            {"target", "glyph_family", "degraded", "message"},
        )
        self.assertEqual(report["focus"]["target"], "desktop")
        self.assertEqual(report["focus"]["glyph_family"], "neutral")
        self.assertEqual(len(report["journal"]), 100)
        self.assertNotIn("diagnostics-secret", result.stdout)
        self.assertEqual(
            report["controllers"][0],
            {
                "path": "/org/shadowblip/InputPlumber/CompositeDevice0",
                "name": "Test Controller",
                "active_profile": "Game Profile",
                "original_profile": "game.yaml",
            },
        )

    def test_script_is_read_only_unprivileged_and_executable(self):
        source = DIAGNOSTICS.read_text()
        self.assertNotIn("sudo", source)
        self.assertNotIn("dict(os.environ)", source)
        self.assertNotIn("os.environ.items", source)
        self.assertNotIn("--vacuum", source)
        self.assertNotIn("--rotate", source)
        self.assertTrue(stat.S_IMODE(DIAGNOSTICS.stat().st_mode) & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
