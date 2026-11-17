from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from tests.test_hybrid_display_reader_fixtures import frame, koutput
from hybrid_display.host_reader import KScreenProfile
from hybrid_display.parse_kscreen import parse_kscreen

class KScreenTests(unittest.TestCase):

    def test_clone_and_replication_mark_both_endpoints(self):
        for relation in ({'clones': [2]}, {'replicationSource': 2}):
            result = self.parse(frame([koutput(1, **relation), koutput(2)]))
            self.assertTrue(result.ok, result.reasons)
            self.assertEqual(tuple(item.mirrored for item in result.value.outputs), (True, True))

    def parse(self, payload):
        return parse_kscreen(payload, KScreenProfile.SYNTHETIC_V1)

    def test_only_explicit_synthetic_profile_has_success(self):
        self.assertTrue(self.parse(frame()).ok)
        for profile in (KScreenProfile.UNKNOWN, True, '6.3.5'):
            self.assertEqual(parse_kscreen(frame(), profile).reasons, ('kscreen_profile_unverified',))

    def test_missing_enabled_numbers_modes_and_rotation_block(self):
        missing = koutput()
        del missing['enabled']
        bad = [missing] + [koutput(**change) for change in ({'scale': True}, {'scale': float('nan')}, {'scale': float('inf')}, {'scale': 0.1}, {'rotation': 3}, {'pos': {'x': True, 'y': 0}}, {'modes': koutput()['modes'] * 129}, {'currentModeId': 'absent'}, {'connected': False})]
        for output in bad:
            result = self.parse(frame([output]))
            self.assertEqual(result.reasons, ('kscreen_schema_invalid',))
            self.assertIsNone(result.value)

    def test_size_depth_duplicate_keys_and_scalar_limits(self):
        for payload in (b' ' * 65537, frame([koutput(i + 1) for i in range(17)]), b'{"outputs":[],"outputs":[]}', b'{"x":' + b'[' * 9 + b'0' + b']' * 9 + b'}', frame([koutput(name='a' * 129)])):
            result = self.parse(payload)
            self.assertEqual(result.reasons, ('kscreen_schema_invalid',))
            self.assertIsNone(result.value)

    def test_geometry_clone_replication_and_overlap(self):
        result = self.parse(frame([koutput(1), koutput(2)]))
        self.assertTrue(result.ok, result.reasons)
        self.assertFalse(any((o.mirrored for o in result.value.outputs)))
        for second in (koutput(2, pos={'x': 0, 'y': 0}), koutput(2, clones=[1]), koutput(2, replicationSource=1)):
            result = self.parse(frame([koutput(1), second]))
            self.assertTrue(result.ok, result.reasons)
            self.assertTrue(any((o.mirrored for o in result.value.outputs)))

    def test_structural_limits_reject_before_container_decode(self):
        from unittest.mock import patch
        import json
        import hybrid_display.parse_kscreen as parser
        payloads = (frame([koutput(number + 1) for number in range(17)]), frame([koutput(modes=koutput()['modes'] * 129)]), frame([koutput(clones=list(range(1, 18)))]), json.dumps({'outputs': [], **{str(index): 0 for index in range(65)}}).encode(), frame([koutput(name='a' * 129)]))
        for payload in payloads:
            with patch.object(parser.json, 'loads', wraps=json.loads) as decode:
                result = self.parse(payload)
            self.assertEqual(result.reasons, ('kscreen_schema_invalid',))
            self.assertEqual(decode.call_count, 0)
