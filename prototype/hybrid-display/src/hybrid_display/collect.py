"""Pure collector boundary over explicit ordinary Python data, never live data.

The exact nine-key dict uses existing Output/OutputIdentity records, list/tuple
inventories and explicit booleans. Only known session/desktop/program labels
and canonical address strings are accepted; descriptions must be empty. Limits
are local validation policy, not measured hardware limits. No input conversion,
fallback monitor choice, Host adapter or preflight decision occurs here.

Success contains a detached snapshot with sorted inventories; strings are
immutable values. A disconnected, disabled connector may explicitly lack EDID.
Only duplicate active EDIDs are refused here; selection ambiguity among other
records remains the resolver/preflight's responsibility. No gaming role is set.
"""

from dataclasses import dataclass, field
import re
from .model import Output, OutputIdentity, SessionSnapshot


@dataclass(frozen=True)
class CollectionResult:
    """Translation status only. Snapshot payload stays out of repr/str."""
    snapshot: SessionSnapshot | None = field(default=None, repr=False)
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.snapshot is not None and not self.reasons

    @property
    def status(self) -> str:
        return 'success' if self.ok else 'blocked'


FIELDS = frozenset({
    'session_type', 'desktop', 'own_local_session', 'kwin_running', 'outputs',
    'existing_clients', 'focus_service_active', 'decky_active', 'capabilities',
})
MAX_OUTPUTS = 16
MAX_CLIENTS = 16
PROGRAMS = frozenset({'gamescope', 'steam', 'vkcube'})
CONNECTOR = r'(?:DP|HDMI-A|eDP|DVI-D|DVI-I|DVI-A|VGA|DSI|LVDS)-[1-9][0-9]{0,2}(?:-[1-9][0-9]{0,2})?'


def _has_fields(value, names):
    # Called only after exact model-type checks. Inspect keys, never dump data.
    data = value.__dict__
    return (type(data) is dict and len(data) == len(names)
            and all(type(key) is str for key in data) and set(data) == names)


def _valid_output(record):
    if type(record) is not Output or type(record.identity) is not OutputIdentity:
        return False
    identity = record.identity
    if not _has_fields(record, {'identity', 'gpu_pci', 'drm_connector', 'kwin_name',
                                'enabled', 'mirrored', 'connected'}):
        return False
    if not _has_fields(identity, {'edid_sha256', 'manufacturer', 'model'}):
        return False
    if any(type(flag) is not bool for flag in (record.enabled, record.mirrored, record.connected)):
        return False
    if (type(identity.manufacturer) is not str or identity.manufacturer != ''
            or type(identity.model) is not str or identity.model != ''):
        return False
    for value, pattern, limit in (
        (record.gpu_pci, r'[0-9a-f]{4}:[0-9a-f]{2}:[01][0-9a-f]\.[0-7]', 12),
        (record.drm_connector, CONNECTOR, 24),
        (record.kwin_name, CONNECTOR, 24),
    ):
        if type(value) is not str or len(value) > limit or re.fullmatch(pattern, value) is None:
            return False
    digest = identity.edid_sha256
    if digest is None:
        return not record.connected and not record.enabled
    return (type(digest) is str and len(digest) == 64
            and re.fullmatch(r'[0-9a-f]{64}', digest) is not None
            and (not record.enabled or record.connected))


def _outputs(records, reasons):
    if type(records) not in (tuple, list):
        reasons.add('outputs_invalid')
        return ()
    if len(records) > MAX_OUTPUTS:
        reasons.add('outputs_limit')
        return ()
    valid = []
    for record in records:
        if _valid_output(record):
            valid.append(record)
        else:
            reasons.add('output_invalid')
    addresses = [(record.gpu_pci, record.drm_connector) for record in valid]
    names = [record.kwin_name for record in valid]
    active = [record.identity.edid_sha256 for record in valid if record.enabled]
    for values, reason in ((addresses, 'output_address_duplicate'),
                           (names, 'output_name_duplicate'),
                           (active, 'output_active_identity_duplicate')):
        if len(set(values)) != len(values):
            reasons.add(reason)
    return tuple(Output(OutputIdentity(record.identity.edid_sha256), record.gpu_pci,
                        record.drm_connector, record.kwin_name, record.enabled,
                        record.mirrored, record.connected) for record in sorted(
                            valid, key=lambda item: (item.gpu_pci, item.drm_connector, item.kwin_name)))


def _labels(values, containers, limit, prefix, reasons):
    if type(values) not in containers:
        reasons.add(prefix + '_invalid')
        return ()
    if len(values) > limit:
        reasons.add(prefix + '_limit')
        return ()
    if any(type(value) is not str or value not in PROGRAMS for value in values):
        reasons.add(prefix + '_invalid')
        return ()
    return tuple(sorted(values))


def collect_snapshot(facts: object) -> CollectionResult:
    """Translate explicit data atomically; failures never include input text."""
    try:
        return _collect(facts)
    except (Exception, SystemExit):
        return CollectionResult(reasons=('collector_failed',))


def _collect(facts):
    if type(facts) is not dict:
        return CollectionResult(reasons=('facts_invalid',))
    if any(type(key) is not str for key in facts):
        return CollectionResult(reasons=('fields_invalid',))
    reasons = set()
    keys = set(facts)
    if FIELDS - keys:
        reasons.add('fields_missing')
    if keys - FIELDS:
        reasons.add('fields_unknown')
    if reasons:
        return CollectionResult(reasons=tuple(sorted(reasons)))
    if type(facts['session_type']) is not str or facts['session_type'] not in ('wayland', 'x11', 'tty'):
        reasons.add('session_type_invalid')
    if type(facts['desktop']) is not str or facts['desktop'] not in ('KDE', 'plasma', 'Plasma', 'GNOME', 'gamescope'):
        reasons.add('desktop_invalid')
    if any(type(facts[name]) is not bool for name in
           ('own_local_session', 'kwin_running', 'focus_service_active', 'decky_active')):
        reasons.add('session_flags_invalid')
    outputs = _outputs(facts['outputs'], reasons)
    clients = _labels(facts['existing_clients'], (list, tuple), MAX_CLIENTS, 'clients', reasons)
    capabilities = _labels(facts['capabilities'], (list, tuple, set, frozenset),
                           len(PROGRAMS), 'capabilities', reasons)
    if reasons:
        return CollectionResult(reasons=tuple(sorted(reasons)))
    return CollectionResult(SessionSnapshot(**dict(facts, outputs=outputs,
                            existing_clients=clients, capabilities=frozenset(capabilities))))
