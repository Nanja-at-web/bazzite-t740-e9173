"""Session validation over detached values; no session or bus access."""
import re
from .host_reader import (EnvKey, OwnIdentity, ParseResult, SessionRaw,
                          SessionData, immutable)


def valid_identity(own):
    return (type(own) is OwnIdentity and immutable(own)
            and type(own.uid) is int and 1 <= own.uid <= 2147483647
            and type(own.euid) is int and own.euid == own.uid
            and type(own.pid) is int and 1 <= own.pid <= 2147483647
            and own.privileged is False)


def parse_session(raw, own):
    if (not valid_identity(own) or type(raw) is not SessionRaw
            or not immutable(raw)):
        return ParseResult(reasons=('session_unverified',))
    try:
        return _parse(raw, own)
    except (ValueError, KeyError, TypeError, AttributeError):
        return ParseResult(reasons=('session_unverified',))


def _parse(raw, own, require_owners=True):
    if type(raw.env) is not tuple or len(raw.env) != 5:
        return ParseResult(reasons=('session_context_invalid',))
    env = {}
    limits = {EnvKey.SESSION_ID: 32, EnvKey.SESSION_TYPE: 16,
              EnvKey.DESKTOP: 16, EnvKey.RUNTIME: 64, EnvKey.BUS: 96}
    for item in raw.env:
        if (type(item) is not tuple or len(item) != 2
                or type(item[0]) is not EnvKey or type(item[1]) is not bytes):
            return ParseResult(reasons=('session_context_invalid',))
        key, value = item
        if key in env or len(value) > limits[key]:
            return ParseResult(reasons=('session_context_invalid',))
        env[key] = value.decode('ascii')
    if re.fullmatch(r'[A-Za-z0-9]{1,32}', env[EnvKey.SESSION_ID]) is None:
        return ParseResult(reasons=('session_context_invalid',))
    if (env[EnvKey.SESSION_TYPE] != 'wayland'
            or env[EnvKey.DESKTOP] not in ('KDE', 'plasma', 'Plasma')
            or env[EnvKey.RUNTIME] != '/run/user/' + str(own.uid)):
        return ParseResult(reasons=('session_context_invalid',))
    if env[EnvKey.BUS] != 'unix:path=/run/user/' + str(own.uid) + '/bus':
        return ParseResult(reasons=('session_bus_invalid',))
    if type(raw.session) is not tuple or len(raw.session) != 8:
        return ParseResult(reasons=('session_unverified',))
    session = {}
    for item in raw.session:
        if (type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                or item[0] in session):
            return ParseResult(reasons=('session_unverified',))
        session[item[0]] = item[1]
    if set(session) != {'Id', 'User', 'Type', 'Desktop', 'Remote', 'Active', 'Class', 'State'}:
        return ParseResult(reasons=('session_unverified',))
    user = session['User']
    if (type(user) is not tuple or len(user) != 2 or type(user[0]) is not int
            or user[0] != own.uid or type(user[1]) is not str
            or re.fullmatch(r'/[A-Za-z0-9_/]{1,254}', user[1]) is None):
        return ParseResult(reasons=('session_unverified',))
    expected = {'Id': env[EnvKey.SESSION_ID], 'Type': 'wayland',
                'Desktop': env[EnvKey.DESKTOP], 'Class': 'user', 'State': 'active'}
    if any(type(session[key]) is not str or session[key] != value
           for key, value in expected.items()):
        return ParseResult(reasons=('session_unverified',))
    if session['Remote'] is not False or session['Active'] is not True:
        return ParseResult(reasons=('session_unverified',))
    if not require_owners and raw.owners == ():
        return ParseResult(SessionData(session['Id'], session['Desktop'], ()))
    if type(raw.owners) is not tuple or len(raw.owners) != 2:
        return ParseResult(reasons=('session_unverified',))
    labels, names = set(), set()
    for owner in raw.owners:
        if type(owner) is not tuple or len(owner) != 5:
            return ParseResult(reasons=('owner_invalid',))
        label, name, uid, pid, session_id = owner
        if (type(label) is not str or label not in ('kwin', 'kscreen')
                or label in labels or type(name) is not str
                or len(name) > 128 or re.fullmatch(r':[0-9]+\.[0-9]+', name) is None
                or name in names or type(uid) is not int or uid != own.uid
                or type(pid) is not int or not 1 <= pid <= 2147483647
                or type(session_id) is not str or session_id != session['Id']):
            return ParseResult(reasons=('session_unverified',))
        labels.add(label)
        names.add(name)
    return ParseResult(SessionData(session['Id'], session['Desktop'],
                                   tuple(sorted(raw.owners))))


def parse_process(stat, status, pid, uid):
    """Project comm/starttime and Uid from one bounded synthetic proc record."""
    rejected = ParseResult(reasons=('process_identity_unverified',))
    if (type(stat) is not bytes or len(stat) > 4096 or type(status) is not bytes
            or len(status) > 8192 or type(pid) is not int or not 1 <= pid <= 2147483647
            or type(uid) is not int or not 1 <= uid <= 2147483647):
        return rejected
    try:
        text = stat.decode('ascii')
        status_text = status.decode('ascii')
        if not text.endswith('\n') or text.count('\n') != 1 or '\0' in text:
            return rejected
        prefix = str(pid) + ' ('
        end = text.rfind(') ')
        if not text.startswith(prefix) or end < len(prefix):
            return rejected
        comm = text[len(prefix):end]
        tail = text[end + 2:-1].split(' ')
        if (not 1 <= len(comm) <= 128 or any(ord(char) < 32 for char in comm)
                or len(tail) != 50 or len(tail[0]) != 1 or tail[0] not in 'RSDZTWtXxKWPIN'
                or any(re.fullmatch(r'-?[0-9]{1,20}', part) is None for part in tail[1:])
                or re.fullmatch(r'[0-9]{1,10}', tail[19]) is None):
            return rejected
        starttime = int(tail[19])
        if not 1 <= starttime <= 2147483647 or '\0' in status_text:
            return rejected
        uid_lines = [line for line in status_text.splitlines() if line.startswith('Uid:')]
        if len(uid_lines) != 1:
            return rejected
        parts = uid_lines[0][4:].split()
        if (len(parts) != 4 or any(re.fullmatch(r'[0-9]{1,10}', part) is None for part in parts)
                or any(int(part) != uid for part in parts)):
            return rejected
        return ParseResult((comm, starttime))
    except (ValueError, IndexError):
        return rejected


def parse_session_context(raw, own):
    """Validate own local context before any GUI-owner lookup is attempted."""
    if (not valid_identity(own) or type(raw) is not SessionRaw or not immutable(raw)
            or type(raw.owners) is not tuple or raw.owners != ()):
        return ParseResult(reasons=('session_unverified',))
    try:
        return _parse(raw, own, require_owners=False)
    except (ValueError, KeyError, TypeError, AttributeError):
        return ParseResult(reasons=('session_unverified',))
