import importlib.util
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
        source = source.split("\n  publish:\n", 1)[1].split("\n  result:\n", 1)[0]
        guard = source.index("python3 scripts/check-version-tag.py")
        build = source.index("just build")
        push_loop = source.index("podman push")
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


class RegistryResponseTests(unittest.TestCase):
    def test_ambiguous_registry_responses_fail_closed(self):
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('guard', ROOT / 'scripts/check-version-tag.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        import contextlib
        import io
        for payload in ('invalid', '{}', '{"Tags":null}', '{"Tags":{}}', '{"Tags":[1]}'):
            with self.subTest(payload=payload):
                response = subprocess.CompletedProcess([], 0, stdout=payload, stderr='')
                with patch.object(guard.subprocess, 'run', return_value=response), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(guard.main('ghcr.io/example/image', 'version'), 2)


class WorkflowPolicyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/build.yml").read_text()

    def job(self, name):
        match = re.search(r"(?ms)^  " + re.escape(name) + r":\n(.*?)(?=^  [a-z_]+:\n|\Z)", self.source)
        self.assertIsNotNone(match, "Missing workflow job: " + name)
        return match.group(1)

    def test_jobs_separate_read_only_validation_from_publish(self):
        for name in ("classify", "tests", "container", "publish", "result"):
            self.job(name)
        for name in ("classify", "tests", "container"):
            job = self.job(name)
            self.assertNotIn("packages: write", job)
            self.assertNotIn("SIGNING_SECRET", job)
            self.assertNotIn("check-version-tag.py", job)
        publish = self.job("publish")
        for required in ("github.event_name == 'push'", "github.ref == 'refs/heads/main'",
                         "needs.classify.outputs.release_candidate == 'true'",
                         "needs.classify.outputs.blocking == 'false'",
                         "needs.tests.result == 'success'", "needs.container.result == 'success'"):
            self.assertIn(required, publish)
        self.assertIn("cancel-in-progress: false", publish)
        self.assertNotIn("pull_request_target", self.source)
        self.assertNotIn("paths-ignore", self.source)

    def test_release_guard_order_and_signature_digest(self):
        publish = self.job("publish")
        self.assertEqual(publish.count("python3 scripts/check-version-tag.py"), 2)
        self.assertLess(publish.index("python3 scripts/check-version-tag.py"), publish.index("just build"))
        self.assertNotIn("continue-on-error", publish)
        self.assertIn('cosign verify --key cosign.pub "$reference"', publish)
        self.assertLess(publish.index('cosign verify'), publish.index('skopeo copy'))
        self.assertIn('reference="${IMAGE_REGISTRY}/${IMAGE_NAME}@${digest}"', publish)

    def test_iso_workflow_has_only_manual_trigger(self):
        source = (ROOT / '.github/workflows/build-disk.yml').read_text()
        # Inspect the complete top-level event block, rather than comparing
        # product files or assuming a fixed historical workflow version.
        match = re.search(r'(?ms)^on:\n(.*?)(?=^[^ #\n]|\Z)', source)
        self.assertIsNotNone(match)
        triggers = re.findall(r'^  ([a-z_]+):', match.group(1), re.MULTILINE)
        self.assertEqual(triggers, ['workflow_dispatch'])
        self.assertNotRegex(self.source, r'(?i)\b(?:gh\s+workflow\s+run|workflow_dispatch\s*[,\"\x27])')
        self.assertNotIn('build-disk.yml', self.source)
        self.assertNotIn("run_iso == 'true'", self.source)

    def test_classifier_never_requests_an_iso(self):
        spec = importlib.util.spec_from_file_location('policy', ROOT / 'scripts/classify-container-changes.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        base = subprocess.check_output(['git', 'rev-parse', 'HEAD^'], cwd=ROOT, text=True).strip()
        for event in ('push', 'pull_request', 'workflow_dispatch', 'unsupported'):
            for comparison in (base, head, '0' * 40):
                with self.subTest(event=event, base=comparison):
                    result = policy.classify(ROOT, event, comparison, head, 'refs/heads/main')
                    self.assertIs(result['run_iso'], False)

    def test_only_pr_validations_can_cancel_older_runs(self):
        container = self.job('container')
        self.assertIn("github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number)", container)
        self.assertIn("|| format('run-{0}', github.run_id)", container)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", container)
        publish = self.job('publish')
        self.assertIn('group: container-publication-${{ github.repository }}', publish)
        self.assertIn('cancel-in-progress: false', publish)

    def release_script(self):
        job = self.job("publish")
        match = re.search(r"(?ms)      - name: Publish version, sign, verify, then promote\n.*?        run: \|\n(.*?)(?=^      - name:|\Z)", job)
        self.assertIsNotNone(match)
        return "\n".join(line[10:] for line in match.group(1).splitlines())

    def run_release(self, failure="", registry_failure=0):
        # Execute the actual workflow shell with external commands replaced by
        # strict local fakes. No registry requests or image builds are made.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "calls"
            fake = root / "tool"
            fake.write_text("#!" + sys.executable + "\n" + r"""import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as f:
 f.write(json.dumps([name] + args) + '\n')
fail = os.environ.get('FAIL', '')
if name == 'python3':
 if args == ['scripts/build-version.py']:
  print('45.20261105.3-polaris-sdl')
 elif args[0] == 'scripts/check-version-tag.py':
  sys.exit(int(os.environ.get('REGISTRY_FAILURE', '0')))
 else:
  sys.exit(90)
elif name == 'just':
 if args != ['generate-build-tags', 'image', 'latest']: sys.exit(96)
 print('latest latest-date 45.20261105.3-polaris-sdl')
elif name == 'podman':
 if args[0] != 'push': sys.exit(91)
 digestarg = next(a for a in args if a.startswith('--digestfile='))
 pathlib.Path(digestarg.split('=', 1)[1]).write_text('sha256:' + 'a' * 64)
elif name == 'cosign':
 if args[0] == 'import-key-pair':
  pathlib.Path('import-cosign.key').write_text('test-key')
 elif args[0] in ('sign', 'verify'):
  if not args[-1].endswith('@sha256:' + 'a' * 64): sys.exit(92)
  if fail == args[0]: sys.exit(33)
 else: sys.exit(93)
elif name == 'skopeo':
 if args[0] != 'copy' or '@sha256:' not in args[-2]: sys.exit(94)
else: sys.exit(95)
""")
            fake.chmod(0o755)
            for name in ('python3', 'podman', 'cosign', 'skopeo', 'just'):
                (root / name).symlink_to(fake)
            env = os.environ | dict(PATH=str(root) + os.pathsep + os.environ['PATH'],
                CALLS=str(log), FAIL=failure, REGISTRY_FAILURE=str(registry_failure),
                IMAGE_REGISTRY='ghcr.io/example', IMAGE_NAME='image', DEFAULT_TAG='latest',
                COSIGN_PRIVATE_KEY='synthetic-test-key', GITHUB_OUTPUT=str(root / 'output'))
            run = subprocess.run(['bash', '-c', self.release_script()], cwd=root,
                                 env=env, capture_output=True, text=True, timeout=15)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return run, calls

    def test_sign_or_verify_failure_never_promotes_aliases(self):
        for failure in ('sign', 'verify'):
            run, calls = self.run_release(failure)
            self.assertNotEqual(run.returncode, 0, run.stderr)
            self.assertEqual(sum(call[0] == 'podman' for call in calls), 1)
            self.assertFalse(any(call[0] == 'skopeo' for call in calls))
            self.assertFalse(any('delete' in call or 'remove' in call for call in calls))

    def test_success_verifies_pushed_digest_before_alias_copy(self):
        run, calls = self.run_release()
        self.assertEqual(run.returncode, 0, run.stderr)
        verify = next(i for i, call in enumerate(calls) if call[:2] == ['cosign', 'verify'])
        aliases = [i for i, call in enumerate(calls) if call[0] == 'skopeo']
        self.assertTrue(aliases)
        self.assertTrue(all(i > verify for i in aliases))
        self.assertEqual(sum(call[0] == 'podman' for call in calls), 1)

    def test_second_registry_guard_failure_never_pushes(self):
        for code in (1, 2):
            run, calls = self.run_release(registry_failure=code)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse(any(call[0] in ('podman', 'skopeo') for call in calls))


    def test_result_rejects_required_failures_and_accepts_intentional_skip(self):
        result_job = self.job('result')
        self.assertIn('if: always()', result_job)
        script = result_job.split('        run: |\n', 1)[1]
        script = '\n'.join(line[10:] for line in script.splitlines())
        good = dict(CLASSIFY='success', BLOCKING='false', TESTS='success', BUILD='false',
                    CONTAINER='skipped', RELEASE='false', PUBLISH='skipped')
        cases = [(good, 0), (good | dict(BLOCKING='true'), 1),
                 (good | dict(TESTS='failure'), 1),
                 (good | dict(BUILD='true', CONTAINER='skipped'), 1),
                 (good | dict(BUILD='true', CONTAINER='success'), 0),
                 (good | dict(RELEASE='true', PUBLISH='failure'), 1),
                 (good | dict(BUILD='true', CONTAINER='success', RELEASE='true', PUBLISH='success'), 0)]
        for values, expected in cases:
            with self.subTest(values=values):
                run = subprocess.run(['bash', '-c', script], env=os.environ | values,
                                     capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, expected, run.stderr)


if __name__ == "__main__":
    unittest.main()
