"""Pure validation of synthetic private IPC records, never a host reader.

Success here describes only bounded, internally consistent bytes. It supplies
no live profile, session authority, snapshot, completeness or start permission.
The public response decoder still rejects IPC_CAPTURE_OK while the profile gate
is unavailable. No collector, preflight or transport is called.
"""
import json
import re
from .reader_service_protocol import Result, request_valid, MAX_RESPONSE, HEADER_SIZE
from .reader_service_policy import PeerFacts, peer_valid
from .parse_kscreen import decode_fixture, _parse, _size, _integer
from .parse_drm import edid_digest


class _Invalid(Exception):
    def __init__(self, reason='ipc_invalid'):
        self.reason = reason


class _Cursor:
    def __init__(self, body):
        self.body = body
        self.position = 0

    def take(self, size):
        if size > len(self.body) - self.position:
            raise _Invalid()
        start = self.position
        self.position += size
        return self.body[start:self.position]

    def number(self, size):
        return int.from_bytes(self.take(size), 'big')

    def record(self, kind, bus, subject, limit):
        if (self.number(1), self.number(1), self.number(4)) != (kind, bus, subject):
            raise _Invalid()
        size = self.number(4)
        if size > limit or size + 16 > 65536:
            raise _Invalid('ipc_limit')
        return self.take(size)


def _text(payload, pattern, limit):
    if len(payload) > limit:
        raise _Invalid()
    try:
        text = payload.decode('ascii')
    except UnicodeError:
        raise _Invalid() from None
    if re.fullmatch(pattern, text) is None:
        raise _Invalid()
    return text


def _u32(payload, low=0):
    if len(payload) != 4:
        raise _Invalid()
    value = int.from_bytes(payload, 'big')
    if not low <= value <= 2147483647:
        raise _Invalid()
    return value


def _projection(payload):
    try:
        raw = decode_fixture(payload, 65520)
        if type(raw) is not dict or set(raw) != {'outputs'}:
            raise ValueError
        allowed = {'id', 'name', 'connected', 'enabled', 'scale', 'rotation',
                   'clones', 'replicationSource', 'pos', 'size', 'modes', 'currentModeId'}
        if type(raw['outputs']) is not list:
            raise ValueError
        for output in raw['outputs']:
            if type(output) is not dict or set(output) - allowed:
                raise ValueError
            modes = output.get('modes', [])
            if type(modes) is not list:
                raise ValueError
            for mode in modes:
                if type(mode) is not dict or set(mode) != {'id', 'size', 'refreshRate'}:
                    raise ValueError
            if 'pos' in output:
                position = output['pos']
                if (type(position) is not dict or set(position) != {'x', 'y'}
                        or any(not _integer(position[key], -32768, 32767)
                               for key in ('x', 'y'))):
                    raise ValueError
            if 'size' in output and not _size(output['size']):
                raise ValueError
            if 'currentModeId' in output:
                current = output['currentModeId']
                if (type(current) is not str or not 1 <= len(current) <= 128
                        or current not in [mode['id'] for mode in modes]):
                    raise ValueError
        if json.dumps(raw, separators=(',', ':'), ensure_ascii=True).encode('ascii') != payload:
            raise ValueError
        parsed = _parse(raw)
        if not parsed.ok:
            raise ValueError
        return parsed.value
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise _Invalid('kscreen_schema_invalid') from None


def _capture(cursor, request, peer):
    count = cursor.number(2)
    if not 21 + len(request.client_pids) <= count <= 53:
        raise _Invalid()
    owners = []
    def owner(subject, uid):
        bus = 0 if subject == 0 else 1
        name = _text(cursor.record(3, bus, subject, 128), r':[0-9]+\.[0-9]+', 128)
        if _u32(cursor.record(4, bus, subject, 4)) != uid:
            raise _Invalid('owner_invalid')
        pid = _u32(cursor.record(5, bus, subject, 4), 1)
        owners.append((bus, name, pid))
    def session(subject):
        return _text(cursor.record(6, 0, subject, 256), r'/[A-Za-z0-9_/]{1,254}', 256)
    owner(0, 0)
    path = session(0)
    properties = [cursor.record(7, 0, index, 4096) for index in range(8)]
    if sum(map(len, properties)) > 4096:
        raise _Invalid('ipc_limit')
    user = properties[1]
    if len(user) < 6 or _u32(user[:4], 1) != peer.uid:
        raise _Invalid('session_unverified')
    if int.from_bytes(user[4:6], 'big') != len(user) - 6:
        raise _Invalid('session_unverified')
    _text(user[6:], r'/[A-Za-z0-9_/]{1,254}', 256)
    expected = (peer.session_id.encode('ascii'), user, b'wayland',
                peer.desktop.encode('ascii'), b'\x00', b'\x01', b'user', b'active')
    if tuple(properties) != expected:
        raise _Invalid('session_unverified')
    for subject in (1, 2):
        owner(subject, peer.uid)
        if session(subject) != path:
            raise _Invalid('session_unverified')
    if len({(bus, name) for bus, name, pid in owners}) != 3:
        raise _Invalid('owner_invalid')
    for index in range(len(request.client_pids)):
        if session(index + 3) != path:
            raise _Invalid('session_unverified')
    config = _projection(cursor.record(8, 1, 0, 65520))
    if count != 21 + len(request.client_pids) + len(config.outputs):
        raise _Invalid()
    digests = set()
    for output in config.outputs:
        payload = cursor.record(9, 1, output.output_id, 4096)
        try:
            digest = edid_digest(payload, not output.connected and not output.enabled)
        except ValueError:
            raise _Invalid('edid_invalid') from None
        if digest is not None:
            if digest in digests:
                raise _Invalid('edid_invalid')
            digests.add(digest)


def _decode(body, request, peer):
    if type(body) is not bytes or len(body) > MAX_RESPONSE - HEADER_SIZE:
        return Result(reason='ipc_limit' if type(body) is bytes else 'input_invalid')
    if not request_valid(request) or type(peer) is not PeerFacts:
        return Result(reason='input_invalid')
    try:
        if not peer_valid(peer, peer.uid, peer.session_id) or peer.pid in request.client_pids:
            return Result(reason='session_unverified')
    except AttributeError:
        return Result(reason='session_unverified')
    cursor = _Cursor(body)
    if cursor.number(1) != 4:
        raise _Invalid()
    for bus in (0, 1):
        if cursor.record(1, bus, 0, 1) != b'\x01':
            raise _Invalid()
        _text(cursor.record(2, bus, 0, 128), r':[0-9]+\.[0-9]+', 128)
    if cursor.number(1) != 2:
        raise _Invalid()
    first_start = cursor.position
    _capture(cursor, request, peer)
    first_end = cursor.position
    _capture(cursor, request, peer)
    if cursor.position != len(body):
        raise _Invalid()
    if body[first_start:first_end] != body[first_end:cursor.position]:
        raise _Invalid('inventory_changed')
    return Result(body)


def decode_capture(body, request, peer):
    """Validate supplied synthetic data atomically; never render input errors."""
    try:
        return _decode(body, request, peer)
    except _Invalid as invalid:
        return Result(reason=invalid.reason)
    except (Exception, SystemExit):
        return Result(reason='reader_failed')


def encode_capture(value, request, peer):
    """Private immutable bytes only; revalidate before producing any output."""
    return decode_capture(value, request, peer)
