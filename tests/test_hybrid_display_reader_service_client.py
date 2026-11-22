"""Reader transport: synthetic metadata first, isolated temporary sockets only."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
import array
import os
import socket
import stat
import struct
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display import reader_service_client as transport
from hybrid_display import reader_service_protocol as wire
from hybrid_display.reader_service_policy import PeerFacts
from hybrid_display.reader_service_state import Service


class Clock:
    value = 0.0
    def now(self):
        return self.value


class IO:
    """Trusted in-memory primitives, not a native implementation."""
    def __init__(self, response=None):
        self.endpoint = endpoint()
        self.facts = PeerFacts(1000, 1000, 23, 99, 'fixture', 1000,
                               'wayland', 'KDE', False, True, 'user', 'active', True)
        self.credentials = (99, 1000, 1000)  # Manager PID, not graphical requester.
        self.connection_id = (2, 5)
        self.response = wire.encode_response(wire.Response('owner_missing')).value if response is None else response
        self.calls = []
        self.sent = b''
        self.closed = 0
        self.closed_fds = []
        self.pending_fds = []
    def session(self):
        return self.facts
    def lookup(self):
        return self.endpoint
    def open_unix_stream(self):
        self.calls.append('open')
        return object()
    def connect(self, handle, remaining):
        self.calls.append('connect')
    def peer(self, handle):
        self.calls.append('peer')
        return self.credentials
    def identity(self, handle):
        return self.connection_id
    def send(self, handle, data, remaining):
        self.calls.append(('send', remaining))
        size = min(3, len(data))
        self.sent += data[:size]
        return size
    def shutdown_write(self, handle, remaining):
        self.calls.append('shutdown')
    def recvmsg(self, handle, size, remaining):
        self.calls.append(('recv', size, remaining))
        chunk, self.response = self.response[:size], self.response[size:]
        return transport.Packet(chunk)
    def close(self, handle):
        self.closed += 1
    def close_fd(self, fd):
        self.closed_fds.append(fd)
    def close_received(self, handle):
        pending, self.pending_fds = self.pending_fds, []
        for fd in pending:
            self.close_fd(fd)


class Monotonic:
    def now(self):
        return time.monotonic()


class SocketFixture(IO):
    """All native primitives are TEST ONLY, rooted in one TemporaryDirectory.

    Synthetic session receipts do not assert any actual graphical session.
    There is no product-path mapping, daemon, installation or live provider.
    """
    def __init__(self, response=None, rights=0, clients=1):
        super().__init__(response)
        self.raw_response = response
        self.rights = rights
        self.clients = clients
        self.live = set()
        self.opened = []
        self.received_fds = []
        self.errors = []
        self.requests = []
        self.stopping = False
        self.pending_by_connection = {}

    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hybrid-reader-transport-')
        self.root = Path(self.temporary.name)
        self.path = self.root / 'hybrid-display-reader-v1.sock'
        self.facts = PeerFacts(os.getuid(), os.geteuid(), os.getpid(), 99, 'fixture',
                               os.getuid(), 'wayland', 'KDE', False, True, 'user', 'active', True)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        self.path.chmod(0o600)
        self.listener.listen(1)
        self.listener.settimeout(.5)
        self.worker = threading.Thread(target=self.serve, daemon=True)
        self.worker.start()
        return self

    def __exit__(self, *args):
        self.stopping = True
        self.listener.close()
        for connection in tuple(self.live):
            connection.close()
        self.worker.join(2)
        self.temporary.cleanup()
        if self.worker.is_alive():
            raise AssertionError('temporary server did not finish')

    def serve(self):
        try:
            for _ in range(self.clients):
                connection, _ = self.listener.accept()
                with connection:
                    connection.settimeout(1)
                    credentials = struct.unpack('3i', connection.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
                    if credentials[:2] != (self.facts.pid, self.facts.uid):
                        raise AssertionError('unexpected temporary client peer')
                    fixture = self
                    class Reader:
                        def capture(self, request):
                            fixture.requests.append(request.client_pids)
                            reason = 'source_denied' if request.client_pids == (6,) else 'owner_missing'
                            return wire.Response(reason)
                    class Peers:
                        def current(self):
                            return fixture.facts
                    service = Service(Monotonic(), Peers(), Reader(), self.facts.uid, 'fixture')
                    if not service.start().ok or not service.accept().ok:
                        raise AssertionError('fixture service rejected own metadata')
                    while True:
                        data = connection.recv(4096)
                        if not data:
                            break
                        if not service.feed(data).ok:
                            return
                    if not service.finish().ok:
                        return
                    response = service.emit().value if self.raw_response is None else self.raw_response
                    if self.rights:
                        descriptors = array.array('i', [self.listener.fileno()] * self.rights)
                        connection.sendmsg([response[:1]], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors)])
                        response = response[1:]
                    if response:
                        connection.sendall(response)
        except (BrokenPipeError, ConnectionResetError):
            # Expected when a malformed/ancillary response is rejected early.
            if self.raw_response is None and not self.rights and not self.stopping:
                self.errors.append('unexpected_disconnect')
        except (Exception, SystemExit) as error:
            if not self.stopping:
                self.errors.append(type(error).__name__)

    def lookup(self):
        directory, entry = self.root.lstat(), self.path.lstat()
        return transport.Endpoint(self.path.name,
            entry.st_uid if entry.st_uid == directory.st_uid else 0,
            stat.S_IMODE(directory.st_mode), stat.S_IMODE(entry.st_mode),
            (directory.st_dev, directory.st_ino), (entry.st_dev, entry.st_ino),
            not stat.S_ISDIR(directory.st_mode), stat.S_ISLNK(entry.st_mode),
            'unix', 'stream' if stat.S_ISSOCK(entry.st_mode) else 'invalid')

    def open_unix_stream(self):
        self.calls.append('open')
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.live.add(connection)
        self.opened.append(connection)
        return connection

    def connect(self, connection, remaining):
        self.calls.append('connect')
        connection.settimeout(remaining)
        connection.connect(str(self.path))

    def peer(self, connection):
        self.calls.append('peer')
        return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))

    def identity(self, connection):
        data = os.fstat(connection.fileno())
        return (data.st_dev, data.st_ino)

    def send(self, connection, data, remaining):
        connection.settimeout(remaining)
        size = connection.send(data[:3])
        self.sent += data[:size]
        return size

    def shutdown_write(self, connection, remaining):
        connection.settimeout(remaining)
        connection.shutdown(socket.SHUT_WR)

    def recvmsg(self, connection, size, remaining):
        connection.settimeout(remaining)
        data, ancillary, flags, _ = connection.recvmsg(size,
            socket.CMSG_SPACE(32 * array.array('i').itemsize), socket.MSG_CMSG_CLOEXEC)
        fds = []
        try:
            for level, kind, payload in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    numbers = array.array('i')
                    numbers.frombytes(payload[:len(payload) - len(payload) % numbers.itemsize])
                    fds.extend(numbers)
            self.received_fds.extend(fds)
            self.pending_by_connection[connection] = fds
            return transport.Packet(data, tuple(fds), bool(ancillary), bool(flags & socket.MSG_CTRUNC))
        except BaseException:
            for fd in fds:
                os.close(fd)
            raise

    def close(self, connection):
        connection.close()
        self.live.discard(connection)
        self.closed += 1

    def close_fd(self, fd):
        os.close(fd)
        self.closed_fds.append(fd)

    def close_received(self, connection):
        for fd in self.pending_by_connection.pop(connection, []):
            self.close_fd(fd)


def endpoint(**changes):
    return replace(transport.Endpoint('hybrid-display-reader-v1.sock', 1000,
                                      0o700, 0o600, (1, 2), (1, 3)), **changes)


class TransportTests(unittest.TestCase):
    def test_overlimit_or_malformed_fd_metadata_cannot_prevent_owned_cleanup(self):
        for packet in (transport.Packet(b'', tuple(range(33)), True), None):
            with self.subTest(malformed=packet is None):
                io = IO()
                def recv(*args):
                    io.pending_fds = list(range(33))
                    return packet
                io.recvmsg = recv
                result = transport.capture_ipc((), io, Clock())
                self.assertFalse(result.ok)
                self.assertEqual(io.closed_fds, list(range(33)))
                self.assertFalse(io.pending_fds)
                self.assertEqual(io.closed, 1)
    def test_client_keeps_unchanged_pure_core_and_no_installation_boundary(self):
        from tests.test_hybrid_display_safety import product_violations
        path = 'prototype/hybrid-display/src/hybrid_display/reader_service_client.py'
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(product_violations(path, (root / path).read_text()), [])
        for source in ('import socket', 'import os', 'import dbus', 'import subprocess',
                       'open("private")', 'adapter.kill(1)',
                       'if __name__ == "__main__":\n    start()'):
            self.assertTrue(product_violations(path, source))
        self.assertFalse((root / 'prototype/hybrid-display/packaging').exists())

    def test_real_temporary_socket_and_kernel_peer_roundtrip(self):
        with SocketFixture() as io:
            root = io.root
            result = transport.capture_ipc((5,), io, Monotonic())
            self.assertTrue(result.ok, result.reason)
            self.assertEqual(result.value.reason, 'owner_missing')
            self.assertEqual(io.calls.count('peer'), 1)
            self.assertEqual(io.sent, wire.encode_request(wire.Request((5,))).value)
            self.assertEqual(io.closed, 1)
            self.assertTrue(all(connection.fileno() == -1 for connection in io.opened))
            self.assertEqual(io.errors, [])
        self.assertFalse(root.exists())

    def test_real_rights_and_ancillary_truncation_leave_no_owned_fds(self):
        for count in (1, 40):
            with self.subTest(count=count), SocketFixture(rights=count) as io:
                result = transport.capture_ipc((), io, Monotonic())
                self.assertEqual(result.reason, 'ipc_invalid')
                self.assertTrue(io.received_fds)
                self.assertEqual(sorted(io.closed_fds), sorted(io.received_fds))
                for fd in io.received_fds:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
                self.assertTrue(all(connection.fileno() == -1 for connection in io.opened))

    def test_real_symlink_and_replaced_socket_paths_block(self):
        with SocketFixture() as io:
            io.path.unlink()
            io.path.symlink_to(io.root / 'missing')
            self.assertEqual(transport.capture_ipc((), io, Monotonic()).reason, 'source_not_allowed')
            self.assertEqual(io.calls, [])
        with SocketFixture() as io:
            original = io.connect
            replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                def connect(connection, remaining):
                    original(connection, remaining)
                    io.path.unlink()
                    replacement.bind(str(io.path))
                    io.path.chmod(0o600)
                io.connect = connect
                self.assertEqual(transport.capture_ipc((), io, Monotonic()).reason, 'inventory_changed')
                self.assertEqual(io.closed, 1)
            finally:
                replacement.close()

    def test_concurrent_temporary_clients_have_no_shared_protocol_state(self):
        with SocketFixture(clients=2) as io:
            results = {}
            def request(pid):
                results[pid] = transport.capture_ipc((pid,), io, Monotonic())
            workers = [threading.Thread(target=request, args=(pid,)) for pid in (5, 6)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(2)
                self.assertFalse(worker.is_alive())
            self.assertEqual(results[5].value.reason, 'owner_missing')
            self.assertEqual(results[6].value.reason, 'source_denied')
            self.assertEqual(sorted(io.requests), [(5,), (6,)])
            self.assertEqual(io.closed, 2)
            self.assertFalse(io.live)

    def test_real_malformed_server_response_is_atomic_and_closed(self):
        frame = wire.encode_response(wire.Response()).value
        for response in (frame[:-1], frame + b'x', frame + frame,
                         wire.header(wire.MessageType.BLOCKED, 0xffffffff)):
            with SocketFixture(response=response) as io:
                result = transport.capture_ipc((), io, Monotonic())
                self.assertFalse(result.ok)
                self.assertIsNone(result.value)
                self.assertEqual(io.closed, 1)
                self.assertTrue(all(connection.fileno() == -1 for connection in io.opened))

    def test_invalid_request_and_absent_backend_do_not_activate_anything(self):
        self.assertEqual(transport.capture_ipc(()).reason, 'source_unavailable')
        class Unvisited:
            def __getattribute__(self, name):
                raise AssertionError('request must be checked before I/O')
        for value in ([], (True,), (0,), (7, 7), tuple(range(1, 18))):
            self.assertEqual(transport.capture_ipc(value, Unvisited(), Clock()).reason, 'input_invalid')

    def test_bad_endpoint_or_session_blocks_before_connect(self):
        for changes in ({'uid': 1001}, {'socket_symlink': True}, {'name': '../neighbor'}):
            io = IO()
            io.endpoint = endpoint(**changes)
            self.assertFalse(transport.capture_ipc((), io, Clock()).ok)
            self.assertEqual(io.calls, [])
        for changes in ({'remote': True}, {'session_type': 'tty'}, {'session_class': 'manager'},
                        {'uid': True}, {'euid': 0}, {'verified': False}):
            io = IO()
            io.facts = replace(io.facts, **changes)
            self.assertEqual(transport.capture_ipc((), io, Clock()).reason, 'session_unverified')
            self.assertEqual(io.calls, [])

    def test_wrong_kernel_uid_closes_one_attempt(self):
        io = IO()
        io.credentials = (99, 1001, 1000)
        self.assertEqual(transport.capture_ipc((), io, Clock()).reason, 'session_unverified')
        self.assertEqual(io.closed, 1)
        self.assertEqual(io.calls.count('peer'), 1)
        self.assertEqual(io.sent, b'')

    def test_replaced_path_connection_or_session_is_atomic(self):
        for changed in ('path', 'connection', 'session'):
            io = IO()
            original = io.recvmsg
            def recv(*args):
                value = original(*args)
                if changed == 'path':
                    io.endpoint = replace(io.endpoint, socket_id=(1, 99))
                elif changed == 'connection':
                    io.connection_id = (2, 99)
                else:
                    io.facts = replace(io.facts, starttime=100)
                return value
            io.recvmsg = recv
            result = transport.capture_ipc((), io, Clock())
            self.assertEqual(result.reason, 'inventory_changed')
            self.assertIsNone(result.value)
            self.assertEqual(io.closed, 1)

    def test_header_limit_is_checked_before_any_body_receive(self):
        for size in (wire.MAX_RESPONSE, 0xffffffff):
            io = IO(wire.header(wire.MessageType.BLOCKED, size))
            result = transport.capture_ipc((), io, Clock())
            self.assertEqual(result.reason, 'ipc_limit')
            self.assertEqual([x[1] for x in io.calls if type(x) is tuple and x[0] == 'recv'], [16])
            self.assertEqual(io.closed, 1)

    def test_trailing_frames_and_incomplete_eof_never_commit(self):
        frame = wire.encode_response(wire.Response()).value
        for data in (frame + b'x', frame + frame, frame[:-1], frame[:5], b''):
            io = IO(data)
            result = transport.capture_ipc((), io, Clock())
            self.assertFalse(result.ok)
            self.assertIsNone(result.value)
            self.assertEqual(io.closed, 1)
        bad = bytearray(frame)
        bad[8:12] = b'\xff' * 4  # Unsigned negative/overflow representation.
        self.assertEqual(transport.capture_ipc((), IO(bytes(bad)), Clock()).reason, 'ipc_limit')

    def test_fragmented_receive_cannot_extend_total_deadline(self):
        io, clock = IO(), Clock()
        original = io.recvmsg
        def recv(handle, size, remaining):
            clock.value += .4
            return original(handle, 1, remaining)
        io.recvmsg = recv
        result = transport.capture_ipc((), io, clock)
        self.assertEqual(result.reason, 'source_timeout')
        self.assertIsNone(result.value)
        self.assertEqual(io.closed, 1)
        remaining = [x[2] for x in io.calls if type(x) is tuple and x[0] == 'recv']
        self.assertEqual(remaining, sorted(remaining, reverse=True))

    def test_late_open_and_cleanup_time_cannot_escape_budget(self):
        for stage in ('open', 'close'):
            io, clock = IO(), Clock()
            if stage == 'open':
                original = io.open_unix_stream
                def late():
                    handle = original()
                    clock.value = 5
                    return handle
                io.open_unix_stream = late
            else:
                original = io.close
                def late(handle):
                    original(handle)
                    clock.value = 5
                io.close = late
            self.assertEqual(transport.capture_ipc((), io, clock).reason, 'source_timeout')
            self.assertEqual(io.closed, 1)

    def test_exceptions_are_fixed_private_and_never_retried(self):
        for operation in ('connect', 'peer', 'send', 'shutdown_write', 'recvmsg', 'close'):
            for error, reason in ((RuntimeError('private-path'), 'reader_failed'),
                                  (SystemExit('private-path'), 'reader_failed'),
                                  (TimeoutError('private-path'), 'source_timeout')):
                io = IO()
                def fail(*args):
                    if operation == 'close':
                        io.closed += 1
                    raise error
                setattr(io, operation, fail)
                result = transport.capture_ipc((), io, Clock())
                self.assertFalse(result.ok)
                self.assertEqual(result.reason, 'reader_failed' if operation == 'close' else reason)
                self.assertNotIn('private-path', repr(result))
                self.assertEqual(io.closed, 1)
                self.assertLessEqual(io.calls.count('connect'), 1)

    def test_untrusted_packet_and_metadata_callbacks_are_never_run(self):
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
        for value in (Trap(),):
            self.assertFalse(transport.credentials_valid(value, 1000))
            self.assertFalse(transport.endpoint_valid(endpoint(socket_id=value), 1000))
            io = IO()
            io.recvmsg = lambda *args: transport.Packet(b'', value)
            self.assertFalse(transport.capture_ipc((), io, Clock()).ok)
            self.assertEqual(io.closed, 1)
        self.assertEqual(calls, [])

    def test_unknown_error_codes_and_unavailable_profile_stay_closed(self):
        io = IO(wire.header(wire.MessageType.BLOCKED, 2) + b'\xff\xff')
        result = transport.capture_ipc((), io, Clock())
        self.assertTrue(result.ok)
        self.assertEqual(result.value.reason, 'reader_failed')
        io = IO(wire.header(wire.MessageType.IPC_CAPTURE_OK, 0))
        self.assertEqual(transport.capture_ipc((), io, Clock()).reason, 'kscreen_profile_unverified')
        self.assertEqual(io.closed, 1)

    def test_ancillary_fds_are_closed_even_when_recv_returns_after_deadline(self):
        for late in (False, True):
            with self.subTest(late=late):
                io, clock = IO(), Clock()
                def recv(handle, size, remaining):
                    io.pending_fds = [7, 8]
                    if late:
                        clock.value = 5
                    return transport.Packet(b'', (7, 8, 7), True, True)
                io.recvmsg = recv
                result = transport.capture_ipc((), io, clock)
                self.assertFalse(result.ok)
                self.assertEqual(io.closed_fds, [7, 8])
                self.assertEqual(io.closed, 1)
                self.assertEqual(result.reason, 'source_timeout' if late else 'ipc_invalid')

    def test_one_exchange_partial_sends_half_close_eof_and_cleanup(self):
        io = IO()
        result = transport.capture_ipc((5,), io, Clock())
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.value.reason, 'owner_missing')
        self.assertEqual(io.sent, wire.encode_request(wire.Request((5,))).value)
        self.assertEqual(io.calls.count('connect'), 1)
        self.assertEqual(io.calls.count('peer'), 1)
        self.assertIn('shutdown', io.calls)
        self.assertEqual(io.closed, 1)
        self.assertNotIn('1000', repr(result))
        self.assertNotIn('99', repr(result))

    def test_endpoint_and_kernel_credentials_are_exact_and_closed(self):
        self.assertTrue(transport.endpoint_valid(endpoint(), 1000))
        for changes in ({'name': '../hybrid-display-reader-v1.sock'},
                        {'name': '/run/user/1000/hybrid-display-reader-v1.sock'},
                        {'uid': 0}, {'uid': True}, {'directory_mode': 0o777},
                        {'socket_mode': 0o666}, {'directory_symlink': True},
                        {'socket_symlink': True}, {'socket_id': [1, 3]},
                        {'family': 'inet'}, {'kind': 'datagram'}):
            self.assertFalse(transport.endpoint_valid(endpoint(**changes), 1000))
    def test_kernel_peer_uid_is_required_but_not_binary_authority(self):
        self.assertTrue(transport.credentials_valid((23, 1000, 1000), 1000))
        for credentials in ((True, 1000, 1000), (0, 1000, 1000), (23, 0, 0),
                            (23, 1001, 1000), (23, 1000, -1), [23, 1000, 1000], None):
            self.assertFalse(transport.credentials_valid(credentials, 1000))
