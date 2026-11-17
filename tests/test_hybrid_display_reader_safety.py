"""Foundation regression checks use existing safety/classification unchanged.

These are structural regressions, not claimed new RED/GREEN production cycles.
No native exception or live adapter safety migration is introduced.
"""
import importlib.util
from pathlib import Path
import unittest
from tests.test_hybrid_display_safety import product_violations
ROOT = Path(__file__).resolve().parents[1]
PRODUCT = 'prototype/hybrid-display/src/hybrid_display/'
MODULES = ('host_reader', 'parse_session', 'parse_kscreen', 'parse_drm', 'reader_policy', 'reader_commands', 'linux_reader', 'adapter')

class FoundationSafetyTests(unittest.TestCase):

    def test_every_foundation_module_obeys_unchanged_pure_core_checker(self):
        for module in MODULES:
            path = PRODUCT + module + '.py'
            self.assertEqual(product_violations(path, (ROOT / path).read_text()), [])

    def test_native_implementation_and_neighbor_operations_still_rejected(self):
        path = PRODUCT + 'linux_reader.py'
        for source in ('import os', 'import dbus', 'import socket', 'open("private")', 'adapter.kill(1)', 'path = "/sys/class/drm/card0-DP-1/status"'):
            self.assertTrue(product_violations(path, source))
        pure = 'from typing import Protocol\nclass Transport(Protocol):\n    def open_readonly(self, source): ...\n'
        self.assertEqual(product_violations(path, pure), [])

    def test_planned_foundation_paths_are_h_and_unknown_neighbors_remain_g(self):
        spec = importlib.util.spec_from_file_location('reader_foundation_policy', ROOT / 'scripts/classify-container-changes.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        paths = [PRODUCT + module + '.py' for module in MODULES]
        paths += ['tests/test_hybrid_display_' + name + '.py' for name in ('reader', 'parse_session', 'parse_kscreen', 'parse_drm', 'reader_policy', 'reader_commands', 'linux_reader', 'adapter', 'reader_fixtures', 'reader_safety')]
        for path in paths:
            self.assertEqual(policy.path_class(path), 'H')
        for path in ('tests/hybrid_display_reader_fixtures.py', 'prototype/hybrid-display-other/linux_reader.py'):
            self.assertEqual(policy.path_class(path), 'G')
