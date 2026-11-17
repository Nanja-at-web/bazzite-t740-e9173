"""Pure reader value contracts; synthetic data only."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display import host_reader as h

class ReaderContracts(unittest.TestCase):

    def test_payload_is_hidden_and_atomic(self):
        result = h.ReadResult(b'private', ('source_denied', 'source_denied'))
        self.assertIsNone(result.payload)
        self.assertEqual(result.reasons, ('source_denied',))
        self.assertNotIn('private', repr(result))
        with self.assertRaises(FrozenInstanceError):
            result.payload = b'other'

    def test_result_codes_are_closed_and_types_exact(self):
        for factory in (h.ReadResult, h.ParseResult, h.AdapterResult):
            result = factory(None, ('private-value',))
            self.assertEqual(result.reasons, ('input_invalid',))
        self.assertIsNone(h.ReadResult('private').payload)
        self.assertEqual(h.ReadResult('private').reasons, ('input_invalid',))

    def test_metaclass_and_container_callbacks_never_run(self):
        calls = []

        class Meta(type):

            def __eq__(self, other):
                calls.append('type-eq')
                return True

        class Trap(tuple, metaclass=Meta):

            def __iter__(self):
                calls.append('iter')
                return super().__iter__()

            def __len__(self):
                calls.append('len')
                return 1

            def __repr__(self):
                calls.append('repr')
                return 'private'
        result = h.ReadResult(b'private', Trap(('source_denied',)))
        self.assertIsNone(result.payload)
        self.assertEqual(result.reasons, ('input_invalid',))
        self.assertEqual(calls, [])

    def test_parse_values_are_detached_immutable_and_hidden(self):
        original = {'items': [1, 2]}
        result = h.ParseResult(original)
        self.assertIsNone(result.value)
        self.assertEqual(result.reasons, ('input_invalid',))
        self.assertNotIn('items', repr(result))

    def test_total_node_budget_rejects_shared_tuple_graph(self):
        value = (1,)
        for _ in range(5):
            value = (value,) * 8
        result = h.ParseResult(value)
        self.assertTrue(result.value is None)
        self.assertEqual(result.reasons, ('input_invalid',))

    def test_malformed_exact_dto_returns_fixed_reason(self):
        malformed = object.__new__(h.SessionRaw)
        try:
            result = h.ParseResult(malformed)
        except Exception:
            self.fail('Malformed exact DTO must return a fixed reason')
        self.assertEqual(result.reasons, ('input_invalid',))
        self.assertIsNone(result.value)

    def test_adapter_snapshot_is_validated_and_detached(self):
        from hybrid_display.model import SessionSnapshot
        source = SessionSnapshot('wayland', 'KDE', True, True, (), (), False, False, frozenset())
        result = h.AdapterResult(source)
        self.assertTrue(result.ok, result.reasons)
        self.assertIsNot(result.snapshot, source)
        invalid = h.AdapterResult(SessionSnapshot())
        self.assertEqual(invalid.reasons, ('input_invalid',))
        self.assertIsNone(invalid.snapshot)
