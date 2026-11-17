"""Only synthetic payloads; these are not observations of a host."""
import json
from hybrid_display.host_reader import EnvKey, OwnIdentity, SessionRaw

def edid(seed=1, blocks=1):
    block = bytearray(128)
    block[:8] = b'\x00\xff\xff\xff\xff\xff\xff\x00'
    block[10] = seed
    block[126] = blocks - 1
    block[127] = -sum(block) % 256
    return bytes(block) + bytes(128) * (blocks - 1)

def frame(outputs=None):
    return json.dumps({'outputs': outputs if outputs is not None else [koutput()]}).encode()

def koutput(number=1, **changes):
    result = dict(id=number, name='DP-' + str(number), connected=True, enabled=True, pos=dict(x=(number - 1) * 1920, y=0), size=dict(width=1920, height=1080), scale=1.0, rotation=1, clones=[], replicationSource=0, currentModeId='m', modes=[dict(id='m', size=dict(width=1920, height=1080), refreshRate=60.0)])
    result.update(changes)
    return result

def session_raw(**changes):
    values = dict(Id='s1', User=(1000, '/user/1000'), Type='wayland', Desktop='KDE', Remote=False, Active=True, Class='user', State='active')
    values.update(changes)
    env = ((EnvKey.SESSION_ID, b's1'), (EnvKey.SESSION_TYPE, b'wayland'), (EnvKey.DESKTOP, b'KDE'), (EnvKey.RUNTIME, b'/run/user/1000'), (EnvKey.BUS, b'unix:path=/run/user/1000/bus'))
    owners = (('kwin', ':1.2', 1000, 11, 's1'), ('kscreen', ':1.3', 1000, 12, 's1'))
    return SessionRaw(env, tuple(values.items()), owners)
OWN = OwnIdentity(1000, 1000, 10)

class FixtureClock:

    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

def adapter_fixture(uid=1000, card=0, second_config=None, session_changes=None, owner_changed=False, client_pids=(), output_count=2, edid_blocks=1, omit_edid=False):
    from dataclasses import replace
    from hybrid_display.host_reader import BusQuery, QueryKey, SourceKey, FileSource, ConnectorManifest, DeclaredFacts, KScreenProfile
    from hybrid_display.linux_reader import FixtureReader
    from hybrid_display.reader_policy import QueryContext, Resolution
    from tests.test_hybrid_display_reader_policy import resolution
    output_ids = tuple(range(1, output_count + 1))
    own = OwnIdentity(uid, uid, 10)
    raw = session_raw(**session_changes or {})
    properties = dict(raw.session)
    properties['User'] = (uid, '/user/' + str(uid))
    env = tuple(((key, value.replace(b'1000', str(uid).encode())) for key, value in raw.env))
    owners = (('org.freedesktop.login1', ':1.1', 9, 0), ('org.kde.KWin', ':1.2', 11, uid), ('org.kde.KScreen', ':1.3', 12, uid))
    context = QueryContext(uid, 10, owners, client_pids, output_ids, True, 's1', '/session/s1')
    queries = []

    def query(key, bus='system', target='', argument='', values=None, once=False):
        payloads = tuple((json.dumps(value).encode() for value in values))
        if len(payloads) == 1 and (not once):
            payloads = payloads * 2
        queries.append((BusQuery(key, bus, target, argument,
                                object_path='/session/s1' if key is QueryKey.SESSION_PROPERTY else ''), payloads))
    for bus in ('system', 'session'):
        query(QueryKey.AUTH, bus, values=['OK'], once=True)
        query(QueryKey.HELLO, bus, values=[':1.99'], once=True)
    for name, owner, pid, owner_uid in owners:
        bus = 'system' if owner_uid == 0 else 'session'
        values = [owner, ':1.4'] if owner_changed and name == 'org.kde.KScreen' else [owner]
        query(QueryKey.OWNER, bus, 'org.freedesktop.DBus', name, values)
        query(QueryKey.OWNER_UID, bus, 'org.freedesktop.DBus', owner, [owner_uid])
        query(QueryKey.OWNER_PID, bus, 'org.freedesktop.DBus', owner, [pid])
    for pid in (10, 11, 12) + client_pids:
        query(QueryKey.SESSION_BY_PID, target=':1.1', argument=pid, values=['/session/s1'])
    for name, value in properties.items():
        query(QueryKey.SESSION_PROPERTY, target=':1.1', argument=name, values=[value])
    config = frame([koutput(number) for number in output_ids])
    queries.append((BusQuery(QueryKey.CONFIG, 'session', ':1.3'), (config, config if second_config is None else second_config)))
    for number in output_ids:
        queries.append((BusQuery(QueryKey.EDID, 'session', ':1.3', number), (edid(number, edid_blocks),) * 2))
    files = []
    for number in output_ids:
        connector = 'DP-' + str(number)
        for key, payload, suffix in ((SourceKey.DRM_STATUS, b'connected\n', 'status'), (SourceKey.DRM_ENABLED, b'enabled\n', 'enabled'), (SourceKey.DRM_EDID, edid(number, edid_blocks), 'edid')):
            metadata = resolution(card, connector)
            metadata = replace(metadata, components=metadata.components[:-1] + (suffix,))
            if not (omit_edid and key is SourceKey.DRM_EDID):
                files.append((FileSource(key, card, connector), payload, metadata, metadata))
    metadata = resolution(card)
    metadata = replace(metadata, kind='directory', components=metadata.links[1][-1], links=metadata.links[:2])
    files.append((FileSource(SourceKey.DRM_DEVICE_LINK, card), b'0000:01:00.0', metadata, metadata))
    for pid, comm in ((10, 'fixture-reader'), (11, 'kwin_wayland'), (12, 'kscreen_backend')) + tuple(((pid, 'steam') for pid in client_pids)):
        tail = ['R'] + ['0'] * 49
        tail[19] = str(pid + 100)
        stat = (str(pid) + ' (' + comm + ') ' + ' '.join(tail) + '\n').encode()
        status = ('Uid: ' + ' '.join([str(uid)] * 4) + '\n').encode()
        for key, payload, suffix in ((SourceKey.PROCESS_STAT, stat, 'stat'), (SourceKey.PROCESS_STATUS, status, 'status')):
            metadata = Resolution('procfs', 'regular', 2, pid, True, False, (str(pid), suffix), (), uid, pid + 100)
            files.append((FileSource(key, pid=pid), payload, metadata, metadata))
    reader = FixtureReader(env, tuple(files), tuple(queries), FixtureClock(), context, (10, 11, 12) + client_pids)
    declarations = DeclaredFacts(own, 's1', ConnectorManifest(tuple(((card, 'DP-' + str(number)) for number in output_ids)), True), client_pids, True, False, False, ('gamescope', 'vkcube'), KScreenProfile.SYNTHETIC_V1)
    return (reader, declarations)
