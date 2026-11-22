"""In-memory framing boundary tests; bytes are supplied directly as events."""
import sys
import unittest
sys.path.insert(0, 'prototype/hybrid-display/src')
from hybrid_display import reader_service_protocol as p
from hybrid_display import reader_service_policy as q
from hybrid_display import reader_service_stream as s

class Clock:
    value = 0
    def now(self):
        return self.value

class StreamTests(unittest.TestCase):
    def decoder(self, response=False):
        clock = Clock()
        budget = q.Budget(clock, 5 if response else 4)
        self.assertTrue(budget.check().ok)
        return s.Decoder(budget, response), clock

    def test_fragmented_header_and_body_commit_only_at_eof(self):
        frame = p.encode_request(p.Request((3,))).value
        for split in range(len(frame) + 1):
            decoder, clock = self.decoder()
            self.assertTrue(decoder.feed(frame[:split]).ok)
            self.assertTrue(decoder.feed(frame[split:]).ok)
            result = decoder.finish()
            self.assertTrue(result.ok)
            self.assertEqual(result.value.client_pids, (3,))
            self.assertFalse(decoder.finish().ok)
            self.assertFalse(decoder.feed(b'').ok)

    def test_oversize_header_rejected_before_body(self):
        decoder, clock = self.decoder()
        header = p.header(p.MessageType.CAPTURE_IPC, p.MAX_REQUEST)
        result = decoder.feed(header)
        self.assertEqual(result.reason, 'ipc_limit')
        self.assertEqual(decoder.buffered_bytes, 0)

    def test_incomplete_eof_and_trailing_bytes_discard(self):
        frame = p.encode_request(p.Request((3,))).value
        for length in range(len(frame)):
            decoder, clock = self.decoder()
            self.assertTrue(decoder.feed(frame[:length]).ok)
            self.assertEqual(decoder.finish().reason, 'ipc_invalid')
        for parts in ((frame + b'x',), (frame, b'x'), (frame, frame)):
            decoder, clock = self.decoder()
            for part in parts:
                result = decoder.feed(part)
            self.assertEqual(result.reason, 'ipc_invalid')
            self.assertFalse(decoder.finish().ok)

    def test_header_deadline_is_absolute(self):
        decoder, clock = self.decoder()
        self.assertTrue(decoder.feed(b'H').ok)
        clock.value = .099
        self.assertTrue(decoder.feed(b'D').ok)
        clock.value = .1
        self.assertEqual(decoder.feed(b'R').reason, 'source_timeout')

    def test_eof_deadline_is_absolute(self):
        decoder, clock = self.decoder()
        self.assertTrue(decoder.feed(p.encode_request(p.Request()).value).ok)
        clock.value = .25
        self.assertEqual(decoder.finish().reason, 'source_timeout')

    def test_bad_types_and_large_chunk_do_not_allocate(self):
        for chunk in (None, bytearray(b'H'), memoryview(b'H'), b'x' * 4097):
            decoder, clock = self.decoder()
            self.assertFalse(decoder.feed(chunk).ok)
            self.assertEqual(decoder.buffered_bytes, 0)

    def test_response_requires_eof_before_client_deadline(self):
        decoder, clock = self.decoder(True)
        self.assertTrue(decoder.feed(p.encode_response(p.Response()).value).ok)
        clock.value = 5
        self.assertEqual(decoder.finish().reason, 'source_timeout')

    def test_header_processing_cannot_cross_stage_deadline(self):
        decoder, clock = self.decoder()
        values = iter((.099, .100))
        clock.now = lambda: next(values)
        result = decoder.feed(p.encode_request(p.Request()).value)
        self.assertEqual(result.reason, 'source_timeout')
