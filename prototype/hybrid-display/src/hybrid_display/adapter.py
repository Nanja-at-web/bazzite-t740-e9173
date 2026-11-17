"""Finite two-pass synthetic orchestration into the unchanged collector.

There is no live completeness source. Only the exact in-memory FixtureReader
can exercise success with the explicit synthetic profile; an ordinary HostReader
always remains blocked. JSON scalar replies and canonical GPU bytes are fixture
encodings, not D-Bus wire compatibility or kernel/filesystem observations.
"""
from math import isfinite
import re
from . import collect
from .host_reader import (AdapterResult, ParseResult, ReadResult, DeclaredFacts,
    SessionRaw, FactsData, DrmRaw, EnvKey, SourceKey, QueryKey, FileSource,
    BusQuery, KScreenProfile, immutable)
from .linux_reader import FixtureReader, MemoryTransport, DeadlineProfile
from .parse_session import (parse_session_context, parse_session, parse_process,
                            valid_identity)
from .parse_kscreen import parse_kscreen, decode_fixture
from .parse_drm import parse_drm, associate, PCI
from .reader_policy import validate_manifest, _context_valid


class _Blocked(Exception):
    def __init__(self, code):
        self.code = code


def _declarations(reader, declared):
    if type(declared) is not DeclaredFacts or not immutable(declared):
        raise _Blocked('input_invalid')
    if (not valid_identity(declared.identity) or type(declared.session_id) is not str
            or re.fullmatch(r'[A-Za-z0-9]{1,32}', declared.session_id) is None):
        raise _Blocked('session_unverified')
    manifest = validate_manifest(declared.manifest)
    if not manifest.ok:
        raise _Blocked(manifest.reasons[0])
    if type(declared.client_pids) is not tuple or len(declared.client_pids) > 16:
        raise _Blocked('input_invalid')
    if any(type(pid) is not int or not 1 <= pid <= 2147483647 for pid in declared.client_pids):
        raise _Blocked('input_invalid')
    if len(set(declared.client_pids)) != len(declared.client_pids):
        raise _Blocked('input_invalid')
    if (type(declared.focus_service_active) is not bool
            or type(declared.decky_active) is not bool):
        raise _Blocked('declaration_missing')
    capabilities = declared.capabilities
    if (type(capabilities) is not tuple or len(capabilities) > 3
            or any(type(name) is not str or name not in ('gamescope', 'steam', 'vkcube')
                   for name in capabilities) or len(set(capabilities)) != len(capabilities)):
        raise _Blocked('input_invalid')
    if declared.kscreen_profile is not KScreenProfile.SYNTHETIC_V1:
        raise _Blocked('kscreen_profile_unverified')
    if (declared.clients_complete is not True or type(reader) is not FixtureReader
            or type(reader.transport) is not MemoryTransport):
        raise _Blocked('client_inventory_unverified')
    if reader.deadline_profile is not DeadlineProfile.SYNTHETIC_ONLY:
        raise _Blocked('reader_deadline_unverified')
    if (not _context_valid(reader.context) or reader.context.uid != declared.identity.uid
            or reader.context.pid != declared.identity.pid
            or reader.context.session_id != declared.session_id
            or reader.context.client_pids != declared.client_pids):
        raise _Blocked('session_unverified')
    return manifest.value


class _Assembly:
    def __init__(self, reader, declared, manifest):
        self.reader = reader
        self.declared = declared
        self.manifest = manifest
        self.started = None
        self.last = None
        self.bytes = 0
        self.bootstrap = set()
        self.owner_receipts = {}
        self.second = False

    def check(self):
        value = self.reader.clock.now()
        if ((type(value) is not int and type(value) is not float)
                or not 0 <= value <= 1e12 or not isfinite(value)
                or self.last is not None and value < self.last):
            raise _Blocked('reader_failed')
        if self.started is None:
            self.started = value
        self.last = value
        if value >= self.started + 5:
            raise _Blocked('source_timeout')
        return value

    def read(self, method, key, limit):
        self.check()
        if self.bytes >= 262144:
            raise _Blocked('source_limit')
        result = method(key)
        self.check()
        if type(result) is not ReadResult:
            raise _Blocked('reader_failed')
        if not result.ok:
            raise _Blocked(result.reasons[0])
        payload = result.payload
        if type(payload) is not bytes:
            raise _Blocked('source_type_invalid')
        if len(payload) > limit or self.bytes + len(payload) > 262144:
            raise _Blocked('source_limit')
        self.bytes += len(payload)
        return payload

    def scalar(self, key, bus='system', target='', argument='', limit=128, object_path=''):
        payload = self.read(self.reader.query, BusQuery(key, bus, target, argument,
                            object_path=object_path), limit)
        try:
            return decode_fixture(payload, limit)
        except (ValueError, TypeError, OverflowError):
            raise _Blocked('ipc_invalid') from None

    def handshake(self, bus):
        if bus in self.bootstrap:
            return
        if self.scalar(QueryKey.AUTH, bus, limit=4096) != 'OK':
            raise _Blocked('ipc_invalid')
        name = self.scalar(QueryKey.HELLO, bus)
        if type(name) is not str or re.fullmatch(r':[0-9]+\.[0-9]+', name) is None:
            raise _Blocked('ipc_invalid')
        self.bootstrap.add(bus)

    def owner(self, name, bus, uid):
        owner = self.scalar(QueryKey.OWNER, bus, 'org.freedesktop.DBus', name)
        if type(owner) is not str or re.fullmatch(r':[0-9]+\.[0-9]+', owner) is None:
            raise _Blocked('owner_missing')
        if self.second and owner != self.owner_receipts[name][0]:
            raise _Blocked('inventory_changed')
        actual_uid = self.scalar(QueryKey.OWNER_UID, bus, 'org.freedesktop.DBus', owner)
        pid = self.scalar(QueryKey.OWNER_PID, bus, 'org.freedesktop.DBus', owner)
        if (type(actual_uid) is not int or actual_uid != uid or type(pid) is not int
                or not 1 <= pid <= 2147483647):
            raise _Blocked('owner_invalid')
        receipt = (owner, actual_uid, pid)
        if self.second and receipt != self.owner_receipts[name]:
            raise _Blocked('inventory_changed')
        self.owner_receipts[name] = receipt
        return receipt

    def session_path(self, owner, pid):
        path = self.scalar(QueryKey.SESSION_BY_PID, target=owner, argument=pid, limit=256)
        if (type(path) is not str or len(path) > 256
                or re.fullmatch(r'/[A-Za-z0-9_/]{1,254}', path) is None):
            raise _Blocked('session_unverified')
        return path

    def process(self, pid):
        status_source = FileSource(SourceKey.PROCESS_STATUS, pid=pid)
        stat_source = FileSource(SourceKey.PROCESS_STAT, pid=pid)
        first_stat = self.read(self.reader.read_file, stat_source, 4096)
        first_status = self.read(self.reader.read_file, status_source, 8192)
        before = parse_process(first_stat, first_status, pid, self.declared.identity.uid)
        if not before.ok:
            raise _Blocked(before.reasons[0])
        second_stat = self.read(self.reader.read_file, stat_source, 4096)
        second_status = self.read(self.reader.read_file, status_source, 8192)
        after = parse_process(second_stat, second_status, pid, self.declared.identity.uid)
        if not after.ok or before.value != after.value:
            raise _Blocked('inventory_changed')
        return before.value

    def capture(self):
        own = self.declared.identity
        limits = {EnvKey.SESSION_ID: 32, EnvKey.SESSION_TYPE: 16,
                  EnvKey.DESKTOP: 16, EnvKey.RUNTIME: 64, EnvKey.BUS: 96}
        env = tuple((key, self.read(self.reader.read_env, key, limits[key])) for key in EnvKey)
        self.handshake('system')
        logind = self.owner('org.freedesktop.login1', 'system', 0)
        path = self.session_path(logind[0], own.pid)
        if path != self.reader.context.session_path:
            raise _Blocked('session_unverified')
        session = []
        property_bytes = self.bytes
        property_deadline = self.check() + 0.5
        for name in ('Id', 'User', 'Type', 'Desktop', 'Remote', 'Active', 'Class', 'State'):
            if self.check() >= property_deadline:
                raise _Blocked('source_timeout')
            value = self.scalar(QueryKey.SESSION_PROPERTY, target=logind[0], argument=name,
                                limit=4096, object_path=path)
            if self.check() >= property_deadline:
                raise _Blocked('source_timeout')
            if name == 'User' and type(value) is list and len(value) == 2:
                value = tuple(value)
            session.append((name, value))
        if self.bytes - property_bytes > 4096:
            raise _Blocked('source_limit')
        session = tuple(session)
        context = parse_session_context(SessionRaw(env, session, ()), own)
        if not context.ok:
            raise _Blocked(context.reasons[0])
        if context.value.session_id != self.declared.session_id:
            raise _Blocked('session_unverified')
        self.handshake('session')
        owners = []
        for label, name in (('kwin', 'org.kde.KWin'), ('kscreen', 'org.kde.KScreen')):
            owner, uid, pid = self.owner(name, 'session', own.uid)
            if self.session_path(logind[0], pid) != path:
                raise _Blocked('session_unverified')
            owners.append((label, owner, uid, pid, context.value.session_id))
        verified = parse_session(SessionRaw(env, session, tuple(owners)), own)
        if not verified.ok:
            raise _Blocked(verified.reasons[0])
        process_receipts = []
        for pid in (own.pid,) + tuple(owner[3] for owner in owners):
            process_receipts.append((pid, self.process(pid)))
        clients = []
        for pid in self.declared.client_pids:
            if self.session_path(logind[0], pid) != path:
                raise _Blocked('session_unverified')
            receipt = self.process(pid)
            if receipt[0] not in ('gamescope', 'steam', 'vkcube'):
                raise _Blocked('process_identity_unverified')
            clients.append(receipt[0])
            process_receipts.append((pid, receipt))
        kscreen_owner = next(owner[1] for owner in owners if owner[0] == 'kscreen')
        config = self.read(self.reader.query, BusQuery(QueryKey.CONFIG, 'session', kscreen_owner), 65536)
        parsed = parse_kscreen(config, self.declared.kscreen_profile)
        if not parsed.ok:
            raise _Blocked(parsed.reasons[0])
        edids = tuple((output.output_id, self.read(self.reader.query,
            BusQuery(QueryKey.EDID, 'session', kscreen_owner, output.output_id), 4096))
            for output in parsed.value.outputs)
        gpus = {}
        for card, connector in self.manifest:
            if card in gpus:
                continue
            gpu = self.read(self.reader.read_file, FileSource(SourceKey.DRM_DEVICE_LINK, card), 1024)
            try:
                gpu = gpu.decode('ascii')
            except ValueError:
                raise _Blocked('drm_device_invalid') from None
            if re.fullmatch(PCI, gpu) is None:
                raise _Blocked('drm_device_invalid')
            gpus[card] = gpu
        drm = []
        for card, connector in self.manifest:
            values = tuple(self.read(self.reader.read_file, FileSource(key, card, connector), limit)
                           for key, limit in ((SourceKey.DRM_STATUS, 16),
                                              (SourceKey.DRM_ENABLED, 16), (SourceKey.DRM_EDID, 4096)))
            drm.append(DrmRaw(card, connector, gpus[card], *values))
        drm = parse_drm(tuple(drm))
        if not drm.ok:
            raise _Blocked(drm.reasons[0])
        associated = associate(parsed.value, drm.value, edids)
        if not associated.ok:
            raise _Blocked(associated.reasons[0])
        facts = FactsData(verified.value, associated.value.outputs, tuple(sorted(clients)),
                          self.declared.focus_service_active, self.declared.decky_active,
                          tuple(sorted(self.declared.capabilities)))
        marker = (env, path, session, tuple(owners), tuple(process_receipts), config,
                  drm.value, associated.value)
        return facts, marker


def assemble_facts(reader, declarations):
    """No partial facts: a single failed source/gate discards both captures."""
    try:
        manifest = _declarations(reader, declarations)
        collection = _Assembly(reader, declarations, manifest)
        first, before = collection.capture()
        collection.second = True
        second, after = collection.capture()
        collection.check()
        if before != after or first != second:
            return ParseResult(reasons=('inventory_changed',))
        return ParseResult(second)
    except _Blocked as blocked:
        return ParseResult(reasons=(blocked.code,))
    except (Exception, SystemExit):
        return ParseResult(reasons=('reader_failed',))


def read_inventory(reader, declarations):
    """Translate once with the real collector. Never preflight, select or launch."""
    facts = assemble_facts(reader, declarations)
    if not facts.ok:
        return AdapterResult(reasons=facts.reasons)
    try:
        result = collect.collect_snapshot(facts.value.to_collector())
        if not result.ok:
            return AdapterResult(reasons=('collector_blocked',))
        # Collector already validated/detached this exact fresh snapshot. The
        # public AdapterResult constructor separately validates external values;
        # rerunning it here would invoke the collector a second time.
        adapted = object.__new__(AdapterResult)
        object.__setattr__(adapted, 'snapshot', result.snapshot)
        object.__setattr__(adapted, 'reasons', ())
        return adapted
    except (Exception, SystemExit):
        return AdapterResult(reasons=('collector_blocked',))
