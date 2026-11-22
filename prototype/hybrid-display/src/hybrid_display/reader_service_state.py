"""Pure one-shot event machines. No connects, reads, writes or native metadata.

The injected clock, peer provider and reader are trusted dependencies. Checks
around callbacks are cooperative, never a bound on a blocking native call.
Malicious same-UID processes remain an open deployment blocker; peer/session
receipts do not solve that authority problem and are neither cryptographic
authentication nor binary attestation.
"""
from enum import Enum
from .reader_service_protocol import (Result, Response, encode_request,
    encode_response, response_valid)
from .reader_service_policy import Budget, peer_valid, peer_identity
from .reader_service_stream import Decoder

class Phase(Enum):
    NEW = 'new'
    ENTRY = 'entry'
    REQUEST = 'request'
    READING = 'reading'
    RESPONSE = 'response'
    DONE = 'done'
    FAILED = 'failed'

class _Attempt:
    def __init__(self, clock, peers, uid, session, seconds):
        self._budget = Budget(clock, seconds)
        self._peers = peers
        self._uid = uid
        self._session = session
        self._identity = None
        self._phase = Phase.NEW
        self._failure = ''
        self._checking = False
        self._decoder = None
        self._pending = None

    @property
    def phase(self):
        return self._phase

    def _fail(self, reason):
        if not self._failure:
            self._failure = reason
        self._phase = Phase.FAILED
        self._pending = None
        self._decoder = None
        return Result(reason=self._failure)

    def _guard(self, deadline=None):
        if self._checking:
            return self._fail('reader_failed')
        self._checking = True
        try:
            return self._guard_inner(deadline)
        finally:
            self._checking = False

    def _guard_inner(self, deadline):
        if self._failure:
            return self._fail(self._failure)
        if self._failure:
            return self._fail(self._failure)
        checked = self._budget.check(deadline)
        if not checked.ok:
            return self._fail(checked.reason)
        try:
            peer = self._peers.current()
        except (Exception, SystemExit):
            return self._fail('session_unverified')
        if self._failure:
            return self._fail(self._failure)
        checked = self._budget.check(deadline)
        if not checked.ok:
            return self._fail(checked.reason)
        if not peer_valid(peer, self._uid, self._session):
            return self._fail('session_unverified')
        identity = peer_identity(peer)
        if self._identity is not None and self._identity != identity:
            return self._fail('inventory_changed')
        self._identity = identity
        return Result(0)

    def feed(self, chunk):
        if self._phase is not Phase.REQUEST:
            return self._fail('ipc_invalid')
        checked = self._guard()
        if not checked.ok:
            return checked
        result = self._decoder.feed(chunk)
        if not result.ok:
            return self._fail(result.reason)
        return self._guard()

class Service(_Attempt):
    """start = process entry, accept = accepted connection, finish = request EOF.

    emit returns at most one already validated complete frame to an in-memory
    sink. It is not an OS send or a claim of atomic SOCK_STREAM writes. A future
    native sender must enforce remaining send time and closure independently.
    """
    def __init__(self, clock, peers, reader, uid, session):
        super().__init__(clock, peers, uid, session, 4)
        self._reader = reader
        self._send_deadline = None

    def start(self):
        if self._phase is not Phase.NEW:
            return self._fail('ipc_invalid')
        checked = self._budget.check()
        if not checked.ok:
            return self._fail(checked.reason)
        self._phase = Phase.ENTRY
        return Result(0)

    def accept(self):
        if self._phase is not Phase.ENTRY:
            return self._fail('ipc_invalid')
        # Accept time precedes identity callbacks; they cannot extend the request.
        checked = self._budget.check()
        if not checked.ok:
            return self._fail(checked.reason)
        self._decoder = Decoder(self._budget)
        checked = self._guard()
        if not checked.ok:
            return checked
        self._phase = Phase.REQUEST
        return Result(0)

    def finish(self):
        if self._phase is not Phase.REQUEST:
            return self._fail('ipc_invalid')
        checked = self._guard()
        if not checked.ok:
            return checked
        decoded = self._decoder.finish()
        if not decoded.ok:
            return self._fail(decoded.reason)
        if self._identity[2] in decoded.value.client_pids:
            return self._fail('session_unverified')
        checked = self._guard()
        if not checked.ok:
            return checked
        self._phase = Phase.READING
        try:
            response = self._reader.capture(decoded.value)
        except (Exception, SystemExit):
            response = Response('reader_failed')
        checked = self._guard()
        if not checked.ok:
            return checked
        if not response_valid(response):
            response = Response('reader_failed')
        encoded = encode_response(response)
        checked = self._guard()
        if not checked.ok:
            return checked
        if not encoded.ok:
            return self._fail(encoded.reason)
        self._pending = encoded.value
        self._decoder = None
        self._send_deadline = self._budget.last + .250
        self._phase = Phase.RESPONSE
        return Result(0)

    def emit(self):
        if self._phase is not Phase.RESPONSE:
            return self._fail('ipc_invalid')
        checked = self._guard(self._send_deadline)
        if not checked.ok:
            return checked
        frame = self._pending
        self._pending = None
        self._phase = Phase.DONE
        return Result(frame)

class Client(_Attempt):
    """Pure client framing. peers supplies the *local graphical requester*.

    No remote SO_PEERCRED is acquired here. The future socket client must check
    the fixed installed listener's UID/PID/starttime separately; a usermanager
    listener PID must never be claimed as a graphical-session Reader binary.
    """
    def __init__(self, clock, peers, uid, session):
        super().__init__(clock, peers, uid, session, 5)

    def request(self, value):
        if self._phase is not Phase.NEW:
            return self._fail('ipc_invalid')
        checked = self._guard()
        if not checked.ok:
            return checked
        encoded = encode_request(value)
        if not encoded.ok:
            return self._fail(encoded.reason)
        if self._identity[2] in value.client_pids:
            return self._fail('session_unverified')
        checked = self._guard()
        if not checked.ok:
            return checked
        self._decoder = Decoder(self._budget, response=True)
        self._phase = Phase.REQUEST
        return encoded

    def finish(self):
        if self._phase is not Phase.REQUEST:
            return self._fail('ipc_invalid')
        checked = self._guard()
        if not checked.ok:
            return checked
        result = self._decoder.finish()
        if not result.ok:
            return self._fail(result.reason)
        checked = self._guard()
        if not checked.ok:
            return checked
        self._decoder = None
        self._phase = Phase.DONE
        return result
