"""Pure injected transport harness only. No native Linux backend is present."""
from dataclasses import dataclass, fields
from enum import Enum
from typing import Protocol
from math import isfinite
from .host_reader import (ReadResult, EnvKey, SourceKey, QueryKey, FileSource, BusQuery, immutable)
from .reader_policy import validate_source, validate_query, Resolution, _context_valid

class DeadlineProfile(Enum):
    UNKNOWN = 'unknown'
    BLOCKED = 'blocked'
    SYNTHETIC_ONLY = 'synthetic-only'

@dataclass(frozen=True, slots=True, repr=False)
class FrameHeader:
    body_size: int
    reply_serial: int = 1
    fd_count: int = 0
    unexpected: bool = False

class ReaderTransport(Protocol):
    def open_readonly(self, source): ...
    def stat_handle(self, handle): ...
    def read_chunk(self, handle, size): ...
    def close_handle(self, handle): ...
    def begin_query(self, query): ...
    def next_header(self, handle): ...
    def read_body(self, handle, size): ...

class _Rejected(Exception):
    """Internal fixed-code control flow; no input or adapter exception text."""
    def __init__(self, code):
        self.code = code


FILE_LIMITS = {SourceKey.DRM_STATUS: 16, SourceKey.DRM_ENABLED: 16,
               SourceKey.DRM_EDID: 4096, SourceKey.DRM_DEVICE_LINK: 1024,
               SourceKey.PROCESS_STAT: 4096, SourceKey.PROCESS_STATUS: 8192}
ENV_LIMITS = {EnvKey.SESSION_ID: 32, EnvKey.SESSION_TYPE: 16,
              EnvKey.DESKTOP: 16, EnvKey.RUNTIME: 64, EnvKey.BUS: 96}
QUERY_LIMITS = {QueryKey.AUTH: (4096, 0.250), QueryKey.HELLO: (128, 0.250),
    QueryKey.OWNER: (128, 0.250), QueryKey.OWNER_UID: (128, 0.250),
    QueryKey.OWNER_PID: (128, 0.250), QueryKey.SESSION_BY_PID: (256, 0.250),
    QueryKey.SESSION_PROPERTY: (4096, 0.500), QueryKey.CONFIG: (65536, 0.500),
    QueryKey.EDID: (4096, 0.100)}


class LinuxReader:
    """One bounded attempt over an injected transport, never a native backend.

    UNKNOWN/BLOCKED deadline profiles forbid transport activity. SYNTHETIC_ONLY
    models deterministic in-memory operations and is not a kernel deadline proof.
    The injected transport and clock are trusted dependencies, not sandboxed code.
    Constructor performs no transport/clock operation; there are no background jobs.
    """
    def __init__(self, transport, clock, deadline_profile=DeadlineProfile.UNKNOWN,
                 context=None, allowed_pids=()):
        self.transport = transport
        self.clock = clock
        self.deadline_profile = deadline_profile
        self.context = context
        self.allowed_pids = allowed_pids
        self._started = None
        self._last = None
        self._bytes = 0
        self._blocked = None
        self._hello = set()
        self._auth = set()

    @property
    def bytes_used(self):
        return self._bytes

    def _check(self, deadline=None):
        value = self.clock.now()
        if ((type(value) is not int and type(value) is not float)
                or not 0 <= value <= 1e12 or not isfinite(value)
                or self._last is not None and value < self._last):
            raise _Rejected('reader_failed')
        if self._started is None:
            self._started = value
        self._last = value
        if value >= self._started + 5 or deadline is not None and value >= deadline:
            raise _Rejected('source_timeout')
        return value

    def _call(self, method, deadline, *args):
        self._check(deadline)
        value = method(*args)
        self._check(deadline)
        return value

    def _charge(self, size):
        if self._bytes + size > 262144:
            raise _Rejected('source_limit')
        self._bytes += size

    def _ready(self):
        if self._blocked is not None:
            raise _Rejected(self._blocked)
        if self.deadline_profile is not DeadlineProfile.SYNTHETIC_ONLY:
            raise _Rejected('reader_deadline_unverified')
        self._check()

    def _run(self, operation):
        try:
            self._ready()
            return ReadResult(operation())
        except _Rejected as rejected:
            self._blocked = rejected.code
        except (Exception, SystemExit):
            self._blocked = 'reader_failed'
        return ReadResult(reasons=(self._blocked,))

    def read_env(self, key):
        if type(key) is not EnvKey:
            return ReadResult(reasons=('source_not_allowed',))
        def operation():
            deadline = self._check() + 0.050
            payload = self._call(self.transport.environment_value, deadline, key, ENV_LIMITS[key] + 1)
            if payload is None:
                raise _Rejected('source_unavailable')
            if type(payload) is not bytes:
                raise _Rejected('source_type_invalid')
            if len(payload) > ENV_LIMITS[key]:
                raise _Rejected('source_limit')
            self._charge(len(payload))
            return payload
        return self._run(operation)

    def read_file(self, source):
        if (type(source) is FileSource and immutable(source)
                and (source.key is SourceKey.PROCESS_STAT or source.key is SourceKey.PROCESS_STATUS)
                and not _context_valid(self.context)):
            return ReadResult(reasons=('process_identity_unverified',))
        checked = validate_source(source, allowed_pids=self.allowed_pids)
        if not checked.ok:
            return ReadResult(reasons=checked.reasons)
        def operation():
            limit = FILE_LIMITS[source.key]
            deadline = self._check() + 0.100
            if 262144 - self._bytes < limit + 1:
                raise _Rejected('source_limit')
            self._check(deadline)
            handle = self.transport.open_readonly(source)
            try:
                self._check(deadline)
                before = self._call(self.transport.stat_handle, deadline, handle)
                source_receipt = validate_source(source, before, self.allowed_pids)
                if not source_receipt.ok:
                    raise _Rejected('source_not_allowed')
                if source.key is SourceKey.PROCESS_STAT or source.key is SourceKey.PROCESS_STATUS:
                    if self.context is None or before.uid != self.context.uid:
                        raise _Rejected('process_identity_unverified')
                before_values = tuple(getattr(before, item.name) for item in fields(Resolution))
                chunks, length = [], 0
                while True:
                    requested = min(4096, limit + 1 - length)
                    chunk = self._call(self.transport.read_chunk, deadline, handle, requested)
                    if type(chunk) is not bytes:
                        raise _Rejected('source_type_invalid')
                    if len(chunk) > requested:
                        raise _Rejected('source_limit')
                    self._charge(len(chunk))
                    length += len(chunk)
                    if length > limit:
                        raise _Rejected('source_limit')
                    if not chunk:
                        break
                    chunks.append(chunk)
                after = self._call(self.transport.stat_handle, deadline, handle)
                if (not validate_source(source, after, self.allowed_pids).ok
                        or before_values != tuple(getattr(after, item.name) for item in fields(Resolution))):
                    raise _Rejected('inventory_changed')
                payload = b''.join(chunks)
                if (source.key is SourceKey.DRM_DEVICE_LINK
                        and payload != source_receipt.value[4].encode('ascii')):
                    raise _Rejected('drm_device_invalid')
                return payload
            finally:
                self.transport.close_handle(handle)
                self._check(deadline)
        return self._run(operation)

    def query(self, query):
        checked = validate_query(query, self.context)
        if not checked.ok:
            return ReadResult(reasons=checked.reasons)
        def operation():
            limit, seconds = QUERY_LIMITS[query.key]
            deadline = self._check() + seconds
            if query.key is QueryKey.AUTH and query.bus in self._auth:
                raise _Rejected('ipc_invalid')
            if (query.key is QueryKey.HELLO
                    and (query.bus in self._hello or query.bus not in self._auth)):
                raise _Rejected('ipc_invalid')
            self._check(deadline)
            handle = self.transport.begin_query(query)
            try:
                self._check(deadline)
                unexpected, unexpected_bytes = 0, 0
                while True:
                    header = self._call(self.transport.next_header, deadline, handle)
                    if type(header) is not FrameHeader:
                        raise _Rejected('ipc_invalid')
                    try:
                        values = (header.body_size, header.reply_serial, header.fd_count, header.unexpected)
                    except AttributeError:
                        raise _Rejected('ipc_invalid') from None
                    if (not immutable(values) or type(header.body_size) is not int
                            or header.body_size < 0 or type(header.reply_serial) is not int
                            or type(header.fd_count) is not int or header.fd_count != 0
                            or type(header.unexpected) is not bool):
                        raise _Rejected('ipc_invalid')
                    if header.body_size + 16 > 65536:
                        raise _Rejected('ipc_limit')
                    if header.unexpected:
                        unexpected += 1
                        unexpected_bytes += header.body_size + 16
                        if unexpected > 32 or unexpected_bytes > 32768:
                            raise _Rejected('ipc_limit')
                    elif header.reply_serial != 1:
                        raise _Rejected('ipc_invalid')
                    if not header.unexpected and header.body_size > limit:
                        raise _Rejected('ipc_limit')
                    if self._bytes + header.body_size + 16 > 262144:
                        raise _Rejected('source_limit')
                    self._charge(16)
                    body = self._call(self.transport.read_body, deadline, handle, header.body_size)
                    if type(body) is not bytes or len(body) != header.body_size:
                        raise _Rejected('ipc_invalid')
                    self._charge(len(body))
                    if not header.unexpected:
                        if query.key is QueryKey.AUTH:
                            if body != b'"OK"':
                                raise _Rejected('ipc_invalid')
                            self._auth.add(query.bus)
                        if query.key is QueryKey.HELLO:
                            self._hello.add(query.bus)
                        return body
            finally:
                self.transport.close_handle(handle)
                self._check(deadline)
        return self._run(operation)


class MemoryTransport:
    """Bounded deterministic fixture values, explicitly unrelated to host evidence.

    All source values and reply queues are exact immutable data. No callbacks,
    environment reads, paths, native handles or lazy host providers are accepted.
    """
    def __init__(self, env=(), files=(), queries=()):
        self.calls = []
        self._handles = {}
        self._env = {}
        self._files = {}
        self._queries = {}
        self._positions = {}
        if (type(env) is not tuple or len(env) > 5 or type(files) is not tuple
                or len(files) > 134 or type(queries) is not tuple or len(queries) > 256):
            raise ValueError('input_invalid')
        total = 0
        for pair in env:
            if (type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not EnvKey
                    or type(pair[1]) is not bytes or len(pair[1]) > 97 or pair[0] in self._env):
                raise ValueError('input_invalid')
            self._env[pair[0]] = pair[1]
            total += len(pair[1])
        for item in files:
            if (type(item) is not tuple or len(item) != 4 or type(item[0]) is not FileSource
                    or not immutable(item[0]) or type(item[0].key) is not SourceKey
                    or type(item[1]) is not bytes or len(item[1]) > 8193):
                raise ValueError('input_invalid')
            source, payload, before, after = item
            for metadata in (before, after):
                if type(metadata) is not Resolution:
                    raise ValueError('input_invalid')
                try:
                    values = tuple(getattr(metadata, field.name) for field in fields(Resolution))
                except AttributeError:
                    raise ValueError('input_invalid') from None
                if not immutable(values):
                    raise ValueError('input_invalid')
            if source in self._files:
                raise ValueError('input_invalid')
            self._files[source] = (payload, Resolution(*tuple(getattr(before, field.name)
                for field in fields(Resolution))), Resolution(*tuple(getattr(after, field.name)
                for field in fields(Resolution))))
            total += len(payload)
        for pair in queries:
            if (type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not BusQuery
                    or not immutable(pair[0]) or type(pair[0].key) is not QueryKey
                    or type(pair[1]) is not tuple or not 1 <= len(pair[1]) <= 2
                    or any(type(body) is not bytes or len(body) > 65520 for body in pair[1])):
                raise ValueError('input_invalid')
            if pair[0] in self._queries:
                raise ValueError('input_invalid')
            self._queries[pair[0]] = pair[1]
            total += sum(len(body) for body in pair[1])
        if total > 524288:
            raise ValueError('source_limit')

    def environment_value(self, key, size):
        self.calls.append(('env', key))
        value = self._env.get(key)
        return None if value is None else value[:size]

    def open_readonly(self, source):
        self.calls.append(('file', source))
        if source not in self._files:
            raise ValueError('source_unavailable')
        handle = object()
        self._handles[handle] = ['file', self._files[source], 0, 0]
        return handle

    def stat_handle(self, handle):
        record = self._handles[handle]
        metadata = record[1][1] if record[3] == 0 else record[1][2]
        record[3] += 1
        return metadata

    def read_chunk(self, handle, size):
        record = self._handles[handle]
        payload, offset = record[1][0], record[2]
        record[2] += size
        return payload[offset:offset + size]

    def close_handle(self, handle):
        self.calls.append(('close',))
        del self._handles[handle]

    def begin_query(self, query):
        self.calls.append(('query', query))
        queue = self._queries.get(query)
        index = self._positions.get(query, 0)
        if queue is None or index >= len(queue):
            raise ValueError('source_unavailable')
        self._positions[query] = index + 1
        handle = object()
        self._handles[handle] = ['query', queue[index], 0, 0]
        return handle

    def next_header(self, handle):
        return FrameHeader(len(self._handles[handle][1]))

    def read_body(self, handle, size):
        return self._handles[handle][1][:size]


class FixtureReader(LinuxReader):
    """Explicit in-memory translation profile, never live completeness evidence."""
    def __init__(self, env, files, queries, clock, context, allowed_pids=()):
        super().__init__(MemoryTransport(env, files, queries), clock,
                         DeadlineProfile.SYNTHETIC_ONLY, context, allowed_pids)
