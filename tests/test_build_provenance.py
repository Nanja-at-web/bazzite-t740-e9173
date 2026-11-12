import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
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
            'NAME=Bazzite\nVERSION_ID=45\nPRETTY_NAME="Bazzite 45"\nBUILD_ID=45.20261105\n'
        )

    def write(self, role="system", **kwargs):
        return metadata.write_metadata(self.root, role, "45.20261105.1-polaris-sdl", "b" * 40,
                                       "2026-11-08T09:00:00Z", PIN, **kwargs)

    def test_system_version_and_commit_are_independent(self):
        result = self.write()
        self.assertEqual(result["os"]["VERSION_ID"], "45")
        self.assertEqual(result["os"]["BUILD_ID"], "45.20261105")
        self.assertEqual(result["build_id"], "45.20261105.1-polaris-sdl")
        self.assertEqual(result["role"], "system")
        self.assertEqual(json.loads((self.root / "usr/share/t740/build-info.json").read_text()), result)

    def test_build_id_uses_bazzite_version_syntax(self):
        self.assertTrue(hasattr(metadata, "parse_build_id"),
                        "build metadata must parse the agreed Bazzite-style version")
        self.assertEqual(
            metadata.parse_build_id("45.20261105.1-polaris-sdl"),
            {
                "upstream_version": "45.20261105",
                "custom_revision": 1,
                "variant": "polaris-sdl",
            },
        )

    def test_metadata_records_structured_version(self):
        result = self.write()
        self.assertIn("version", result)
        self.assertEqual(
            result["version"],
            {
                "upstream_version": "45.20261105",
                "custom_revision": 1,
                "variant": "polaris-sdl",
            },
        )
        self.assertIn("target_hardware", result)
        self.assertEqual(result["target_hardware"]["system"], "HP t740 Thin Client")
        self.assertEqual(result["target_hardware"]["discrete_gpu"], "AMD Radeon E9173")
        self.assertIn("display_name", result)
        self.assertEqual(result["display_name"],
                         "Bazzite 45.20261105.1 (Polaris SDL)")

    def test_metadata_rejects_base_version_mismatch(self):
        (self.root / "usr/lib/os-release").write_text(
            'NAME=Bazzite\nVERSION_ID=45\nBUILD_ID="Stable (F45.20261104)"\n'
        )
        with self.assertRaisesRegex(ValueError, "does not match base OS"):
            self.write()

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

    def test_missing_os_build_is_rejected(self):
        (self.root / "usr/lib/os-release").write_text('NAME="Bazzite"\n')
        with self.assertRaisesRegex(ValueError, "Cannot determine Bazzite base version"):
            self.write()


class WiringTests(unittest.TestCase):
    def test_hybrid_prototype_does_not_change_release_inputs(self):
        expected = {
            "Containerfile":
                "57b687d068d75e145a9f68d11e7cb96df48f538b02cf760e56e173b3dbd6015e",
            "system_files/etc/gamescope-session-plus/sessions.d/steam":
                "bfa9fc32090f794eafe6e496812bc54b2d56382905d2dc8b094442d7b165dbd5",
            "image-lock.json":
                "230acb8bf6691ee0b5e45547d990477223933ebc666432db80dc3d7891747fc4",
            ".github/workflows/build.yml":
                "2f787653fd70a6327f5d0e073cf76c38b26dc0af66630a0bfc993492c4e91e69",
            ".github/workflows/build-disk.yml":
                "1b52d044d049aa55f4d1c0f9be31d0413794451cfb350ec4e9e8509cb8e44cb4",
        }
        for relative_path, digest in expected.items():
            with self.subTest(path=relative_path):
                actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
                self.assertEqual(actual, digest)

    def test_every_iso_workflow_is_manual_only(self):
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            source = workflow.read_text()
            if "titanoboa" not in source and "*.iso" not in source:
                continue
            with self.subTest(workflow=workflow.name):
                self.assertIn("\n  workflow_dispatch:\n", source)
                for automatic_trigger in ("push", "pull_request", "schedule"):
                    self.assertNotIn(f"\n  {automatic_trigger}:", source)

    def test_version_generator_uses_locked_bazzite_version(self):
        script = ROOT / "scripts/build-version.py"
        self.assertTrue(script.exists(), "missing build version generator")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            lock = directory / "image-lock.json"
            config = directory / "build-version.json"
            lock.write_text(json.dumps({
                "container_base": {"version": "45.20261105"},
            }))
            config.write_text(json.dumps({
                "custom_revision": 1,
                "variant": "polaris-sdl",
            }))
            result = subprocess.run(
                ["python3", str(script), "--lock", str(lock),
                 "--config", str(config)],
                check=True, capture_output=True, text=True,
            )
        self.assertEqual(result.stdout.strip(), "45.20261105.1-polaris-sdl")

    def test_container_build_uses_generated_version(self):
        source = (ROOT / "Justfile").read_text()
        self.assertIn("python3 scripts/build-version.py", source)
        self.assertNotIn('T740_BUILD_ID="t740-', source)
        self.assertNotIn('T740_BUILD_ID="${T740_BUILD_ID}-dirty"', source)
        self.assertGreaterEqual(source.count("python3 scripts/build-version.py"), 2)
        self.assertIn('BUILD_TAGS+=("${T740_BUILD_ID}")', source)

    def test_lock_has_three_pinned_inputs(self):
        data = json.loads((ROOT / "image-lock.json").read_text())
        self.assertEqual(data["platform"], "linux/amd64")
        for key in ("container_base", "installer_base", "install_payload"):
            metadata.pinned(data[key]["image"])
        self.assertEqual(data["container_base"]["version"], "45.20261105")
        payload_version = metadata.parse_build_id(data["install_payload"]["version"])
        self.assertEqual(
            payload_version["upstream_version"],
            data["container_base"]["version"],
        )

    def test_lock_refresh_captures_oci_version(self):
        source = (ROOT / "scripts/lock-images.py").read_text()
        self.assertIn('org.opencontainers.image.version', source)

    def test_kickstart_keeps_digest_intact(self):
        source = (ROOT / "installer/titanoboa_hook_postrootfs.sh").read_text()
        self.assertIn('imageref="${INSTALL_IMAGE_PAYLOAD:', source)
        self.assertNotIn("$imageref:$imagetag", source)
        self.assertIn("ostreecontainer --url=$imageref --transport=containers-storage", source)

    def test_iso_trigger_is_manual_only(self):
        source = (ROOT / ".github/workflows/build-disk.yml").read_text()
        self.assertIn("\n  workflow_dispatch:\n", source)
        for automatic_trigger in ("push", "pull_request", "schedule"):
            self.assertNotIn(f"\n  {automatic_trigger}:", source)

    def test_iso_uses_payload_version_and_versioned_filename(self):
        source = (ROOT / ".github/workflows/build-disk.yml").read_text()
        self.assertIn(".install_payload.version", source)
        self.assertIn('bazzite-t740-e9173-${BUILD_ID}-amd64.iso', source)
        self.assertNotIn('BUILD_ID="t740-iso-', source)
        self.assertNotIn("bazzite-t740-e9173-polaris-amd64.iso", source)

    def test_conky_separates_live_and_payload(self):
        source = (ROOT / "installer/system_files/shared/usr/share/conky/conky.conf").read_text()
        for label in ("LIVE OS:", "ISO BUILD:", "PAYLOAD OS:", "PAYLOAD BUILD:"):
            self.assertIn(label, source)
        self.assertNotIn("podman images -q", source)
        self.assertIn('.display_name // .build_id', source)

    def test_build_info_prefers_human_display_name(self):
        source = (ROOT / "system_files/usr/bin/t740-build-info").read_text()
        self.assertIn('.display_name // .build_id', source)

    def test_diagnostics_reads_only_allowlisted_environment(self):
        source = (ROOT / "system_files/usr/bin/t740-gpu-diagnostics").read_text()
        self.assertIn("^(BACKEND|VULKAN_ADAPTER|DRI_PRIME|", source)
        self.assertNotIn("sudo ", source)

    def test_polaris_sdl_variant_matches_session_configuration(self):
        version = json.loads((ROOT / "build-version.json").read_text())
        session = (ROOT / "system_files/etc/gamescope-session-plus/sessions.d/steam").read_text()
        self.assertEqual(version["variant"], "polaris-sdl")
        self.assertIn("export GAMESCOPE_BIN=/usr/bin/gamescope", session)
        self.assertIn("export BACKEND=sdl", session)
        self.assertNotIn("GAMESCOPE_BIN=/usr/bin/gamescope-legacy", session)

    def test_repository_release_uses_next_custom_revision(self):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/build-version.py")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertEqual(result.stdout.strip(), "45.20261105.2-polaris-sdl")

    def test_build_wires_deterministic_commit_time(self):
        source = (ROOT / "Justfile").read_text()
        containerfile = (ROOT / "Containerfile").read_text()
        self.assertIn("python3 scripts/build-created.py --format rfc3339", source)
        self.assertIn("python3 scripts/build-created.py --format epoch", source)
        self.assertIn('SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH}"', source)
        self.assertNotIn("T740_CREATED=$(date -u", source)
        self.assertNotIn('org.opencontainers.image.created=$(date -u', source)
        self.assertIn("DATE=$(python3 scripts/build-created.py --format rfc3339", source)
        self.assertNotIn("DATE=$(date", source)
        self.assertIn("ARG SOURCE_DATE_EPOCH", containerfile)
        self.assertIn('SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH"', containerfile)

    def test_publish_guard_runs_before_build_and_registry_push(self):
        source = (ROOT / ".github/workflows/build.yml").read_text()
        guard = source.index("python3 scripts/check-version-tag.py")
        build = source.index("- name: Build Image")
        push_loop = source.index("for tag in ${ALIAS_TAGS}")
        self.assertLess(guard, build)
        self.assertLess(guard, push_loop)

    def test_container_workflow_runs_provenance_tests(self):
        source = (ROOT / ".github/workflows/build.yml").read_text()
        self.assertIn("python3 -m unittest discover -s tests -v", source)
        self.assertIn('PYTHONDONTWRITEBYTECODE: "1"', source)


class ReleaseScriptTests(unittest.TestCase):
    def test_commit_timestamp_is_stable_in_both_formats(self):
        script = ROOT / "scripts/build-created.py"
        self.assertTrue(script.exists(), "missing deterministic build timestamp generator")
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.invalid"], check=True)
            (repository / "file").write_text("content")
            subprocess.run(["git", "-C", str(repository), "add", "file"], check=True)
            environment = os.environ | {
                "GIT_AUTHOR_DATE": "2026-11-08T12:34:56Z",
                "GIT_COMMITTER_DATE": "2026-11-08T12:34:56Z",
            }
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-q", "-m", "fixture"],
                check=True, env=environment,
            )
            rfc3339 = subprocess.run(
                ["python3", str(script), "--repo", str(repository), "--format", "rfc3339"],
                check=True, capture_output=True, text=True,
            )
            epoch = subprocess.run(
                ["python3", str(script), "--repo", str(repository), "--format", "epoch"],
                check=True, capture_output=True, text=True,
            )
        self.assertEqual(rfc3339.stdout.strip(), "2026-11-08T12:34:56Z")
        self.assertEqual(epoch.stdout.strip(), "1794141296")

    def run_tag_check(self, tags, tag="45.20261105.2-polaris-sdl", exit_code=0,
                      provide_skopeo=True):
        script = ROOT / "scripts/check-version-tag.py"
        self.assertTrue(script.exists(), "missing immutable version-tag guard")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            if provide_skopeo:
                fake = directory / "skopeo"
                fake.write_text(
                    "#!/bin/sh\n"
                    f"printf '%s\\n' '{json.dumps({'Repository': 'example/image', 'Tags': tags})}'\n"
                    f"exit {exit_code}\n"
                )
                fake.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(script), "ghcr.io/example/image", tag],
                capture_output=True, text=True,
                env=os.environ | {"PATH": str(directory)},
            )
        return result

    def test_version_tag_guard_accepts_unused_tag(self):
        result = self.run_tag_check(["latest", "45.20261105.1-polaris-sdl"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("available", result.stdout)

    def test_version_tag_guard_rejects_existing_tag(self):
        result = self.run_tag_check(["latest", "45.20261105.2-polaris-sdl"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stderr)

    def test_version_tag_guard_fails_closed_on_registry_error(self):
        result = self.run_tag_check([], exit_code=42)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unable to list registry tags", result.stderr)

    def test_version_tag_guard_fails_closed_when_skopeo_is_missing(self):
        result = self.run_tag_check([], provide_skopeo=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("skopeo is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
