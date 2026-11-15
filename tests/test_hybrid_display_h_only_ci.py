"""Regression contract for an isolated H-only change using real Git objects."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HOnlyCIContractTests(unittest.TestCase):
    def test_h_only_change_runs_tests_without_container_release_or_iso(self):
        spec = importlib.util.spec_from_file_location(
            'h_only_policy', ROOT / 'scripts/classify-container-changes.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        changed_path = 'tests/test_hybrid_display_h_only_ci.py'

        self.assertEqual(policy.path_class('prototype/hybrid-display/README.md'), 'H')
        self.assertEqual(policy.path_class(changed_path), 'H')
        self.assertEqual(policy.path_class('experimental/unclassified-feature.txt'), 'G')

        with tempfile.TemporaryDirectory(prefix='hybrid-display-h-only-') as directory:
            repo = Path(directory) / 'repository'
            repo.mkdir()

            def git(*args):
                return subprocess.run(
                    ['git', '-C', str(repo),
                     '-c', 'user.name=H-only Policy Test',
                     '-c', 'user.email=test@example.invalid', *args],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()

            git('init', '-q', '--initial-branch=fixture')
            (repo / 'README.md').write_text('Temporary baseline.\n')
            git('add', '--', 'README.md')
            git('commit', '-qm', 'baseline')
            base = git('rev-parse', 'HEAD')

            target = repo / changed_path
            target.parent.mkdir()
            target.write_text('# Isolated H-only fixture.\n')
            git('add', '--', changed_path)
            git('commit', '-qm', 'add isolated display test')
            head = git('rev-parse', 'HEAD')

            self.assertRegex(base, r'^[0-9a-f]{40}$')
            self.assertRegex(head, r'^[0-9a-f]{40}$')
            self.assertNotEqual(base, head)
            self.assertEqual(git('rev-list', '--count', base + '..' + head), '1')
            self.assertEqual(git('diff', '--name-status', base, head), 'A\t' + changed_path)

            for event, ref in (
                ('workflow_dispatch', 'refs/heads/fixture'),
                ('pull_request', 'refs/pull/1/merge'),
                ('push', 'refs/heads/fixture'),
            ):
                with self.subTest(event=event):
                    result = policy.classify(repo, event, base, head, ref)
                    self.assertIs(result['blocking'], False)
                    self.assertEqual(result['classes'], ['H'])
                    self.assertIs(result['run_tests'], True)
                    for key in ('build_container', 'release_candidate', 'run_iso'):
                        self.assertIs(result[key], False, key)
                    self.assertEqual(result['unknown'], [])
                    self.assertEqual(result['paths'], {'H': [changed_path]})
                    self.assertRegex(result['summary'].casefold(), r'tests[ -]only')
                    self.assertRegex(result['summary'].casefold(), r'container\b.*\bskipped')
