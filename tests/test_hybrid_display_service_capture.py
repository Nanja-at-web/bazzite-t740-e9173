"""Explicitly synthetic IPC records. No real KScreen profile is supported."""
import sys
import unittest
sys.path.insert(0, 'prototype/hybrid-display/src')
from hybrid_display import reader_service_protocol as p
from hybrid_display import reader_service_policy as q
from hybrid_display import reader_service_capture as c


def peer():
    return q.PeerFacts(1000, 1000, 23, 99, 'fixture', 1000,
                       'wayland', 'KDE', False, True, 'user', 'active', True)


def record(kind, bus, subject, payload):
    return bytes((kind, bus)) + subject.to_bytes(4, 'big') + len(payload).to_bytes(4, 'big') + payload


def synthetic_body(config=b'{"outputs":[]}', extras=()):
    boot = b''.join((record(1, 0, 0, b'\x01'), record(2, 0, 0, b':1.1'),
                     record(1, 1, 0, b'\x01'), record(2, 1, 0, b':1.2')))
    path = b'/org/freedesktop/login1/session/fixture'
    userpath = b'/org/freedesktop/login1/user/_1000'
    props = (b'fixture', (1000).to_bytes(4, 'big') + len(userpath).to_bytes(2, 'big') + userpath,
             b'wayland', b'KDE', b'\x00', b'\x01', b'user', b'active')
    records = [record(3, 0, 0, b':1.3'), record(4, 0, 0, b'\x00' * 4),
               record(5, 0, 0, (10).to_bytes(4, 'big')), record(6, 0, 0, path)]
    records.extend(record(7, 0, i, value) for i, value in enumerate(props))
    for subject in (1, 2):
        records.extend((record(3, 1, subject, b':1.' + str(subject + 3).encode('ascii')),
                        record(4, 1, subject, (1000).to_bytes(4, 'big')),
                        record(5, 1, subject, (30 + subject).to_bytes(4, 'big')),
                        record(6, 0, subject, path)))
    records.append(record(8, 1, 0, config))
    records.extend(extras)
    capture = len(records).to_bytes(2, 'big') + b''.join(records)
    return b'\x04' + boot + b'\x02' + capture + capture

class CaptureTests(unittest.TestCase):
    def test_capture_rejects_oversize_foreign_types_and_malformed_metadata(self):
        calls = []
        class Meta(type):
            def __eq__(self, other):
                calls.append('meta')
                raise AssertionError
        class Blob(bytes, metaclass=Meta):
            def __len__(self):
                calls.append('len')
                raise AssertionError
        for body in (Blob(b'private'), bytearray(synthetic_body()), b'x' * p.MAX_RESPONSE):
            result = c.decode_capture(body, p.Request(), peer())
            self.assertFalse(result.ok)
            self.assertIsNone(result.value)
            self.assertNotIn('private', repr(result))
        self.assertEqual(calls, [])
        for identity in (None, object.__new__(q.PeerFacts)):
            self.assertFalse(c.decode_capture(synthetic_body(), p.Request(), identity).ok)

    def test_edid_and_output_records_are_bound_and_limited(self):
        import json
        from tests.test_hybrid_display_reader_fixtures import koutput, edid
        config = json.dumps({'outputs': [koutput()]}, separators=(',', ':')).encode()
        valid = synthetic_body(config, (record(9, 1, 1, edid()),))
        result = c.decode_capture(valid, p.Request(), peer())
        self.assertTrue(result.ok, result.reason)
        self.assertNotIn('DP-1', repr(result))
        for subject, payload in ((2, edid()), (1, b'x' * 128), (1, edid() * 33)):
            result = c.decode_capture(synthetic_body(config, (record(9, 1, subject, payload),)), p.Request(), peer())
            self.assertFalse(result.ok)
            self.assertIsNone(result.value)

    def test_synthetic_complete_two_capture_roundtrip(self):
        for body in (synthetic_body(), synthetic_body().replace(b':1.3', b':1.4')):
            with self.subTest(cross_bus_collision=body != synthetic_body()):
                decoded = c.decode_capture(body, p.Request(), peer())
                self.assertTrue(decoded.ok, decoded.reason)
                self.assertEqual(c.encode_capture(decoded.value, p.Request(), peer()).value, body)
                self.assertNotIn('fixture', repr(decoded))

    def test_projection_unknown_duplicate_nonfinite_or_noncanonical_blocks(self):
        for config in (b'{"outputs":[],"unknown":1}', b'{"outputs":[],"outputs":[]}',
                       b'{"outputs":[NaN]}', b'{"outputs":[Infinity]}',
                       b'{"outputs": []}', b'\xff', b'{"outputs":[' + b'[' * 9 + b'0' + b']' * 9 + b']}'):
            result = c.decode_capture(synthetic_body(config), p.Request(), peer())
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'kscreen_schema_invalid')
            self.assertIsNone(result.value)
        import json
        from tests.test_hybrid_display_reader_fixtures import koutput, edid
        for changes in ({'pos': {'unknown': 123}}, {'size': {'unknown': 456}},
                        {'currentModeId': {'unknown': 789}}, {'currentModeId': 'absent'},
                        {'pos': {'x': True, 'y': 0}}, {'size': {'width': 0, 'height': 1}}):
            with self.subTest(field=next(iter(changes))):
                output = koutput(enabled=False, **changes)
                config = json.dumps({'outputs': [output]}, separators=(',', ':')).encode()
                result = c.decode_capture(synthetic_body(config, (record(9, 1, 1, edid()),)),
                                          p.Request(), peer())
                self.assertEqual(result.reason, 'kscreen_schema_invalid')
                self.assertIsNone(result.value)

    def test_record_order_counts_subject_bus_and_mirror_are_enforced(self):
        body = synthetic_body()
        for index in (0, 1, 2, 3, 4, 5):
            bad = bytearray(body)
            bad[index] ^= 1
            self.assertFalse(c.decode_capture(bytes(bad), p.Request(), peer()).ok)
        self.assertFalse(c.decode_capture(body[:-1], p.Request(), peer()).ok)
        self.assertFalse(c.decode_capture(body + b'x', p.Request(), peer()).ok)
        bad = body.replace(b':1.3', b':1.9', 1)
        self.assertEqual(c.decode_capture(bad, p.Request(), peer()).reason, 'inventory_changed')

    def test_profile_gate_is_not_a_wire_parameter(self):
        body = synthetic_body()
        frame = p.header(p.MessageType.IPC_CAPTURE_OK, len(body)) + body
        self.assertEqual(p.decode_frame(frame, True).reason, 'kscreen_profile_unverified')
