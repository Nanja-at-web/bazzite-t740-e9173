"""Injected activation reference model, never a productive systemd entrypoint.

Metadata is an explicit activation-only projection, not the process environment.
No native descriptor discovery or operation is supplied by this module.

All providers are trusted injected code. take(3) is atomic: exception or any
non-valid Receipt means NO ownership transfer and no close/inspection is allowed.
A valid Receipt confirms exclusive ownership of that pinned descriptor and its
generation until release, including every operation after metadata inspection.
The future adapter must prevent numeric FD reuse/TOCTOU itself; a Receipt is not
cryptographic evidence or proof of systemd origin. release(receipt) consumes the
resource even if reporting an error. Accepted clients and ancillary FDs remain
in the adapter's independent, per-invocation registry and are drained by its
idempotent close_client/close_received primitives even on partial failure.

OWNED -> TRANSFERRED moves cleanup responsibility to the runtime bridge. Its
guard covers an exception before the runtime can run its own finally. Close is
terminal before calling trusted release, so no previous owner can close twice.
The shared four-second budget is cooperative, not native preemption. No host
runtime, kernel descriptor acquisition, installed units or sandbox is provided.
Same-UID and D-Bus method authority remain explicitly unresolved.
"""
from dataclasses import dataclass
from enum import Enum
from .reader_service_protocol import Result, integer
from . import reader_service_runtime as runtime
from .reader_service_policy import Budget


def validate_metadata(metadata, current_pid):
    if (not integer(current_pid, 1, 2147483647) or type(metadata) is not dict
            or len(metadata) != 2):
        return Result(reason='input_invalid')
    # Check key types before any dictionary lookup/hash/equality operation.
    for key in metadata:
        if type(key) is not str or key not in ('LISTEN_PID', 'LISTEN_FDS'):
            return Result(reason='input_invalid')
    pid, count = metadata['LISTEN_PID'], metadata['LISTEN_FDS']
    if (type(pid) is not str or not 1 <= len(pid) <= 10
            or not pid.isascii() or not pid.isdecimal() or pid[0] == '0'
            or type(count) is not str or count != '1' or int(pid) != current_pid):
        return Result(reason='input_invalid')
    return Result(0)


@dataclass(frozen=True, slots=True, repr=False)
class Receipt:
    descriptor: int
    generation: int


@dataclass(frozen=True, slots=True, repr=False)
class Descriptor:
    descriptor: int
    listener: object
    connected: bool


class Phase(Enum):
    UNOWNED = 'unowned'
    OWNED = 'owned'
    TRANSFERRED = 'transferred'
    CLOSED = 'closed'


def validate_unit_model(service, socket):
    """Selected synthetic requirements only, not a full unit/sandbox verifier.

    No artifact/ExecStart is generated, installed or made runnable. Native BOM,
    syscall policy, bus mediation and actual enforcement remain separate gates.
    """
    expected_service = (
        ('ExecStart', '/usr/libexec/hybrid-display-reader-v1'), ('Type', 'exec'),
        ('Restart', 'no'), ('NoNewPrivileges', 'yes'), ('PrivateNetwork', 'yes'),
        ('ProtectSystem', 'strict'), ('ProtectHome', 'yes'), ('PrivateDevices', 'yes'),
        ('RestrictAddressFamilies', 'AF_UNIX'), ('MemoryMax', '64M'), ('TasksMax', '1'),
        ('RuntimeMaxSec', '4s'), ('TimeoutStopSec', '100ms'),
        ('RootDirectory', '/usr/lib/hybrid-display-reader-v1/root'),
        ('StandardOutput', 'null'), ('StandardError', 'null'))
    expected_socket = (
        ('ListenStream', '%t/hybrid-display-reader-v1.sock'), ('SocketMode', '0600'),
        ('Accept', 'no'), ('Backlog', '1'), ('Service', 'hybrid-display-reader-v1.service'))
    for actual, expected in ((service, expected_service), (socket, expected_socket)):
        if type(actual) is not dict or len(actual) != len(expected):
            return Result(reason='input_invalid')
        allowed = tuple(key for key, value in expected)
        for key, value in actual.items():
            if (type(key) is not str or key not in allowed or type(value) is not str
                    or len(value) > 128):
                return Result(reason='input_invalid')
        if any(actual[key] != value for key, value in expected):
            return Result(reason='input_invalid')
    return Result(0)


def receipt_valid(value):
    return (type(value) is Receipt and type(value.descriptor) is int
            and value.descriptor == 3 and integer(value.generation, 1, 2**63 - 1))


def descriptor_valid(value):
    return (type(value) is Descriptor and type(value.descriptor) is int
            and value.descriptor == 3 and value.connected is False
            and runtime.listener_valid(value.listener))


class _Rejected(Exception):
    pass


def _remaining(budget):
    checked = budget.check()
    if not checked.ok:
        if checked.reason == 'source_timeout':
            raise TimeoutError()
        raise ValueError()
    return budget.deadline - budget.last


class Ownership:
    """Local ownership only; no descriptor acquisition or closing by number."""
    def __init__(self, adapter):
        self.adapter = adapter
        self.phase = Phase.UNOWNED
        self.receipt = None

    def adopt(self, receipt):
        if self.phase is not Phase.UNOWNED or not receipt_valid(receipt):
            return False
        self.receipt = receipt
        self.phase = Phase.OWNED
        return True

    def transfer(self):
        if self.phase is not Phase.OWNED:
            return False
        self.phase = Phase.TRANSFERRED
        return True

    def close(self, owner):
        if ((owner is Phase.OWNED or owner is Phase.TRANSFERRED)
                and self.phase is owner):
            self.phase = Phase.CLOSED
            self.adapter.release(self.receipt)


class _RuntimeIO:
    def __init__(self, ownership, descriptor, budget):
        self.ownership = ownership
        self.adapter = ownership.adapter
        self.client_closed = False
        self.descriptor = descriptor
        self.budget = budget

    def call(self, function, *args, remaining=None):
        limit = _remaining(self.budget)
        result = (function(*args, min(limit, remaining)) if remaining is not None
                  else function(*args))
        _remaining(self.budget)
        return result

    def activation(self):
        _remaining(self.budget)
        return (3,)

    def listener_metadata(self, handle):
        value = self.call(self.adapter.inspect, self.ownership.receipt)
        if (type(handle) is not int or handle != 3 or not descriptor_valid(value)
                or value != self.descriptor):
            return None
        return value.listener

    def accept(self, handle, remaining):
        return self.call(self.adapter.accept, self.ownership.receipt, remaining=remaining)

    def peer(self, handle):
        return self.call(self.adapter.peer, handle)

    def session(self, credentials):
        return self.call(self.adapter.session, credentials)

    def recvmsg(self, handle, size, remaining):
        return self.call(self.adapter.recvmsg, handle, size, remaining=remaining)

    def close_received(self, handle):
        return self.adapter.close_received(handle)

    def send(self, handle, data, remaining):
        return self.call(self.adapter.send, handle, data, remaining=remaining)

    def close_client(self):
        if not self.client_closed:
            self.client_closed = True
            self.adapter.close_client()

    def close_activation(self):
        self.ownership.close(Phase.TRANSFERRED)


def activate_once(metadata, current_pid, uid, session, adapter=None, clock=None, backend=None):
    checked = validate_metadata(metadata, current_pid)
    if not checked.ok:
        return checked
    if adapter is None or clock is None or backend is None:
        return Result(reason='source_unavailable')
    ownership = Ownership(adapter)
    bridge = None
    budget = Budget(clock, 4)
    try:
        _remaining(budget)
        receipt = adapter.take(3)
        if not ownership.adopt(receipt):
            raise _Rejected()
        _remaining(budget)
        descriptor = adapter.inspect(receipt)
        _remaining(budget)
        if not descriptor_valid(descriptor):
            raise _Rejected()
        bridge = _RuntimeIO(ownership, descriptor, budget)
        ownership.transfer()
        result = runtime.serve_once(uid, session, bridge, clock, backend)
    except _Rejected:
        result = Result(reason='source_not_allowed')
    except TimeoutError:
        result = Result(reason='source_timeout')
    except (Exception, SystemExit):
        result = Result(reason='reader_failed')
    finally:
        if ownership.phase is Phase.TRANSFERRED:
            # Runtime ownership guard covers exceptions before runtime cleanup.
            try:
                bridge.close_client()
            except (Exception, SystemExit):
                result = Result(reason='reader_failed')
            try:
                bridge.close_activation()
            except (Exception, SystemExit):
                result = Result(reason='reader_failed')
        try:
            ownership.close(Phase.OWNED)
        except (Exception, SystemExit):
            result = Result(reason='reader_failed')
        checked = budget.check()
        if not checked.ok:
            result = Result(reason=checked.reason)
    return result
