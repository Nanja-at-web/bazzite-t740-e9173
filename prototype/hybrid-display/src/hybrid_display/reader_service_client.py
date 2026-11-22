"""One-shot private stream algorithm over explicit trusted I/O primitives.

No native/default backend, socket path lookup, clock, connection or installation
is supplied here. Only temporary test fixtures implement the native primitives.
The fixed logical reader endpoint cannot be selected by a request. Peers on a
socket-activated listener may be the usermanager: UID is checked, but its PID
never becomes graphical-session, reader-binary or sandbox authority. Same-UID
attackers and actual syscall/deadline enforcement remain deployment blockers.

The injected I/O and clock are trusted code, not untrusted metadata. I/O must
honor each remaining timeout, bound native ancillary receipt to 32 FDs, retain
ancillary ownership per connection independently of returned Packet metadata,
and implement close_received(handle) as an idempotent drain of that registry,
including partial/native-decoding failure. close and close_received consume all
their owned resources even if reporting an error. No close-by-untrusted-number
occurs here. Lookup/connect must use one bound endpoint. No provider is sandboxed.
"""
from dataclasses import dataclass
from .reader_service_protocol import (Result, Request, integer, request_valid,
                                      inspect_header, HEADER_SIZE)
from .reader_service_policy import Budget, PeerFacts, peer_valid, peer_identity
from .reader_service_state import Client


@dataclass(frozen=True, slots=True, repr=False)
class Endpoint:
    name: str
    uid: int
    directory_mode: int
    socket_mode: int
    directory_id: tuple
    socket_id: tuple
    directory_symlink: bool = False
    socket_symlink: bool = False
    family: str = 'unix'
    kind: str = 'stream'


@dataclass(frozen=True, slots=True, repr=False)
class Packet:
    data: bytes
    fds: tuple = ()
    ancillary: bool = False
    truncated: bool = False


def endpoint_valid(value, uid):
    if type(value) is not Endpoint or not integer(uid, 1, 2147483647):
        return False
    try:
        return (type(value.name) is str and value.name == 'hybrid-display-reader-v1.sock'
                and type(value.uid) is int and value.uid == uid
                and type(value.directory_mode) is int and value.directory_mode == 0o700
                and type(value.socket_mode) is int and value.socket_mode == 0o600
                and identity_valid(value.directory_id) and identity_valid(value.socket_id)
                and value.directory_symlink is False and value.socket_symlink is False
                and type(value.family) is str and value.family == 'unix'
                and type(value.kind) is str and value.kind == 'stream')
    except AttributeError:
        return False


def identity_valid(value):
    return (type(value) is tuple and len(value) == 2
            and all(integer(item, 0, 2**64 - 1) for item in value))


def credentials_valid(value, uid):
    return (integer(uid, 1, 2147483647) and type(value) is tuple and len(value) == 3
            and integer(value[0], 1, 2147483647) and type(value[1]) is int
            and value[1] == uid and integer(value[2], 0, 2147483647))


class _Blocked(Exception):
    def __init__(self, reason):
        self.reason = reason


class _Session:
    def __init__(self, io):
        self.io = io
    def current(self):
        return self.io.session()


class _Exchange:
    def __init__(self, io, clock):
        self.io = io
        self.clock = clock
        self.budget = Budget(clock, 5)
        self.handle = None

    def check(self):
        checked = self.budget.check()
        if not checked.ok:
            raise _Blocked(checked.reason)
        return self.budget.deadline - self.budget.last

    def call(self, function, *args, timed=False):
        remaining = self.check()
        result = function(*args, remaining) if timed else function(*args)
        self.check()
        return result

    def receive(self, size):
        remaining = self.check()
        try:
            packet = self.io.recvmsg(self.handle, size, remaining)
        finally:
            # Ownership is tracked by the primitive, not by untrusted Packet
            # fields. Drain even on oversized/malformed metadata or late return.
            self.io.close_received(self.handle)
        self.check()
        if type(packet) is not Packet:
            raise _Blocked('ipc_invalid')
        fds = packet.fds
        if (type(fds) is not tuple or len(fds) > 32
                or any(not integer(fd, 0, 2147483647) for fd in fds)):
            raise _Blocked('ipc_invalid')
        if fds or packet.ancillary is not False or packet.truncated is not False:
            raise _Blocked('ipc_invalid')
        return packet

    def exchange(self, request):
        facts = self.call(self.io.session)
        if type(facts) is not PeerFacts:
            raise _Blocked('session_unverified')
        try:
            uid, session = facts.uid, facts.session_id
            if not peer_valid(facts, uid, session):
                raise _Blocked('session_unverified')
        except AttributeError:
            raise _Blocked('session_unverified') from None
        initial_session = peer_identity(facts)
        client = Client(self.clock, _Session(self.io), uid, session)
        encoded = client.request(request)
        if not encoded.ok:
            return encoded
        endpoint = self.call(self.io.lookup)
        if not endpoint_valid(endpoint, uid):
            raise _Blocked('source_not_allowed')
        # Assign ownership before the post-open clock check, including late open.
        self.check()
        self.handle = self.io.open_unix_stream()
        self.check()
        if self.handle is None:
            raise _Blocked('reader_failed')
        self.call(self.io.connect, self.handle, timed=True)
        credentials = self.call(self.io.peer, self.handle)
        if not credentials_valid(credentials, uid):
            raise _Blocked('session_unverified')
        connection_id = self.call(self.io.identity, self.handle)
        if not identity_valid(connection_id):
            raise _Blocked('reader_failed')

        def bound():
            current = self.call(self.io.session)
            if not peer_valid(current, uid, session):
                raise _Blocked('session_unverified')
            if peer_identity(current) != initial_session:
                raise _Blocked('inventory_changed')
            current_endpoint = self.call(self.io.lookup)
            if not endpoint_valid(current_endpoint, uid) or current_endpoint != endpoint:
                raise _Blocked('inventory_changed')
            identity = self.call(self.io.identity, self.handle)
            if not identity_valid(identity) or identity != connection_id:
                raise _Blocked('inventory_changed')

        bound()
        sent = 0
        while sent < len(encoded.value):
            count = self.call(self.io.send, self.handle, encoded.value[sent:], timed=True)
            if not integer(count, 1, len(encoded.value) - sent):
                raise _Blocked('ipc_invalid')
            sent += count
        self.call(self.io.shutdown_write, self.handle, timed=True)
        header, total, frame_size = b'', 0, None
        while True:
            bound()
            size = HEADER_SIZE - total if frame_size is None else min(4096, frame_size - total + 1)
            packet = self.receive(size)
            data = packet.data
            if type(data) is not bytes or len(data) > size:
                raise _Blocked('ipc_invalid')
            if not data:
                break
            total += len(data)
            if frame_size is None:
                header += data
                if len(header) == HEADER_SIZE:
                    checked = inspect_header(header, response=True)
                    if not checked.ok:
                        return checked
                    frame_size = HEADER_SIZE + checked.value
            received = client.feed(data)
            if not received.ok:
                return received
        bound()
        result = client.finish()
        self.check()
        return result


def capture_ipc(declared_client_pids, io=None, clock=None):
    """Exactly one attempt. No live default and no response before EOF/cleanup."""
    request = Request(declared_client_pids)
    if not request_valid(request):
        return Result(reason='input_invalid')
    if io is None or clock is None:
        return Result(reason='source_unavailable')
    attempt = _Exchange(io, clock)
    try:
        result = attempt.exchange(request)
    except _Blocked as blocked:
        result = Result(reason=blocked.reason)
    except TimeoutError:
        result = Result(reason='source_timeout')
    except PermissionError:
        result = Result(reason='source_denied')
    except (Exception, SystemExit):
        result = Result(reason='reader_failed')
    finally:
        if attempt.handle is not None:
            try:
                io.close(attempt.handle)
            except (Exception, SystemExit):
                result = Result(reason='reader_failed')
        checked = attempt.budget.check()
        if not checked.ok:
            result = Result(reason=checked.reason)
    return result
