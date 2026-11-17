"""Pure immutable contracts. No host implementation or implicit collection."""
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Protocol

CODES = frozenset("session_context_invalid session_bus_invalid ipc_invalid owner_missing owner_invalid session_unverified kscreen_unavailable kscreen_schema_invalid edid_invalid drm_status_invalid drm_enabled_invalid drm_device_invalid process_identity_unverified source_not_allowed input_invalid source_unavailable source_denied source_limit source_timeout source_type_invalid ipc_limit inventory_changed association_ambiguous declaration_missing client_inventory_unverified kscreen_profile_unverified reader_deadline_unverified reader_failed collector_blocked command_not_allowed".split())

class EnvKey(Enum):
    SESSION_ID = 'XDG_SESSION_ID'
    SESSION_TYPE = 'XDG_SESSION_TYPE'
    DESKTOP = 'XDG_CURRENT_DESKTOP'
    RUNTIME = 'XDG_RUNTIME_DIR'
    BUS = 'DBUS_SESSION_BUS_ADDRESS'

class SourceKey(Enum):
    DRM_STATUS = 'drm_status'
    DRM_ENABLED = 'drm_enabled'
    DRM_EDID = 'drm_edid'
    DRM_DEVICE_LINK = 'drm_device_link'
    PROCESS_STAT = 'process_stat'
    PROCESS_STATUS = 'process_status'

class QueryKey(Enum):
    AUTH = 'auth'
    HELLO = 'hello'
    OWNER = 'owner'
    OWNER_UID = 'owner_uid'
    OWNER_PID = 'owner_pid'
    SESSION_BY_PID = 'session_by_pid'
    SESSION_PROPERTY = 'session_property'
    CONFIG = 'config'
    EDID = 'edid'

class KScreenProfile(Enum):
    UNKNOWN = 'unknown'
    SYNTHETIC_V1 = 'synthetic-json-v1-not-a-live-protocol'

@dataclass(frozen=True, slots=True, repr=False)
class OwnIdentity:
    uid: int
    euid: int
    pid: int
    privileged: bool = False

@dataclass(frozen=True, slots=True, repr=False)
class FileSource:
    key: SourceKey
    card: int = 0
    connector: str = ''
    pid: int = 0

@dataclass(frozen=True, slots=True, repr=False)
class BusQuery:
    key: QueryKey
    bus: str = 'system'
    target: str = ''
    argument: str | int = ''
    autostart: bool = False
    object_path: str = ''

@dataclass(frozen=True, slots=True, repr=False)
class ConnectorManifest:
    entries: tuple
    complete: bool

@dataclass(frozen=True, slots=True, repr=False)
class DeclaredFacts:
    identity: OwnIdentity
    session_id: str
    manifest: ConnectorManifest
    client_pids: tuple
    clients_complete: bool | None
    focus_service_active: bool | None
    decky_active: bool | None
    capabilities: tuple
    kscreen_profile: KScreenProfile = KScreenProfile.UNKNOWN

@dataclass(frozen=True, slots=True, repr=False)
class SessionRaw:
    env: tuple
    session: tuple
    owners: tuple

@dataclass(frozen=True, slots=True, repr=False)
class SessionData:
    session_id: str
    desktop: str
    owners: tuple

@dataclass(frozen=True, slots=True, repr=False)
class KOutput:
    output_id: int
    name: str
    connected: bool
    enabled: bool
    rectangle: tuple | None
    mirrored: bool

@dataclass(frozen=True, slots=True, repr=False)
class KScreenData:
    outputs: tuple

@dataclass(frozen=True, slots=True, repr=False)
class DrmRaw:
    card: int
    connector: str
    gpu: str
    status: bytes
    enabled: bytes
    edid: bytes

@dataclass(frozen=True, slots=True, repr=False)
class DrmOutput:
    card: int
    connector: str
    gpu: str
    connected: bool
    enabled: bool
    digest: str | None

@dataclass(frozen=True, slots=True, repr=False)
class DrmData:
    outputs: tuple

@dataclass(frozen=True, slots=True, repr=False)
class Associated:
    outputs: tuple

@dataclass(frozen=True, slots=True, repr=False)
class FactsData:
    session: SessionData
    outputs: tuple
    clients: tuple
    focus_service_active: bool
    decky_active: bool
    capabilities: tuple

    def to_collector(self):
        """Fresh nine-field translation, only used after validated assembly."""
        from .model import Output, OutputIdentity
        outputs = tuple(Output(OutputIdentity(item[0]), *item[1:]) for item in self.outputs)
        return {'session_type': 'wayland', 'desktop': self.session.desktop,
                'own_local_session': True, 'kwin_running': True, 'outputs': outputs,
                'existing_clients': self.clients, 'focus_service_active': self.focus_service_active,
                'decky_active': self.decky_active, 'capabilities': self.capabilities}

_VALUE_TYPES = (OwnIdentity, FileSource, BusQuery, ConnectorManifest, DeclaredFacts,
                SessionRaw, SessionData, KOutput, KScreenData, DrmRaw, DrmOutput,
                DrmData, Associated, FactsData)

def immutable(value, depth=0, budget=None):
    """Exact types before every operation; bounded, callback-free validation."""
    if budget is None:
        budget = [4096, 262144]
    budget[0] -= 1
    if depth > 12 or budget[0] < 0:
        return False
    kind = type(value)
    if value is None or kind is bool:
        return True
    if kind is str:
        budget[1] -= len(value) * 4
        return len(value) <= 8192 and budget[1] >= 0
    if kind is bytes:
        budget[1] -= len(value)
        return len(value) <= 65536 and budget[1] >= 0
    if kind is int:
        return -2147483648 <= value <= 2147483647
    if kind is float:
        return value == value and -1e12 <= value <= 1e12
    if any(kind is allowed for allowed in (EnvKey, SourceKey, QueryKey, KScreenProfile)):
        return True
    if kind is tuple:
        return len(value) <= 256 and all(immutable(item, depth + 1, budget) for item in value)
    if any(kind is allowed for allowed in _VALUE_TYPES):
        try:
            return all(immutable(getattr(value, item.name), depth + 1, budget)
                       for item in fields(value))
        except AttributeError:
            return False
    return False


def _reasons(value):
    if type(value) is not tuple or len(value) > len(CODES):
        return ('input_invalid',)
    if any(type(code) is not str or len(code) > 32 or code not in CODES for code in value):
        return ('input_invalid',)
    return tuple(sorted(set(value)))

@dataclass(frozen=True, slots=True)
class ReadResult:
    payload: bytes | None = field(default=None, repr=False)
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        reasons = _reasons(self.reasons)
        if self.payload is not None and (type(self.payload) is not bytes or len(self.payload) > 65536):
            reasons = ('input_invalid',)
        if self.payload is None and not reasons:
            reasons = ('source_unavailable',)
        object.__setattr__(self, 'reasons', reasons)
        if reasons:
            object.__setattr__(self, 'payload', None)

    @property
    def ok(self):
        return self.payload is not None and not self.reasons

    @property
    def status(self):
        return 'success' if self.ok else 'blocked'

@dataclass(frozen=True, slots=True)
class ParseResult:
    value: object = field(default=None, repr=False)
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        reasons = _reasons(self.reasons)
        if self.value is not None and not immutable(self.value):
            reasons = ('input_invalid',)
        if self.value is None and not reasons:
            reasons = ('input_invalid',)
        object.__setattr__(self, 'reasons', reasons)
        if reasons:
            object.__setattr__(self, 'value', None)

    @property
    def ok(self):
        return self.value is not None and not self.reasons

    @property
    def status(self):
        return 'success' if self.ok else 'blocked'

@dataclass(frozen=True, slots=True)
class AdapterResult:
    snapshot: object = field(default=None, repr=False)
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        from .model import SessionSnapshot
        reasons = _reasons(self.reasons)
        if self.snapshot is not None and type(self.snapshot) is not SessionSnapshot:
            reasons = ('input_invalid',)
        if self.snapshot is not None and not reasons:
            from .collect import collect_snapshot, FIELDS
            try:
                if self.snapshot.gaming_edid_sha256 is not None:
                    reasons = ('input_invalid',)
                else:
                    checked = collect_snapshot({name: getattr(self.snapshot, name)
                                                for name in FIELDS})
                    if checked.ok:
                        object.__setattr__(self, 'snapshot', checked.snapshot)
                    else:
                        reasons = ('input_invalid',)
            except (Exception, SystemExit):
                reasons = ('input_invalid',)
        if self.snapshot is None and not reasons:
            reasons = ('input_invalid',)
        object.__setattr__(self, 'reasons', reasons)
        if reasons:
            object.__setattr__(self, 'snapshot', None)

    @property
    def ok(self):
        return self.snapshot is not None and not self.reasons

    @property
    def status(self):
        return 'success' if self.ok else 'blocked'

class HostReader(Protocol):
    def read_env(self, key: EnvKey) -> ReadResult: ...
    def read_file(self, source: FileSource) -> ReadResult: ...
    def query(self, query: BusQuery) -> ReadResult: ...
