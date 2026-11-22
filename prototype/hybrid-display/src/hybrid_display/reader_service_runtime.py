"""Non-installed, one-client orchestration over explicitly trusted primitives.

No native/default provider, endpoint creation, activation discovery or host I/O.
activation() transfers an I/O-owned registry, not authority to close arbitrary
returned numbers. close_activation() drains all transferred listener resources;
close_client() drains any accepted connection even if accept raised after taking
ownership. close_received(handle) drains per-connection ancillary ownership in
a finally path, independently of malformed Packet metadata. These primitives
must consume their resources even if reporting an error and be idempotent.
Native implementations must bound ancillary receipt (32 FDs), use CLOEXEC and
honor the supplied remaining timeout; cooperative checks cannot interrupt an
opaque blocking primitive or backend. None is provided by this module.

peer() reads kernel credentials once. session(credentials) is a trusted injected
receipt provider bound to that PID/UID, not acquisition from the Reader's own
environment. Metadata providers, clock, backend and I/O are trusted code; only
their returned data is validated callback-free. Same-UID binary/method authority,
the native runtime, actual systemd transfer and sandbox enforcement remain open.
Success means only that a fixed BLOCKED response was completely written and
owned resources released, never a host snapshot or display/start permission.
"""
from dataclasses import dataclass
from .reader_service_protocol import Result, integer, HEADER_SIZE, inspect_header
from .reader_service_state import Service
from .reader_service_client import credentials_valid, identity_valid, Packet
from .reader_service_policy import peer_valid, Budget


@dataclass(frozen=True, slots=True, repr=False)
class Listener:
    family: str
    kind: str
    listening: bool
    closed: bool
    nonblocking: bool
    cloexec: bool
    identity: tuple


def listener_valid(value):
    if type(value) is not Listener:
        return False
    return (type(value.family) is str and value.family == 'unix'
            and type(value.kind) is str and value.kind == 'stream'
            and value.listening is True and value.closed is False
            and value.nonblocking is True and value.cloexec is True
            and identity_valid(value.identity))


class _Blocked(Exception):
    def __init__(self, reason):
        self.reason = reason


class _Attempt:
    def __init__(self, io, clock):
        self.io = io
        self.budget = Budget(clock, 4)

    def check(self, deadline=None):
        checked = self.budget.check(deadline)
        if not checked.ok:
            raise _Blocked(checked.reason)
        return min(self.budget.deadline, deadline if deadline is not None
                   else self.budget.deadline) - self.budget.last

    def call(self, function, *args, deadline=None, timed=False):
        remaining = self.check(deadline)
        result = function(*args, remaining) if timed else function(*args)
        self.check(deadline)
        return result

    def receive(self, handle, size, deadline):
        remaining = self.check(deadline)
        try:
            packet = self.io.recvmsg(handle, size, remaining)
        finally:
            self.io.close_received(handle)
        self.check(deadline)
        if type(packet) is not Packet:
            raise _Blocked('ipc_invalid')
        if (type(packet.fds) is not tuple or len(packet.fds) > 32
                or packet.fds or packet.ancillary is not False or packet.truncated is not False
                or type(packet.data) is not bytes or len(packet.data) > size):
            raise _Blocked('ipc_invalid')
        return packet.data


def _run(uid, session, io, clock, backend, attempt):
    response_deadline = None
    class Reader:
        def capture(self, request):
            nonlocal response_deadline
            try:
                return backend.capture(request)
            finally:
                # Begin no later than response encoding/readiness, including
                # exception-to-BLOCKED conversion. Never reset this on emit.
                attempt.check()
                response_deadline = attempt.budget.last + .250
    class Peers:
        def current(self):
            facts = attempt.call(io.session, credentials)
            if not peer_valid(facts, uid, session) or facts.pid != credentials[0]:
                return None
            return facts
    service = Service(clock, Peers(), Reader(), uid, session)
    checked = service.start()
    if not checked.ok:
        return checked
    fds = attempt.call(io.activation)
    if type(fds) is not tuple or len(fds) != 1 or not integer(fds[0], 0, 2147483647):
        return Result(reason='source_not_allowed')
    listener = fds[0]
    metadata = attempt.call(io.listener_metadata, listener)
    if not listener_valid(metadata):
        return Result(reason='source_not_allowed')
    remaining = attempt.check()
    client = io.accept(listener, remaining)
    attempt.check()
    accepted = attempt.budget.last
    if not integer(client, 0, 2147483647) or client == listener:
        return Result(reason='source_not_allowed')
    # No intervening I/O between valid accept and the kernel-credential read.
    credentials = attempt.call(io.peer, client, deadline=accepted + .100)
    if not credentials_valid(credentials, uid):
        return Result(reason='session_unverified')
    checked = service.accept()
    if not checked.ok:
        return checked
    current = attempt.call(io.listener_metadata, listener)
    if not listener_valid(current) or current != metadata:
        return Result(reason='source_not_allowed')
    header, total, frame_size = b'', 0, None
    while True:
        deadline = accepted + (.100 if frame_size is None else .250)
        size = HEADER_SIZE - total if frame_size is None else frame_size - total + 1
        data = attempt.receive(client, size, deadline)
        if not data:
            break
        total += len(data)
        if frame_size is None:
            header += data
            if len(header) == HEADER_SIZE:
                checked = inspect_header(header)
                if not checked.ok:
                    return checked
                frame_size = HEADER_SIZE + checked.value
        checked = service.feed(data)
        if not checked.ok:
            return checked
    attempt.check(accepted + .250)
    checked = service.finish()
    attempt.check()
    if not checked.ok:
        return checked
    if response_deadline is None:
        return Result(reason='reader_failed')
    attempt.check(response_deadline)
    encoded = service.emit()
    if not encoded.ok:
        return encoded
    frame = encoded.value
    sent = 0
    while sent < len(frame):
        count = attempt.call(io.send, client, frame[sent:], deadline=response_deadline, timed=True)
        if not integer(count, 1, len(frame) - sent):
            return Result(reason='ipc_invalid')
        sent += count
    return Result(0)


def serve_once(uid, session, io=None, clock=None, backend=None):
    if io is None or clock is None or backend is None:
        return Result(reason='source_unavailable')
    attempt = _Attempt(io, clock)
    try:
        attempt.check()
        result = _run(uid, session, io, clock, backend, attempt)
    except _Blocked as blocked:
        result = Result(reason=blocked.reason)
    except TimeoutError:
        result = Result(reason='source_timeout')
    except (Exception, SystemExit):
        result = Result(reason='reader_failed')
    finally:
        for cleanup in ('close_client', 'close_activation'):
            try:
                getattr(io, cleanup)()
            except (Exception, SystemExit):
                result = Result(reason='reader_failed')
        checked = attempt.budget.check()
        if not checked.ok:
            result = Result(reason=checked.reason)
    return result
