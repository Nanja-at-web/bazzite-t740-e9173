"""Injected peer and monotonic-time policy. No identity acquisition or timers."""
from dataclasses import dataclass, fields
from math import isfinite
import re
from .reader_service_protocol import Result, integer

@dataclass(frozen=True, slots=True, repr=False)
class PeerFacts:
    uid: int
    euid: int
    pid: int
    starttime: int
    session_id: str
    session_uid: int
    session_type: str | None = None
    desktop: str | None = None
    remote: bool | None = None
    active: bool | None = None
    session_class: str | None = None
    state: str | None = None
    verified: bool = False

    def __repr__(self):
        return '<PeerFacts>'

    def __post_init__(self):
        for item in fields(PeerFacts):
            value = getattr(self, item.name)
            kind = type(value)
            if kind is not str and kind is not int and kind is not bool:
                object.__setattr__(self, item.name, None)

@dataclass(frozen=True, slots=True)
class Limits:
    header: float = 0.100
    request: float = 0.250
    response: float = 0.250
    service: float = 4.0
    client: float = 5.0


    def __post_init__(self):
        for item, expected in zip(fields(self), (.100, .250, .250, 4.0, 5.0)):
            value = getattr(self, item.name)
            if type(value) is not float or value != expected:
                raise ValueError('input_invalid')


def peer_valid(value, uid, session):
    if (type(value) is not PeerFacts or not integer(uid, 1, 2147483647)
            or type(session) is not str or re.fullmatch(r'[A-Za-z0-9]{1,32}', session) is None):
        return False
    try:
        return (integer(value.uid, 1, 2147483647) and value.uid == uid
            and integer(value.euid, 1, 2147483647) and value.euid == uid
            and integer(value.pid, 1, 2147483647)
            and integer(value.starttime, 1, 9223372036854775807)
            and type(value.session_id) is str and len(value.session_id) <= 32
            and value.session_id == session
            and integer(value.session_uid, 1, 2147483647) and value.session_uid == uid
            and type(value.session_type) is str and value.session_type == 'wayland'
            and type(value.desktop) is str and value.desktop in ('KDE', 'plasma', 'Plasma')
            and value.remote is False and value.active is True
            and type(value.session_class) is str and value.session_class == 'user'
            and type(value.state) is str and value.state == 'active'
            and value.verified is True)
    except AttributeError:
        return False


def peer_identity(value):
    # Call only after peer_valid. The detached exact scalars cannot alias input.
    return tuple(getattr(value, item.name) for item in fields(PeerFacts))


class Budget:
    """Cooperative checks over a trusted clock, not a native interruption proof."""
    def __init__(self, clock, seconds):
        self.clock = clock
        self._duration = seconds
        self.started = None
        self.last = None
        self._failure = ''
        if ((type(seconds) is not int and type(seconds) is not float)
                or seconds not in (4, 5)):
            self._failure = 'reader_failed'

    @property
    def deadline(self):
        return None if self.started is None else self.started + self._duration

    def check(self, deadline=None):
        if self._failure:
            return Result(reason=self._failure)
        try:
            value = self.clock.now()
            if ((type(value) is not int and type(value) is not float)
                    or not 0 <= value <= 1e12 or not isfinite(value)
                    or self.last is not None and value < self.last):
                self._failure = 'reader_failed'
            else:
                if self.started is None:
                    self.started = value
                self.last = value
                if deadline is not None and ((type(deadline) is not int and type(deadline) is not float)
                        or not 0 <= deadline <= 1e12 + 5 or not isfinite(deadline)):
                    self._failure = 'reader_failed'
                elif value >= self.deadline or deadline is not None and value >= deadline:
                    self._failure = 'source_timeout'
        except (Exception, SystemExit):
            self._failure = 'reader_failed'
        return Result(reason=self._failure) if self._failure else Result(0)
