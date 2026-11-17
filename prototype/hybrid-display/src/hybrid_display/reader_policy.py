"""Pure source-policy skeleton."""
from dataclasses import dataclass
import re
from .collect import CONNECTOR
from .parse_drm import PCI
from .host_reader import (ParseResult, FileSource, SourceKey, BusQuery, QueryKey,
                          ConnectorManifest, immutable)

@dataclass(frozen=True, slots=True, repr=False)
class Resolution:
    filesystem: str
    kind: str
    mount: int
    inode: int
    same_mount: bool
    final_symlink: bool
    components: tuple
    links: tuple = ()
    uid: int = 1000
    starttime: int = 1

@dataclass(frozen=True, slots=True, repr=False)
class QueryContext:
    uid: int
    pid: int
    owners: tuple = ()
    client_pids: tuple = ()
    output_ids: tuple = ()
    session_bound: bool = False
    session_id: str = ''
    session_path: str = ''

def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _connector(value):
    return (type(value) is str and len(value) <= 24
            and re.fullmatch(CONNECTOR, value) is not None)


def _pci(value):
    return type(value) is str and len(value) == 12 and re.fullmatch(PCI, value) is not None


def validate_manifest(value):
    if type(value) is not ConnectorManifest or not immutable(value):
        return ParseResult(reasons=('source_not_allowed',))
    entries = value.entries
    if value.complete is not True or type(entries) is not tuple or len(entries) > 16:
        return ParseResult(reasons=('source_not_allowed',))
    seen = set()
    for pair in entries:
        if (type(pair) is not tuple or len(pair) != 2
                or not _int(pair[0], 0, 15) or not _connector(pair[1]) or pair in seen):
            return ParseResult(reasons=('source_not_allowed',))
        seen.add(pair)
    return ParseResult(tuple(sorted(entries)))


def _components(value):
    return (type(value) is tuple and 1 <= len(value) <= 32
            and all(type(part) is str and 1 <= len(part) <= 64
                    and part not in ('.', '..') and '/' not in part and '\0' not in part
                    and re.fullmatch(r'[A-Za-z0-9_.:-]+', part) is not None
                    for part in value))


def _resolution(source, metadata):
    if type(metadata) is not Resolution:
        return None
    try:
        values = (metadata.filesystem, metadata.kind, metadata.mount, metadata.inode,
                  metadata.same_mount, metadata.final_symlink, metadata.components,
                  metadata.links, metadata.uid, metadata.starttime)
    except AttributeError:
        return None
    if (not immutable(values) or type(metadata.filesystem) is not str
            or type(metadata.kind) is not str or not _int(metadata.mount, 1, 2147483647)
            or not _int(metadata.inode, 1, 2147483647) or metadata.same_mount is not True
            or metadata.final_symlink is not False or not _components(metadata.components)):
        return None
    if source.key is SourceKey.PROCESS_STAT or source.key is SourceKey.PROCESS_STATUS:
        suffix = 'stat' if source.key is SourceKey.PROCESS_STAT else 'status'
        if (metadata.filesystem != 'procfs' or metadata.kind != 'regular'
                or metadata.components != (str(source.pid), suffix)
                or metadata.links != () or not _int(metadata.uid, 1, 2147483647)
                or not _int(metadata.starttime, 1, 2147483647)):
            return None
        return ''
    if metadata.filesystem != 'sysfs' or type(metadata.links) is not tuple:
        return None
    expected_roles = {'card', 'device'}
    if source.key is not SourceKey.DRM_DEVICE_LINK:
        expected_roles.add('connector')
    if len(metadata.links) != len(expected_roles):
        return None
    roles, gpu, gpu_target = set(), None, None
    targets = {}
    card_name = 'card' + str(source.card)
    for link in metadata.links:
        if type(link) is not tuple or len(link) != 6:
            return None
        role, card, connector, address, hops, components = link
        if (type(role) is not str or role not in expected_roles or role in roles
                or not _int(card, 0, 15) or card != source.card
                or type(connector) is not str or not _pci(address)
                or not _int(hops, 1, 8) or not _components(components)
                or len(components) < 3 or components[0] != 'devices'
                or re.fullmatch(r'pci[0-9a-f]{4}:[0-9a-f]{2}', components[1]) is None):
            return None
        roles.add(role)
        targets[role] = components
        if gpu is not None and gpu != address:
            return None
        gpu = address
        if role == 'card':
            if connector != '' or components[-3:] != (address, 'drm', card_name):
                return None
            topology = components[2:-2]
        elif role == 'device':
            if connector != '' or components[-1] != address:
                return None
            topology = components[2:]
        else:
            if (connector != source.connector or components[-4:] !=
                    (address, 'drm', card_name, card_name + '-' + source.connector)):
                return None
            topology = components[2:-3]
        if not topology or any(not _pci(part) for part in topology):
            return None
        target = components[:2] + topology
        if gpu_target is not None and gpu_target != target:
            return None
        gpu_target = target
    if roles != expected_roles:
        return None
    suffixes = {SourceKey.DRM_STATUS: 'status', SourceKey.DRM_ENABLED: 'enabled',
                SourceKey.DRM_EDID: 'edid'}
    if source.key is SourceKey.DRM_DEVICE_LINK:
        if metadata.kind != 'directory' or metadata.components != targets['device']:
            return None
    elif (metadata.kind != 'regular' or metadata.components !=
          targets['connector'] + (suffixes[source.key],)):
        return None
    return gpu


def validate_source(source, resolution=None, allowed_pids=()):
    if type(source) is not FileSource or not immutable(source):
        return ParseResult(reasons=('source_type_invalid',))
    if type(source.key) is not SourceKey:
        return ParseResult(reasons=('source_not_allowed',))
    if type(allowed_pids) is not tuple or len(allowed_pids) > 19:
        return ParseResult(reasons=('source_not_allowed',))
    if any(not _int(pid, 1, 2147483647) for pid in allowed_pids):
        return ParseResult(reasons=('source_not_allowed',))
    process = source.key is SourceKey.PROCESS_STAT or source.key is SourceKey.PROCESS_STATUS
    if process:
        if (not _int(source.pid, 1, 2147483647) or source.pid not in allowed_pids
                or type(source.card) is not int or source.card != 0
                or type(source.connector) is not str or source.connector != ''):
            return ParseResult(reasons=('source_not_allowed',))
    elif (not _int(source.card, 0, 15) or type(source.pid) is not int or source.pid != 0
          or (source.key is SourceKey.DRM_DEVICE_LINK and source.connector != '')
          or (source.key is not SourceKey.DRM_DEVICE_LINK and not _connector(source.connector))):
        return ParseResult(reasons=('source_not_allowed',))
    gpu = ''
    if resolution is not None:
        gpu = _resolution(source, resolution)
        if gpu is None:
            return ParseResult(reasons=('source_not_allowed',))
    return ParseResult((source.key.value, source.card, source.connector, source.pid, gpu))


def _context_valid(context):
    if type(context) is not QueryContext:
        return False
    try:
        values = (context.uid, context.pid, context.owners, context.client_pids,
                  context.output_ids, context.session_bound, context.session_id)
    except AttributeError:
        return False
    if (not immutable(values) or not _int(context.uid, 1, 2147483647)
            or not _int(context.pid, 1, 2147483647)
            or type(context.owners) is not tuple or len(context.owners) > 3
            or type(context.client_pids) is not tuple or len(context.client_pids) > 16
            or type(context.output_ids) is not tuple or len(context.output_ids) > 16
            or type(context.session_bound) is not bool or type(context.session_id) is not str
            or len(context.session_id) > 32 or type(context.session_path) is not str
            or len(context.session_path) > 256
            or context.session_path != '' and re.fullmatch(r'/[A-Za-z0-9_/]{1,254}', context.session_path) is None):
        return False
    if any(not _int(number, 1, 2147483647)
           for number in context.client_pids + context.output_ids):
        return False
    if context.session_bound and re.fullmatch(r'[A-Za-z0-9]{1,32}', context.session_id) is None:
        return False
    names, owners = set(), set()
    for item in context.owners:
        if type(item) is not tuple or len(item) != 4:
            return False
        name, owner, pid, uid = item
        if (type(name) is not str or name not in
                ('org.freedesktop.login1', 'org.kde.KWin', 'org.kde.KScreen')
                or name in names or type(owner) is not str or len(owner) > 128
                or re.fullmatch(r':[0-9]+\.[0-9]+', owner) is None or owner in owners
                or not _int(pid, 1, 2147483647) or type(uid) is not int
                or uid != (0 if name == 'org.freedesktop.login1' else context.uid)):
            return False
        names.add(name)
        owners.add(owner)
    return True


def validate_query(query, context=None):
    denied = ParseResult(reasons=('source_not_allowed',))
    if (type(query) is not BusQuery or not immutable(query) or not _context_valid(context)
            or type(query.key) is not QueryKey or type(query.bus) is not str
            or query.bus not in ('system', 'session') or type(query.target) is not str
            or len(query.target) > 128 or query.autostart is not False
            or type(query.object_path) is not str
            or (query.key is not QueryKey.SESSION_PROPERTY and query.object_path != '')):
        return denied
    owners = {name: owner for name, owner, pid, uid in context.owners}
    daemon = 'org.freedesktop.DBus'
    key, argument = query.key, query.argument
    if key is QueryKey.AUTH or key is QueryKey.HELLO:
        valid = query.target == '' and type(argument) is str and argument == ''
    elif key is QueryKey.OWNER:
        allowed = ('org.freedesktop.login1',) if query.bus == 'system' else ('org.kde.KWin', 'org.kde.KScreen')
        valid = (query.target == daemon and type(argument) is str and argument in allowed)
    elif key is QueryKey.OWNER_UID or key is QueryKey.OWNER_PID:
        allowed = [owner for name, owner in owners.items()
                   if (name == 'org.freedesktop.login1') is (query.bus == 'system')]
        valid = query.target == daemon and type(argument) is str and argument in allowed
    elif key is QueryKey.SESSION_BY_PID:
        pids = (context.pid,) + tuple(item[2] for item in context.owners
                                            if item[0] in ('org.kde.KWin', 'org.kde.KScreen')) + context.client_pids
        valid = (query.bus == 'system' and query.target == owners.get('org.freedesktop.login1')
                 and _int(argument, 1, 2147483647) and argument in pids)
    elif key is QueryKey.SESSION_PROPERTY:
        valid = (query.bus == 'system' and query.target == owners.get('org.freedesktop.login1')
                 and context.session_path != '' and query.object_path == context.session_path
                 and context.session_id != '' and type(argument) is str and argument in
                 ('Id', 'User', 'Type', 'Desktop', 'Remote', 'Active', 'Class', 'State'))
    elif key is QueryKey.CONFIG or key is QueryKey.EDID:
        valid = (query.bus == 'session' and query.target == owners.get('org.kde.KScreen')
                 and context.session_bound is True)
        if key is QueryKey.CONFIG:
            valid = valid and type(argument) is str and argument == ''
        else:
            valid = valid and _int(argument, 1, 2147483647) and argument in context.output_ids
    else:
        valid = False
    if not valid:
        return denied
    return ParseResult((query.key.value, query.bus, query.target, query.argument))
