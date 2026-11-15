"""Policy behavior against real Git objects; no registry or container access."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/classify-container-changes.py'


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT.exists():
            raise AssertionError('Classifier missing: scripts/classify-container-changes.py')
        spec = importlib.util.spec_from_file_location('policy', SCRIPT)
        cls.policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.policy)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Policy Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.write('README.md', 'baseline')
        self.write('image-lock.json', (ROOT / 'image-lock.json').read_text())
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True)

    def write(self, path, value):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'change')
        return self.git('rev-parse', 'HEAD').strip()

    def decision(self, event='push', ref='refs/heads/main', head=None, base=None):
        return self.policy.classify(self.repo, event, self.base if base is None else base,
                                    head or self.commit(), ref)

    def test_paths_have_explicit_classes(self):
        cases = {
            'Containerfile': 'A', 'build_files/new file': 'A', 'system_files/a': 'A',
            'installer/build-metadata.py': 'A', 'build-version.json': 'A',
            'scripts/build-version.py': 'A', 'scripts/build-created.py': 'A',
            'Justfile': 'A', 'image-template.env': 'A',
            '.github/workflows/build.yml': 'B', 'scripts/classify-container-changes.py': 'B',
            'scripts/check-version-tag.py': 'B', 'cosign.pub': 'B', 'tests/test_container_workflow_policy.py': 'D',
            'tests/test_build_provenance.py': 'D', 'README.md': 'E', 'docs/a': 'E',
            'AGENTS.md': 'E', '.agents/a': 'E', 'prototype/hybrid-focus/a': 'F',
            'tests/test_hybrid_focus_model.py': 'F', '.github/workflows/build-disk.yml': 'C',
            'disk_config/a': 'C', 'installer/other': 'C', 'unknown file': 'G',
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(self.policy.path_class(path), expected)

    def test_event_and_class_decisions(self):
        for path, build, release in [('Containerfile', True, True),
                                     ('.github/workflows/build.yml', True, False),
                                     ('README.md', False, False),
                                     ('AGENTS.md', False, False),
                                     ('installer/a', False, False),
                                     ('tests/test_build_provenance.py', False, False),
                                     ('prototype/hybrid-focus/a', False, False)]:
            self.write(path, 'changed')
            head = self.commit()
            for event, ref in [('push', 'refs/heads/main'), ('pull_request', 'refs/pull/1/merge'),
                               ('workflow_dispatch', 'refs/heads/main'),
                               ('workflow_dispatch', 'refs/heads/fix')]:
                with self.subTest(path=path, event=event, ref=ref):
                    result = self.policy.classify(self.repo, event, self.base, head, ref)
                    self.assertFalse(result['blocking'])
                    self.assertEqual(result['release_candidate'], release and event == 'push')
                    self.assertEqual(result['build_container'], build or event == 'workflow_dispatch')
                    self.assertTrue(result['run_tests'])
                    self.assertFalse(result['run_iso'])
            self.base = head

    def test_unknown_and_mixed_paths_block(self):
        self.write('Containerfile', 'build')
        self.write('new unknown', 'unknown')
        result = self.decision()
        self.assertTrue(result['blocking'])
        self.assertIn('new unknown', result['paths']['G'])
        self.assertFalse(result['release_candidate'])
        self.assertFalse(result['build_container'])

    def test_lock_field_classification(self):
        original = json.loads((self.repo / 'image-lock.json').read_text())
        for section, field, value, classes in [
            ('container_base', 'image', 'ghcr.io/example/base@sha256:' + 'a' * 64, ['A']),
            ('container_base', 'version', '45.20261106', ['A']),
            ('installer_base', 'version', '45.20261106', ['C']),
            ('install_payload', 'version', '45.20261105.3-polaris-sdl', ['C']),
            (None, 'resolved_at', '2026-11-14T12:00:00Z', ['D']),
        ]:
            changed = copy.deepcopy(original)
            (changed[section] if section else changed)[field] = value
            self.write('image-lock.json', json.dumps(changed))
            head = self.commit()
            result = self.policy.classify(self.repo, 'push', self.base, head, 'refs/heads/main')
            self.assertEqual(result['classes'], classes)
            self.assertFalse(result['blocking'])
            self.assertEqual(result['release_candidate'], classes == ['A'])
            self.write('image-lock.json', json.dumps(original))
            self.base = self.commit()

    def test_mixed_lock_a_and_c(self):
        lock = json.loads((self.repo / 'image-lock.json').read_text())
        lock['container_base']['version'] = '45.20261106'
        lock['installer_base']['version'] = '45.20261106'
        self.write('image-lock.json', json.dumps(lock))
        result = self.decision()
        self.assertEqual(result['classes'], ['A', 'C'])
        self.assertTrue(result['release_candidate'])

    def test_lock_unknown_invalid_schema_and_deletion_block(self):
        original = json.loads((self.repo / 'image-lock.json').read_text())
        for value in [dict(original, surprise=True), dict(original, schema_version=3),
                      dict(original, platform='linux/arm64'),
                      dict(original, container_base=dict(original['container_base'], surprise=1))]:
            self.write('image-lock.json', json.dumps(value))
            head = self.commit()
            self.assertTrue(self.policy.classify(self.repo, 'push', self.base, head,
                                                'refs/heads/main')['blocking'])
        self.write('image-lock.json', '{invalid')
        self.assertTrue(self.decision()['blocking'])
        (self.repo / 'image-lock.json').unlink()
        self.assertTrue(self.decision()['blocking'])

    def test_rename_checks_old_and_new_paths(self):
        self.git('mv', 'README.md', 'new unknown')
        result = self.decision()
        self.assertEqual(result['classes'], ['E', 'G'])
        self.assertTrue(result['blocking'])

    def test_deleted_container_input_is_relevant(self):
        self.write('system_files/example', 'content')
        self.base = self.commit()
        (self.repo / 'system_files/example').unlink()
        self.assertTrue(self.decision()['release_candidate'])

    def test_multiple_commits_are_all_considered(self):
        self.write('Containerfile', 'first')
        self.commit()
        self.write('README.md', 'second')
        result = self.decision()
        self.assertEqual(result['classes'], ['A', 'E'])
        self.assertTrue(result['release_candidate'])

    def test_missing_objects_empty_and_unsupported_event_block(self):
        for base, head, event in [('0' * 40, self.base, 'push'),
                                  (self.base, 'f' * 40, 'push'),
                                  (self.base, self.base, 'push'),
                                  (self.base, self.base, 'schedule')]:
            self.assertTrue(self.policy.classify(self.repo, event, base, head,
                                                'refs/heads/main')['blocking'])

    def test_non_main_push_does_not_release(self):
        self.write('Containerfile', 'content')
        self.assertFalse(self.decision(ref='refs/heads/other')['release_candidate'])

    def test_nul_parser_rejects_incomplete_or_invalid_records(self):
        self.assertEqual(self.policy.parse_diff(b'A\0build_files/a b\0'),
                         [('A', ['build_files/a b'])])
        self.assertEqual(self.policy.parse_diff(b'R100\0README.md\0docs/a\0'),
                         [('R100', ['README.md', 'docs/a'])])
        for raw in [b'A\0missing', b'A\0', b'R100\0old\0', b'X\0file\0', b'']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.policy.parse_diff(raw)

    def test_diverged_base_is_not_accepted(self):
        self.write('README.md', 'one branch')
        branch_head = self.commit()
        self.git('checkout', '--detach', self.base)
        self.write('README.md', 'other branch')
        other_head = self.commit()
        self.assertTrue(self.policy.classify(self.repo, 'push', branch_head, other_head,
                                            'refs/heads/main')['blocking'])

    def test_cli_unknown_exit_is_blocking_and_outputs_are_safe(self):
        self.write('unclassified', 'content')
        head = self.commit()
        result = subprocess.run(['python3', '-B', str(SCRIPT), '--repo', str(self.repo),
                                 '--event', 'push', '--ref', 'refs/heads/main',
                                 '--base', self.base, '--head', head], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(json.loads(result.stdout)['blocking'])

    def test_cli_json_and_explicit_github_output(self):
        self.write('Containerfile', 'content')
        head = self.commit()
        output = self.repo / 'outputs'
        run = subprocess.run(['python3', '-B', str(SCRIPT), '--repo', str(self.repo),
                              '--event', 'push', '--ref', 'refs/heads/main',
                              '--base', self.base, '--head', head,
                              '--github-output', str(output)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)['release_candidate'])
        self.assertIn('release_candidate=true\n', output.read_text())


if __name__ == '__main__':
    unittest.main()
