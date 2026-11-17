from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display.reader_commands import reject_command

class CommandBoundaryTests(unittest.TestCase):

    def test_all_commands_denied_without_spawn(self):
        calls = []
        for argv in ((), ('reader',), 'shell private', ('timeout', '1', 'reader'), None):
            result = reject_command(argv, lambda *args: calls.append('spawn'))
            self.assertEqual(result.reasons, ('command_not_allowed',))
            self.assertIsNone(result.payload)
        self.assertEqual(calls, [])

    def test_tuple_metaclass_never_visited(self):
        calls = []

        class Meta(type):

            def __eq__(self, other):
                calls.append('eq')
                return True

        class Trap(tuple, metaclass=Meta):

            def __iter__(self):
                calls.append('iter')
                raise RuntimeError

            def __len__(self):
                calls.append('len')
                raise RuntimeError
        result = reject_command(Trap(('private',)))
        self.assertEqual(result.reasons, ('command_not_allowed',))
        self.assertEqual(calls, [])
