"""Injected one-client runtime; native operations belong only to fixtures."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import array
import os
import socket
import stat
import struct
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display import reader_service_runtime as runtime
from hybrid_display import reader_service_protocol as wire
from hybrid_display.reader_service_policy import PeerFacts
from hybrid_display.reader_service_client import Packet


class Clock:
    value = 0.0
    def now(self):
        return self.value


class Backend:
    def __init__(self):
        self.requests = []
    def capture(self, request):
        self.requests.append(request.client_pids)
        return wire.Response('owner_missing')


class IO:
    """Trusted primitives own resources independently of returned metadata."""
    def __init__(self, data=None):
        self.data = wire.encode_request(wire.Request((5,))).value if data is None else data
        self.activation_fds = (7,)
        self.metadata = runtime.Listener('unix', 'stream', True, False, True, True, (1, 2))
        self.credentials = (23, 1000, 1000)
        self.facts = PeerFacts(1000, 1000, 23, 99, 'fixture', 1000,
                              'wayland', 'KDE', False, True, 'user', 'active', True)
        self.events = []
        self.sent = b''
        self.pending = []
        self.closed_fds = []
    def activation(self):
        self.events.append('activation')
        return self.activation_fds
    def listener_metadata(self, handle):
        self.events.append('metadata')
        return self.metadata
    def accept(self, handle, remaining):
        self.events.append('accept')
        return 8
    def peer(self, handle):
        self.events.append('peer')
        return self.credentials
    def session(self, credentials):
        self.events.append('session')
        return self.facts
    def recvmsg(self, handle, size, remaining):
        self.events.append(('recv', size, remaining))
        data, self.data = self.data[:size], self.data[size:]
        return Packet(data)
    def close_received(self, handle):
        self.closed_fds.extend(self.pending)
        self.pending.clear()
    def send(self, handle, data, remaining):
        self.events.append(('send', remaining))
        size = min(3, len(data))
        self.sent += data[:size]
        return size
    def close_client(self):
        self.events.append('close_client')
        self.close_received(None)
    def close_activation(self):
        self.events.append('close_activation')


class Monotonic:
    def now(self):
        return time.monotonic()


class SocketFixture(IO):
    """Test owns paths; runtime receives only a registry-owned listening FD.

    Client connects and sends before serve_once: no worker/thread is needed for
    these small bounded frames. No real activation, session or backend is used.
    """
    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='reader-runtime-')
        self.root = Path(self.temporary.name)
        self.path = self.root / 'fixture.sock'
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.caller = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.accepted = None
        self.pending_native = []
        self.received = []
        self.listener.bind(str(self.path))
        self.listener.listen(1)
        self.listener.setblocking(False)
        entry = self.path.lstat()
        self.owned_inode = (entry.st_dev, entry.st_ino)
        self.activation_fds = (self.listener.fileno(),)
        self.facts = replace(self.facts, uid=os.getuid(), euid=os.geteuid(),
                             session_uid=os.getuid(), pid=os.getpid())
        self.caller.settimeout(1)
        self.caller.connect(str(self.path))
        return self

    def remove_owned_endpoint(self):
        try:
            entry = self.path.lstat()
        except FileNotFoundError:
            return False
        if (stat.S_ISSOCK(entry.st_mode)
                and (entry.st_dev, entry.st_ino) == self.owned_inode):
            self.path.unlink()
            return True
        return False

    def __exit__(self, *args):
        try:
            self.close_client()
            self.close_activation()
            self.caller.close()
            self.remove_owned_endpoint()
        finally:
            self.temporary.cleanup()

    def listener_metadata(self, handle):
        self.events.append('metadata')
        self.assert_listener_handle(handle)
        data = os.fstat(handle)
        return runtime.Listener('unix' if self.listener.family == socket.AF_UNIX else 'other',
            'stream' if self.listener.type & socket.SOCK_STREAM else 'other',
            bool(self.listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)),
            self.listener.fileno() < 0, not self.listener.getblocking(),
            not self.listener.get_inheritable(), (data.st_dev, data.st_ino))

    def assert_listener_handle(self, handle):
        if handle != self.listener.fileno():
            raise AssertionError('fixture listener identity')

    def accept(self, handle, remaining):
        self.assert_listener_handle(handle)
        self.events.append('accept')
        # Test-only readiness wait; restore the listening descriptor flags.
        self.listener.settimeout(remaining)
        try:
            self.accepted, _ = self.listener.accept()
        finally:
            self.listener.setblocking(False)
        self.accepted.set_inheritable(False)
        return self.accepted.fileno()

    def connection(self, handle):
        if self.accepted is None or handle != self.accepted.fileno():
            raise AssertionError('fixture connection identity')
        return self.accepted

    def peer(self, handle):
        self.events.append('peer')
        return struct.unpack('3i', self.connection(handle).getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, 12))

    def recvmsg(self, handle, size, remaining):
        connection = self.connection(handle)
        connection.settimeout(remaining)
        self.events.append(('recv', size, remaining))
        data, ancillary, flags, _ = connection.recvmsg(size,
            socket.CMSG_SPACE(32 * array.array('i').itemsize), socket.MSG_CMSG_CLOEXEC)
        try:
            for level, kind, payload in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    numbers = array.array('i')
                    numbers.frombytes(payload[:len(payload) - len(payload) % numbers.itemsize])
                    self.pending_native.extend(numbers)
            self.received.extend(self.pending_native)
            return Packet(data, tuple(self.pending_native), bool(ancillary),
                          bool(flags & socket.MSG_CTRUNC))
        except BaseException:
            self.close_received(handle)
            raise

    def close_received(self, handle):
        pending, self.pending_native = self.pending_native, []
        for fd in pending:
            os.close(fd)
            self.closed_fds.append(fd)

    def send(self, handle, data, remaining):
        connection = self.connection(handle)
        connection.settimeout(remaining)
        return connection.send(data[:3])

    def close_client(self):
        self.close_received(None)
        if self.accepted is not None:
            self.accepted.close()
        self.events.append('close_client')

    def close_activation(self):
        self.listener.close()
        self.events.append('close_activation')


class RuntimeTests(unittest.TestCase):
    def test_response_expiry_is_not_reset_after_frame_readiness(self):
        io, clock = IO(), Clock()
        actual_service = runtime.Service
        class PausedService(actual_service):
            def finish(self):
                result = super().finish()
                # Inject scheduling latency after real state-machine readiness;
                # keep its framing, peer policy and original expiry unchanged.
                clock.value = .200
                return result
        send = io.send
        def late_write(*args):
            clock.value = .300
            return send(*args)
        io.send = late_write
        with patch.object(runtime, 'Service', PausedService):
            result = runtime.serve_once(1000, 'fixture', io, clock, Backend())
        self.assertEqual(result.reason, 'source_timeout')
        self.assertIsNone(result.value)
        self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])

    def test_real_activated_fixture_roundtrip_closes_both_owned_sockets(self):
        with SocketFixture() as io:
            root = io.root
            io.caller.sendall(io.data)
            io.caller.shutdown(socket.SHUT_WR)
            backend = Backend()
            result = runtime.serve_once(io.facts.uid, 'fixture', io, Monotonic(), backend)
            self.assertTrue(result.ok, result.reason)
            received = b''
            while True:
                chunk = io.caller.recv(4096)
                if not chunk:
                    break
                received += chunk
            self.assertEqual(wire.decode_frame(received, True).value.reason, 'owner_missing')
            self.assertEqual(backend.requests, [(5,)])
            self.assertEqual(io.events.count('peer'), 1)
            self.assertEqual(io.events.count('accept'), 1)
            self.assertEqual(io.listener.fileno(), -1)
            self.assertEqual(io.accepted.fileno(), -1)
            self.assertTrue(io.path.exists())  # Product never removes the fixture path.
            self.assertTrue(io.remove_owned_endpoint())
        self.assertFalse(root.exists())

    def test_real_received_rights_and_ctrunc_are_drained_on_rejection(self):
        for count in (1, 40):
            with self.subTest(count=count), SocketFixture() as io:
                descriptors = array.array('i', [io.caller.fileno()] * count)
                io.caller.sendmsg([io.data[:1]],
                    [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors)])
                backend = Backend()
                result = runtime.serve_once(io.facts.uid, 'fixture', io, Monotonic(), backend)
                self.assertEqual(result.reason, 'ipc_invalid')
                self.assertFalse(backend.requests)
                self.assertTrue(io.received)
                self.assertEqual(sorted(io.closed_fds), sorted(io.received))
                for fd in io.received:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
                self.assertEqual(io.listener.fileno(), -1)
                self.assertEqual(io.accepted.fileno(), -1)

    def test_fixture_never_unlinks_replacement_file_or_symlink(self):
        for replacement in ('file', 'symlink', 'socket'):
            with self.subTest(replacement=replacement), SocketFixture() as io:
                io.path.unlink()
                neighbor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    if replacement == 'file':
                        io.path.touch()
                    elif replacement == 'symlink':
                        io.path.symlink_to(io.root / 'absent')
                    else:
                        neighbor.bind(str(io.path))
                    before = io.path.lstat()
                    self.assertFalse(io.remove_owned_endpoint())
                    after = io.path.lstat()
                    self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
                finally:
                    neighbor.close()

    def test_invalid_accepted_handle_is_not_passed_to_credential_primitive(self):
        for value in (None, True, -1, 7, object()):
            io = IO()
            def accept(*args):
                io.events.append('accept')
                return value
            io.accept = accept
            self.assertEqual(runtime.serve_once(1000, 'fixture', io, Clock(), Backend()).reason,
                             'source_not_allowed')
            self.assertNotIn('peer', io.events)
            self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])

    def test_no_default_activation_or_host_access(self):
        self.assertEqual(runtime.serve_once(1000, 'fixture').reason, 'source_unavailable')
        from tests.test_hybrid_display_safety import product_violations
        path = 'prototype/hybrid-display/src/hybrid_display/reader_service_runtime.py'
        source = (Path(__file__).resolve().parents[1] / path).read_text()
        self.assertEqual(product_violations(path, source), [])
        import ast
        tree = ast.parse(source)
        forbidden = {'socket', 'bind', 'listen', 'lstat', 'unlink', 'open', 'getenv',
                     'system', 'spawn', 'Thread', 'connect'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
                self.assertNotIn(name, forbidden)
        self.assertNotIn('/run/user', source)
        self.assertNotIn('__main__', source)

    def test_header_deadline_and_partial_header_never_slide(self):
        io, clock, backend = IO(), Clock(), Backend()
        receive = io.recvmsg
        def fragment(handle, size, remaining):
            clock.value += .025
            return receive(handle, 1, remaining)
        io.recvmsg = fragment
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, clock, backend).reason, 'source_timeout')
        self.assertFalse(backend.requests)
        self.assertLessEqual(clock.value, .101)

    def test_request_eof_has_absolute_quarter_second_budget(self):
        io, clock, backend = IO(), Clock(), Backend()
        receive = io.recvmsg
        def delayed_eof(handle, size, remaining):
            if not io.data:
                clock.value = .250
            return receive(handle, size, remaining)
        io.recvmsg = delayed_eof
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, clock, backend).reason, 'source_timeout')
        self.assertFalse(backend.requests)
        self.assertFalse(io.sent)

    def test_header_and_request_deadlines_start_at_accept_not_after_peer(self):
        io, clock, backend = IO(), Clock(), Backend()
        peer = io.peer
        def delayed(handle):
            clock.value = .100
            return peer(handle)
        io.peer = delayed
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, clock, backend).reason, 'source_timeout')
        self.assertFalse(backend.requests)

    def test_incomplete_extra_and_trailing_frames_never_reach_backend(self):
        frame = wire.encode_request(wire.Request((5,))).value
        for data in (b'', frame[:3], frame[:-1], frame + b'x', frame + frame,
                     wire.header(wire.MessageType.BLOCKED, 2) + b'\x00\x01'):
            with self.subTest(length=len(data)):
                io, backend = IO(data), Backend()
                result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
                self.assertEqual(result.reason, 'ipc_invalid')
                self.assertIsNone(result.value)
                self.assertFalse(backend.requests)
                self.assertFalse(io.sent)
                self.assertEqual(io.events.count('accept'), 1)
                self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])

    def test_session_mismatch_and_changed_receipts_block(self):
        for changes in ({'remote': True}, {'verified': False}, {'session_id': 'other'},
                        {'session_class': 'manager'}, {'euid': 0}):
            io, backend = IO(), Backend()
            io.facts = replace(io.facts, **changes)
            self.assertEqual(runtime.serve_once(1000, 'fixture', io, Clock(), backend).reason,
                             'session_unverified')
            self.assertFalse(backend.requests)
        io, backend = IO(), Backend()
        receive = io.recvmsg
        def changed(*args):
            io.facts = replace(io.facts, starttime=100)
            return receive(*args)
        io.recvmsg = changed
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, Clock(), backend).reason,
                         'inventory_changed')
        self.assertFalse(backend.requests)
        self.assertEqual(io.events.count('peer'), 1)

    def test_listener_receipt_replacement_blocks_before_request(self):
        io, backend = IO(), Backend()
        peer = io.peer
        def replace_after_accept(handle):
            io.metadata = replace(io.metadata, identity=(1, 99))
            return peer(handle)
        io.peer = replace_after_accept
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, Clock(), backend).reason,
                         'source_not_allowed')
        self.assertFalse(backend.requests)

    def test_backend_exception_systemexit_unknown_and_timeout_are_closed(self):
        for error in (RuntimeError('private-secret'), SystemExit('private-secret'),
                      TimeoutError('private-secret')):
            io, backend = IO(), Backend()
            def capture(request):
                backend.requests.append(request.client_pids)
                raise error
            backend.capture = capture
            result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
            self.assertTrue(result.ok)
            self.assertEqual(wire.decode_frame(io.sent, True).value.reason, 'reader_failed')
            self.assertEqual(backend.requests, [(5,)])
            self.assertNotIn('private-secret', repr(result))
        io, backend = IO(), Backend()
        backend.capture = lambda request: wire.Response('unknown-error')
        self.assertTrue(runtime.serve_once(1000, 'fixture', io, Clock(), backend).ok)
        self.assertEqual(wire.decode_frame(io.sent, True).value.reason, 'reader_failed')

    def test_backend_late_return_has_no_response(self):
        io, clock, backend = IO(), Clock(), Backend()
        def capture(request):
            backend.requests.append(request.client_pids)
            clock.value = 4
            return wire.Response('owner_missing')
        backend.capture = capture
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, clock, backend).reason,
                         'source_timeout')
        self.assertEqual(backend.requests, [(5,)])
        self.assertFalse(io.sent)

    def test_io_exceptions_cleanup_and_no_retry(self):
        for operation in ('activation', 'listener_metadata', 'accept', 'peer', 'session',
                          'recvmsg', 'send', 'close_received', 'close_client', 'close_activation'):
            for error in (RuntimeError('private-secret'), SystemExit('private-secret'), TimeoutError()):
                with self.subTest(operation=operation, error=type(error).__name__):
                    io = IO()
                    original = getattr(io, operation)
                    def fail(*args):
                        if operation in ('close_client', 'close_activation'):
                            original(*args)
                        raise error
                    setattr(io, operation, fail)
                    result = runtime.serve_once(1000, 'fixture', io, Clock(), Backend())
                    self.assertFalse(result.ok)
                    self.assertIn(result.reason, wire.REASONS)
                    self.assertIsNone(result.value)
                    self.assertNotIn('private-secret', repr(result))
                    self.assertLessEqual(io.events.count('accept'), 1)
                    self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])

    def test_invalid_send_counts_and_aborted_clients_do_not_report_success(self):
        for count in (0, -1, True, 19, None):
            io, backend = IO(), Backend()
            io.send = lambda *args: count
            result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
            self.assertEqual(result.reason, 'ipc_invalid')
            self.assertEqual(backend.requests, [(5,)])
            self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])

    def test_untrusted_metadata_subclasses_never_execute_callbacks(self):
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
        class Text(str):
            def __eq__(self, other):
                calls.append('eq')
                raise AssertionError
        for field, value in (('activation_fds', Trap()), ('credentials', Trap()),
                             ('metadata', Trap())):
            io = IO()
            setattr(io, field, value)
            self.assertFalse(runtime.serve_once(1000, 'fixture', io, Clock(), Backend()).ok)
        for field in ('family', 'kind', 'identity', 'listening', 'closed'):
            io = IO()
            io.metadata = replace(io.metadata, **{field: Text('unix')})
            self.assertFalse(runtime.serve_once(1000, 'fixture', io, Clock(), Backend()).ok)
        io = IO()
        io.recvmsg = lambda *args: Packet(Trap())
        self.assertFalse(runtime.serve_once(1000, 'fixture', io, Clock(), Backend()).ok)
        self.assertEqual(calls, [])

    def test_successive_invocations_have_detached_peer_decoder_and_backend_state(self):
        first, second = IO(), IO(wire.encode_request(wire.Request((6,))).value)
        a, b = Backend(), Backend()
        for io, backend in ((first, a), (second, b)):
            self.assertTrue(runtime.serve_once(1000, 'fixture', io, Clock(), backend).ok)
            self.assertEqual(io.events.count('accept'), 1)
            self.assertEqual(io.events.count('peer'), 1)
        self.assertEqual(a.requests, [(5,)])
        self.assertEqual(b.requests, [(6,)])

    def test_header_is_bounded_before_any_body_read(self):
        for length in (wire.MAX_REQUEST, 0xffffffff):
            io, backend = IO(wire.header(wire.MessageType.CAPTURE_IPC, length)), Backend()
            result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
            self.assertEqual(result.reason, 'ipc_limit')
            self.assertEqual([item[1] for item in io.events if type(item) is tuple], [16])
            self.assertFalse(backend.requests)

    def test_ancillary_registry_drained_even_for_malformed_packet_or_late_return(self):
        for packet in (Packet(b'', (9,), True), Packet(b'', tuple(range(33)), True),
                       Packet(b'', (), False, True), None):
            for late in (False, True):
                io, clock, backend = IO(), Clock(), Backend()
                def receive(*args):
                    io.pending = [9, 10]
                    if late:
                        clock.value = 4
                    return packet
                io.recvmsg = receive
                result = runtime.serve_once(1000, 'fixture', io, clock, backend)
                self.assertEqual(result.reason, 'source_timeout' if late else 'ipc_invalid')
                self.assertEqual(io.closed_fds, [9, 10])
                self.assertFalse(io.pending)
                self.assertFalse(backend.requests)

    def test_partial_writes_cannot_reset_response_deadline(self):
        io, clock, backend = IO(), Clock(), Backend()
        send = io.send
        def delayed(handle, data, remaining):
            clock.value += .050
            return send(handle, data, remaining)
        io.send = delayed
        result = runtime.serve_once(1000, 'fixture', io, clock, backend)
        self.assertEqual(result.reason, 'source_timeout')
        self.assertIsNone(result.value)
        self.assertLess(len(io.sent), 18)
        remaining = [item[1] for item in io.events if type(item) is tuple and item[0] == 'send']
        self.assertEqual(remaining, sorted(remaining, reverse=True))
        self.assertLessEqual(remaining[0], .250)

    def test_entry_accept_and_cleanup_share_total_budget(self):
        for operation in ('activation', 'accept', 'close_client'):
            io, clock, backend = IO(), Clock(), Backend()
            original = getattr(io, operation)
            def late(*args):
                value = original(*args)
                clock.value = 4
                return value
            setattr(io, operation, late)
            result = runtime.serve_once(1000, 'fixture', io, clock, backend)
            self.assertEqual(result.reason, 'source_timeout')
            if operation != 'close_client':
                self.assertFalse(backend.requests)
            self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])

    def test_activation_count_and_listener_properties_fail_closed(self):
        for fds in (None, (), (7, 9), [7], (True,), (-1,)):
            with self.subTest(fds=fds):
                io, backend = IO(), Backend()
                io.activation_fds = fds
                result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
                self.assertEqual(result.reason, 'source_not_allowed')
                self.assertNotIn('accept', io.events)
                self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])
                self.assertFalse(backend.requests)
        for changes in ({'family': 'abstract'}, {'family': 'inet'}, {'kind': 'datagram'},
                        {'listening': False}, {'closed': True}, {'nonblocking': False},
                        {'cloexec': False}, {'identity': (True, 2)}, {'family': True}):
            with self.subTest(changes=changes):
                io = IO()
                io.metadata = replace(io.metadata, **changes)
                result = runtime.serve_once(1000, 'fixture', io, Clock(), Backend())
                self.assertEqual(result.reason, 'source_not_allowed')
                self.assertNotIn('accept', io.events)
        io = IO()
        io.metadata = {'family': 'unix', 'extra': 'forbidden'}
        self.assertEqual(runtime.serve_once(1000, 'fixture', io, Clock(), Backend()).reason,
                         'source_not_allowed')

    def test_kernel_credentials_must_match_session_receipt(self):
        for credentials in (None, (True, 1000, 1000), (23, 0, 0), (23, 1001, 1000),
                            (24, 1000, 1000), [23, 1000, 1000]):
            with self.subTest(credentials=credentials):
                io, backend = IO(), Backend()
                io.credentials = credentials
                result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
                self.assertEqual(result.reason, 'session_unverified')
                self.assertEqual(io.events.count('peer'), 1)
                self.assertFalse(backend.requests)
                self.assertFalse(io.sent)

    def test_one_request_one_response_and_owned_cleanup(self):
        io, backend = IO(), Backend()
        result = runtime.serve_once(1000, 'fixture', io, Clock(), backend)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.value, 0)
        self.assertEqual(wire.decode_frame(io.sent, response=True).value.reason, 'owner_missing')
        self.assertEqual(backend.requests, [(5,)])
        self.assertEqual(io.events.count('accept'), 1)
        self.assertEqual(io.events.count('peer'), 1)
        self.assertEqual(io.events[io.events.index('accept') + 1], 'peer')
        self.assertEqual(io.events[-2:], ['close_client', 'close_activation'])
