"""Synthetic event sources/sinks and trusted callbacks; no native transport."""
import sys
import unittest
from dataclasses import replace
sys.path.insert(0, 'prototype/hybrid-display/src')
from hybrid_display import reader_service_protocol as p
from hybrid_display import reader_service_policy as q
from hybrid_display import reader_service_state as m

class Clock:
    value = 0
    def now(self):
        return self.value

class Peers:
    def __init__(self):
        self.value = q.PeerFacts(1000, 1000, 23, 99, 'fixture', 1000, 'wayland', 'KDE', False, True, 'user', 'active', True)
    def current(self):
        return self.value

class Reader:
    def __init__(self):
        self.calls = []
        self.response = p.Response()
    def capture(self, request):
        self.calls.append(request)
        return self.response

class StateTests(unittest.TestCase):
    def test_declared_conflict_list_cannot_claim_kernel_peer(self):
        for side in ('service', 'client'):
            with self.subTest(side=side):
                if side == 'service':
                    service, clock, peers, reader = self.service()
                    self.assertTrue(service.feed(p.encode_request(p.Request((23,))).value).ok)
                    self.assertEqual(service.finish().reason, 'session_unverified')
                    self.assertEqual(reader.calls, [])
                else:
                    client = m.Client(Clock(), Peers(), 1000, 'fixture')
                    self.assertEqual(client.request(p.Request((23,))).reason, 'session_unverified')

    def service(self):
        clock, peers, reader = Clock(), Peers(), Reader()
        service = m.Service(clock, peers, reader, 1000, 'fixture')
        self.assertTrue(service.start().ok)
        self.assertTrue(service.accept().ok)
        return service, clock, peers, reader

    def test_service_one_request_one_atomic_response(self):
        service, clock, peers, reader = self.service()
        request = p.encode_request(p.Request((4,))).value
        self.assertTrue(service.feed(request).ok)
        self.assertEqual(reader.calls, [])
        self.assertTrue(service.finish().ok)
        self.assertEqual(len(reader.calls), 1)
        response = service.emit()
        self.assertTrue(response.ok)
        self.assertEqual(p.decode_frame(response.value, True).value.reason, 'kscreen_profile_unverified')
        self.assertFalse(service.emit().ok)
        self.assertFalse(service.finish().ok)
        self.assertFalse(service.start().ok)
        self.assertEqual(len(reader.calls), 1)

    def test_reader_never_called_before_valid_peer_frame_and_eof(self):
        for frame in (b'', b'H', p.encode_request(p.Request()).value + b'x'):
            service, clock, peers, reader = self.service()
            service.feed(frame)
            self.assertFalse(service.finish().ok)
            self.assertEqual(reader.calls, [])
        service, clock, peers, reader = self.service()
        peers.value = replace(peers.value, session_id='other')
        self.assertFalse(service.feed(p.encode_request(p.Request()).value).ok)
        self.assertEqual(reader.calls, [])

    def test_peer_change_and_pid_reuse_block(self):
        for changes in ({'uid': 1001}, {'pid': 24}, {'starttime': 100}, {'verified': False}):
            service, clock, peers, reader = self.service()
            self.assertTrue(service.feed(p.encode_request(p.Request()).value).ok)
            peers.value = replace(peers.value, **changes)
            self.assertFalse(service.finish().ok)
            self.assertEqual(reader.calls, [])

    def test_reader_exception_is_fixed_blocked_frame(self):
        service, clock, peers, reader = self.service()
        def broken(request):
            raise RuntimeError('private-session-value')
        reader.capture = broken
        self.assertTrue(service.feed(p.encode_request(p.Request()).value).ok)
        self.assertTrue(service.finish().ok)
        response = service.emit()
        self.assertTrue(response.ok)
        self.assertEqual(p.decode_frame(response.value, True).value.reason, 'reader_failed')
        self.assertNotIn(b'private-session-value', response.value)
        self.assertNotIn('private-session-value', repr(response))

    def test_reader_delay_or_peer_change_discards_response(self):
        for change in ('time', 'peer'):
            service, clock, peers, reader = self.service()
            def capture(request):
                if change == 'time':
                    clock.value = 4
                else:
                    peers.value = replace(peers.value, starttime=100)
                return p.Response()
            reader.capture = capture
            service.feed(p.encode_request(p.Request()).value)
            self.assertFalse(service.finish().ok)
            self.assertFalse(service.emit().ok)

    def test_send_deadline_and_entry_budget_are_absolute(self):
        service, clock, peers, reader = self.service()
        service.feed(p.encode_request(p.Request()).value)
        self.assertTrue(service.finish().ok)
        clock.value = .25
        self.assertEqual(service.emit().reason, 'source_timeout')
        clock, peers, reader = Clock(), Peers(), Reader()
        service = m.Service(clock, peers, reader, 1000, 'fixture')
        self.assertTrue(service.start().ok)
        clock.value = 4
        self.assertEqual(service.accept().reason, 'source_timeout')
        self.assertEqual(reader.calls, [])

    def test_client_single_canonical_request_and_complete_eof(self):
        clock, peers = Clock(), Peers()
        client = m.Client(clock, peers, 1000, 'fixture')
        request = client.request(p.Request((4,)))
        self.assertTrue(request.ok)
        self.assertEqual(request.value, p.encode_request(p.Request((4,))).value)
        self.assertTrue(client.feed(p.encode_response(p.Response('owner_missing')).value).ok)
        result = client.finish()
        self.assertTrue(result.ok)
        self.assertEqual(result.value.reason, 'owner_missing')
        self.assertFalse(client.request(p.Request()).ok)
        self.assertFalse(client.finish().ok)

    def test_client_protocol_failures_and_timeout_are_atomic(self):
        response = p.encode_response(p.Response()).value
        for data in (response[:-1], response + b'x', b'', b'HDR1' + b'\x00' * 12):
            client = m.Client(Clock(), Peers(), 1000, 'fixture')
            self.assertTrue(client.request(p.Request()).ok)
            client.feed(data)
            result = client.finish()
            self.assertFalse(result.ok)
            self.assertIsNone(result.value)
        clock = Clock()
        client = m.Client(clock, Peers(), 1000, 'fixture')
        client.request(p.Request())
        client.feed(response)
        clock.value = 5
        self.assertEqual(client.finish().reason, 'source_timeout')

    def test_peer_callback_reentry_is_terminal(self):
        service, clock, peers, reader = self.service()
        original = peers.current
        def current():
            service.feed(b'')
            return original()
        peers.current = current
        result = service.feed(p.encode_request(p.Request()).value)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, 'reader_failed')
        self.assertEqual(reader.calls, [])

    def test_invalid_reader_types_are_fixed_failure(self):
        for value in (None, {'private': 1}, object.__new__(p.Response), p.Request(), b'private'):
            service, clock, peers, reader = self.service()
            reader.response = value
            service.feed(p.encode_request(p.Request()).value)
            self.assertTrue(service.finish().ok)
            frame = service.emit()
            self.assertTrue(frame.ok)
            self.assertEqual(p.decode_frame(frame.value, True).value.reason, 'reader_failed')

    def test_client_changed_local_session_discards_complete_frame(self):
        peers = Peers()
        client = m.Client(Clock(), peers, 1000, 'fixture')
        self.assertTrue(client.request(p.Request()).ok)
        self.assertTrue(client.feed(p.encode_response(p.Response()).value).ok)
        peers.value = replace(peers.value, starttime=100)
        self.assertEqual(client.finish().reason, 'inventory_changed')

    def test_reader_cannot_reenter_or_run_twice(self):
        service, clock, peers, reader = self.service()
        def capture(request):
            reader.calls.append(request)
            self.assertFalse(service.finish().ok)
            return p.Response()
        reader.capture = capture
        service.feed(p.encode_request(p.Request()).value)
        self.assertFalse(service.finish().ok)
        self.assertFalse(service.emit().ok)
        self.assertEqual(len(reader.calls), 1)
