import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("metadata", ROOT / "installer/build-metadata.py")
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)
PIN = "ghcr.io/example/image@sha256:" + "a" * 64


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "usr/lib").mkdir(parents=True)
        (self.root / "usr/lib/os-release").write_text(
            'NAME=Bazzite\nVERSION_ID=45\nPRETTY_NAME="Bazzite 45"\nBUILD_ID=45.20261108\n'
        )

    def write(self, role="system", **kwargs):
        return metadata.write_metadata(self.root, role, "t740-test", "b" * 40,
                                       "2026-11-08T09:00:00Z", PIN, **kwargs)

    def test_system_version_and_commit_are_independent(self):
        result = self.write()
        self.assertEqual(result["os"]["VERSION_ID"], "45")
        self.assertEqual(result["os"]["BUILD_ID"], "45.20261108")
        self.assertEqual(result["build_id"], "t740-test")
        self.assertEqual(result["role"], "system")
        self.assertEqual(json.loads((self.root / "usr/share/t740/build-info.json").read_text()), result)

    def test_installer_pins_payload_separately(self):
        result = self.write("installer", payload=PIN)
        self.assertEqual(result["install_payload"], PIN)
        self.assertEqual(result["role"], "installer")

    def test_installer_rejects_mutable_payload(self):
        with self.assertRaises(ValueError):
            self.write("installer", payload="ghcr.io/example/image:latest")

    def test_rejects_mutable_or_malformed_base(self):
        for value in ("ghcr.io/example/image:stable", "ghcr.io/example/image@sha256:123", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                metadata.pinned(value)

    def test_preserves_upstream_metadata(self):
        path = self.root / "usr/share/ublue-os/image-info.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"image-name":"bazzite-deck","version":"45.test"}')
        self.assertEqual(self.write()["upstream_image_info"]["version"], "45.test")

    def test_missing_os_build_is_explicit_null(self):
        (self.root / "usr/lib/os-release").write_text('NAME="Bazzite"\n')
        self.assertIsNone(self.write()["os"]["BUILD_ID"])


class WiringTests(unittest.TestCase):
    def test_lock_has_three_pinned_inputs(self):
        data = json.loads((ROOT / "image-lock.json").read_text())
        self.assertEqual(data["platform"], "linux/amd64")
        for key in ("container_base", "installer_base", "install_payload"):
            metadata.pinned(data[key]["image"])

    def test_kickstart_keeps_digest_intact(self):
        source = (ROOT / "installer/titanoboa_hook_postrootfs.sh").read_text()
        self.assertIn('imageref="${INSTALL_IMAGE_PAYLOAD:', source)
        self.assertNotIn("$imageref:$imagetag", source)
        self.assertIn("ostreecontainer --url=$imageref --transport=containers-storage", source)

    def test_iso_trigger_excludes_development_branch(self):
        source = (ROOT / ".github/workflows/build-disk.yml").read_text()
        self.assertIn("branches: [main]", source)
        self.assertNotIn("pull_request:", source)

    def test_conky_separates_live_and_payload(self):
        source = (ROOT / "installer/system_files/shared/usr/share/conky/conky.conf").read_text()
        for label in ("LIVE OS:", "ISO BUILD:", "PAYLOAD OS:", "PAYLOAD BUILD:"):
            self.assertIn(label, source)
        self.assertNotIn("podman images -q", source)

    def test_diagnostics_reads_only_allowlisted_environment(self):
        source = (ROOT / "system_files/usr/bin/t740-gpu-diagnostics").read_text()
        self.assertIn("^(BACKEND|VULKAN_ADAPTER|DRI_PRIME|", source)
        self.assertNotIn("sudo ", source)


if __name__ == "__main__":
    unittest.main()
