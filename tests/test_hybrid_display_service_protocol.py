"""In-memory service protocol tests; no transport, runtime or host evidence."""
import sys
import unittest
sys.path.insert(0, 'prototype/hybrid-display/src')
from hybrid_display import reader_service_protocol as p

class ProtocolTests(unittest.TestCase):
    def test_canonical_request_and_roundtrip(self):
        encoded = p.encode_request(p.Request((7, 9)))
        self.assertTrue(encoded.ok)
        self.assertEqual(encoded.value, b'HDR1\x00\x01\x00\x01\x00\x00\x00\x09\x00\x00\x00\x01\x02\x00\x00\x00\x07\x00\x00\x00\x09')
        decoded = p.decode_frame(encoded.value)
        self.assertTrue(decoded.ok)
        self.assertEqual(decoded.value.client_pids, (7, 9))

    def test_request_rejects_invalid_and_mutable_inputs(self):
        for value in (None, (), p.Request([7]), p.Request((True,)),
                      p.Request((0,)), p.Request((2147483648,)),
                      p.Request((7, 7)), p.Request(tuple(range(1, 18)))):
            with self.subTest(kind=type(value).__name__):
                result = p.encode_request(value)
                self.assertFalse(result.ok)
                self.assertIsNone(result.value)
                self.assertEqual(result.reason, 'input_invalid')

    def test_blocked_wire_table_is_closed(self):
        for number, reason in enumerate(p.REASONS, 1):
            encoded = p.encode_response(p.Response(reason))
            self.assertTrue(encoded.ok)
            self.assertEqual(encoded.value[-2:], number.to_bytes(2, 'big'))
            decoded = p.decode_frame(encoded.value, response=True)
            self.assertTrue(decoded.ok)
            self.assertEqual(decoded.value.reason, reason)
        self.assertFalse(p.encode_response(p.Response('sensitive-value')).ok)

    def test_untrusted_callbacks_are_never_called(self):
        calls = []
        class Meta(type):
            def __eq__(self, other):
                calls.append('meta')
                raise AssertionError
        class Trap(tuple, metaclass=Meta):
            def __len__(self):
                calls.append('len')
                raise AssertionError
            def __iter__(self):
                calls.append('iter')
                raise AssertionError
        class Blob(bytes, metaclass=Meta):
            def __len__(self):
                calls.append('bytes')
                raise AssertionError
        for value in (Trap(), p.Request(Trap()), Blob(b'sensitive')):
            self.assertFalse(p.encode_request(value).ok)
            self.assertFalse(p.decode_frame(value).ok)
        self.assertEqual(calls, [])

    def test_constructor_never_retains_mutable_alias(self):
        original = [7]
        request = p.Request(original)
        original.append(8)
        self.assertIsNone(request.client_pids)
        self.assertIsNone(p.Response(original).reason)
        self.assertFalse(p.Result(original).ok)
        self.assertNotIn('7', repr(request))

    def test_unknown_duplicate_fields_and_non_binary_bodies_block(self):
        bodies = (b'{"pid":1}', b'{"pid":1,"pid":1}', b'{"unknown":0}',
                  b'NaN', b'Infinity', b'1.0', b'01', b'\xff', b'\x00extra',
                  b'\x02\x00\x00\x00\x07\x00\x00\x00\x07')
        for body in bodies:
            self.assertFalse(p.decode_frame(p.header(p.MessageType.CAPTURE_IPC, len(body)) + body).ok)

    def test_header_direction_version_id_and_length_are_exact(self):
        good = p.encode_request(p.Request()).value
        for index in (0, 4, 5, 6, 7, 12, 15):
            bad = bytearray(good)
            bad[index] ^= 1
            self.assertFalse(p.decode_frame(bytes(bad)).ok)
        self.assertFalse(p.decode_frame(good + b'x').ok)
        self.assertFalse(p.decode_frame(good[:-1]).ok)
        self.assertFalse(p.decode_frame(good, True).ok)
        self.assertFalse(p.decode_frame(good, 1).ok)

    def test_no_live_profile_or_arbitrary_success_payload(self):
        header = p.header(p.MessageType.IPC_CAPTURE_OK, 0)
        self.assertEqual(p.decode_frame(header, True).reason, 'kscreen_profile_unverified')
        self.assertFalse(p.encode_response(p.Request()).ok)
        self.assertFalse(p.Result(object.__new__(p.Request)).ok)
        self.assertFalse(p.Result(object.__new__(p.Response)).ok)

    def test_wire_error_unknown_code_is_fixed_and_private(self):
        frame = p.header(p.MessageType.BLOCKED, 2) + b'\xff\xff'
        result = p.decode_frame(frame, True)
        self.assertTrue(result.ok)
        self.assertEqual(result.value.reason, 'reader_failed')
        result = p.Result(p.Request((1234567,)), 'sensitive-session')
        self.assertEqual(result.reason, 'reader_failed')
        self.assertIsNone(result.value)
        self.assertNotIn('sensitive', repr(result))
        self.assertNotIn('1234567', repr(result))

    def test_exact_maximum_request_count_and_extreme_pids(self):
        request = p.Request((1, 2147483647) + tuple(range(2, 16)))
        frame = p.encode_request(request)
        self.assertTrue(frame.ok)
        self.assertEqual(len(frame.value), 81)
        self.assertEqual(p.decode_frame(frame.value).value.client_pids, request.client_pids)
