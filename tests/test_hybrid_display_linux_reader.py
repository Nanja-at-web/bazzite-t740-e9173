"""All transport activity is in memory; no files, IPC, children, or signals."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display.host_reader import FileSource, SourceKey, BusQuery, QueryKey
from hybrid_display.linux_reader import LinuxReader, DeadlineProfile, FrameHeader
from hybrid_display.reader_policy import QueryContext, Resolution
from tests.test_hybrid_display_reader_policy import resolution

class FakeClock:

    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

class FakeTransport:

    def __init__(self, body=b'connected\n'):
        self.body = body
        self.calls = []
        self.metadata = resolution()
        self.after = self.metadata
        self.stats = 0
        self.headers = [FrameHeader(len(body))]
        self.clock = None
        self.fail = False

    def open_readonly(self, source):
        self.calls.append(('open_readonly', source.key))
        return object()

    def stat_handle(self, handle):
        self.stats += 1
        return self.metadata if self.stats == 1 else self.after

    def read_chunk(self, handle, size):
        self.calls.append(('read_chunk', size))
        if self.fail:
            raise RuntimeError('private')
        if self.clock is not None:
            self.clock.value = 1.0
        body, self.body = (self.body[:size], self.body[size:])
        return body

    def close_handle(self, handle):
        self.calls.append(('close_handle',))

    def begin_query(self, query):
        self.calls.append(('begin_query',))
        return object()

    def next_header(self, handle):
        self.calls.append(('header',))
        return self.headers.pop(0)

    def read_body(self, handle, size):
        self.calls.append(('body', size))
        return self.body[:size]

class TransportTests(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.source = FileSource(SourceKey.DRM_STATUS, 0, 'DP-1')

    def reader(self, transport):
        return LinuxReader(transport, self.clock, DeadlineProfile.SYNTHETIC_ONLY, QueryContext(1000, 10))

    def test_deadline_gate_before_read_and_limit_plus_one(self):
        transport = FakeTransport()
        result = LinuxReader(transport, self.clock).read_file(self.source)
        self.assertEqual(result.reasons, ('reader_deadline_unverified',))
        self.assertEqual(transport.calls, [])
        transport = FakeTransport(b'x' * 17)
        result = self.reader(transport).read_file(self.source)
        self.assertEqual(result.reasons, ('source_limit',))
        self.assertEqual([call for call in transport.calls if call[0] == 'read_chunk'], [('read_chunk', 17)])
        self.assertEqual(transport.calls[-1], ('close_handle',))

    def test_zero_size_hint_does_not_truncate_and_inode_replacement_blocks(self):
        transport = FakeTransport()
        self.assertEqual(self.reader(transport).read_file(self.source).payload, b'connected\n')
        transport = FakeTransport()
        transport.after = replace(transport.metadata, inode=3)
        result = self.reader(transport).read_file(self.source)
        self.assertEqual(result.reasons, ('inventory_changed',))
        self.assertIsNone(result.payload)

    def test_timeout_and_error_close_without_retry(self):
        for failure in ('timeout', 'exception'):
            transport = FakeTransport()
            if failure == 'timeout':
                transport.clock = self.clock
            else:
                transport.fail = True
            result = self.reader(transport).read_file(self.source)
            expected = 'source_timeout' if failure == 'timeout' else 'reader_failed'
            self.assertEqual(result.reasons, (expected,))
            self.assertEqual(sum((call[0] == 'open_readonly' for call in transport.calls)), 1)
            self.assertEqual(sum((call[0] == 'close_handle' for call in transport.calls)), 1)
            self.assertNotIn('private', repr(result))
            self.clock.value = 0.0

    def test_header_size_fds_serial_and_unexpected_budget_before_body(self):
        query = BusQuery(QueryKey.AUTH)
        for header, reason in ((FrameHeader(65537), 'ipc_limit'), (FrameHeader(1, fd_count=1), 'ipc_invalid'), (FrameHeader(1, reply_serial=2), 'ipc_invalid')):
            transport = FakeTransport(b'x')
            transport.headers = [header]
            result = self.reader(transport).query(query)
            self.assertEqual(result.reasons, (reason,))
            self.assertFalse(any((call[0] == 'body' for call in transport.calls)))
            self.assertEqual(transport.calls[-1], ('close_handle',))
        transport = FakeTransport()
        transport.headers = [FrameHeader(0, unexpected=True)] * 33
        result = self.reader(transport).query(query)
        self.assertEqual(result.reasons, ('ipc_limit',))
        self.assertEqual(sum((call[0] == 'header' for call in transport.calls)), 33)

    def test_late_open_still_closes_the_returned_handle(self):
        transport = FakeTransport()
        original = transport.open_readonly

        def late(source):
            handle = original(source)
            self.clock.value = 1.0
            return handle
        transport.open_readonly = late
        result = self.reader(transport).read_file(self.source)
        self.assertEqual(result.reasons, ('source_timeout',))
        self.assertEqual(sum((call[0] == 'close_handle' for call in transport.calls)), 1)

    def test_foreign_process_uid_blocks_before_body(self):
        from hybrid_display.reader_policy import Resolution
        source = FileSource(SourceKey.PROCESS_STAT, pid=10)
        transport = FakeTransport(b'private')
        transport.metadata = Resolution('procfs', 'regular', 1, 2, True, False, ('10', 'stat'), (), 1001, 50)
        transport.after = transport.metadata
        reader = LinuxReader(transport, self.clock, DeadlineProfile.SYNTHETIC_ONLY, QueryContext(1000, 10), (10,))
        result = reader.read_file(source)
        self.assertEqual(result.reasons, ('process_identity_unverified',))
        self.assertFalse(any((call[0] == 'read_chunk' for call in transport.calls)))

    def test_device_payload_cannot_disagree_with_verified_gpu(self):
        metadata = resolution()
        metadata = replace(metadata, kind='directory', components=metadata.links[1][-1], links=metadata.links[:2])
        transport = FakeTransport(b'0000:02:00.0')
        transport.metadata = metadata
        transport.after = metadata
        source = FileSource(SourceKey.DRM_DEVICE_LINK, 0)
        result = self.reader(transport).read_file(source)
        self.assertEqual(result.reasons, ('drm_device_invalid',))
        self.assertIsNone(result.payload)

    def test_hello_requires_prior_synthetic_authentication(self):
        transport = FakeTransport(b':1.9')
        result = self.reader(transport).query(BusQuery(QueryKey.HELLO))
        self.assertEqual(result.reasons, ('ipc_invalid',))
        self.assertEqual(transport.calls, [])

    def test_process_context_rejected_before_property_callbacks_or_reads(self):
        calls = []

        class Context:

            @property
            def uid(self):
                calls.append('uid')
                return 1000
        transport = FakeTransport()
        transport.metadata = Resolution('procfs', 'regular', 1, 2, True, False, ('10', 'stat'), (), 1000, 50)
        transport.after = transport.metadata
        reader = LinuxReader(transport, self.clock, DeadlineProfile.SYNTHETIC_ONLY, Context(), (10,))
        result = reader.read_file(FileSource(SourceKey.PROCESS_STAT, pid=10))
        self.assertEqual(result.reasons, ('process_identity_unverified',))
        self.assertEqual(calls, [])
        self.assertEqual(transport.calls, [])

class MemoryFixtureTests(unittest.TestCase):

    def test_explicit_fixture_reader_reads_detached_memory_sources(self):
        from hybrid_display.host_reader import EnvKey
        from hybrid_display.linux_reader import FixtureReader
        env = ((EnvKey.SESSION_ID, b's1'),)
        source = FileSource(SourceKey.DRM_STATUS, 0, 'DP-1')
        files = ((source, b'connected\n', resolution(), resolution()),)
        query = BusQuery(QueryKey.HELLO)
        auth = BusQuery(QueryKey.AUTH)
        reader = FixtureReader(env, files, ((auth, (b'"OK"',)), (query, (b':1.9',))), FakeClock(), QueryContext(1000, 10))
        self.assertEqual(reader.read_env(EnvKey.SESSION_ID).payload, b's1')
        self.assertEqual(reader.read_file(source).payload, b'connected\n')
        self.assertEqual(reader.query(auth).payload, b'"OK"')
        self.assertEqual(reader.query(query).payload, b':1.9')
        self.assertNotIn('DP-1', repr(reader.transport))
