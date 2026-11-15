"""Fixed-schema redacted diagnostics over explicitly supplied Python data.

No collection, clock, output, logging, file/network access or other MVP imports.
render_report returns only status, fixed renderer finding codes and an optional
safe string. Its status describes report generation, not a hardware/MVP result.
The explicitly supplied result field remains separate. No facts are measured.

Schema 1, fixed order: mode/result; optional marker, six numeric component
versions, session/backend/stage enums, connected/active counts, journal count
and truncation flag, exit code, closed finding codes, sorted monitor rows.
Mappings are read by exact known keys only; unknown fields/keys/values are never
visited. Typed DiagnosticData/MonitorData are copied by named fields, never by
reflection, repr, vars, asdict, exception text or generic recursive dumping.

Text policy is conservative: whole invalid fields are omitted, not shortened.
There is no generic secret detector. Free text, usernames, paths, suffixes,
addresses and arbitrary syntactically valid codes are not accepted. Descriptions
are exact catalog literals (including the explicitly allowed Unicode 三星),
not proof of hardware identity. New labels need a separately reviewed policy.
Numeric versions have 1--3 components; raw distro/RPM suffixes are not supported.
Markers must already be redacted t+SECONDS.mmm s without the intervening space.
Only literal code catalog members of <=32 characters survive; no free codes.

Monitor input accepts ONLY an already redacted edid: + 12 lowercase hex digits
+ …, optionally with the established ambiguity marker. Never supply a full EDID
digest, raw EDID, Output object or serial. Prefixes are display-only, never a
selection key. Repeated prefixes are marked ambiguous even for equal models.
Optional geometry is all-or-none, 1..16384 per axis and 1..360 integer Hz.

Limits: 16 input codes (before dedup), 8 monitor rows, 32 display/code chars,
24 marker chars, 48 label chars, 1024 report Unicode characters and 32 LF lines.
These also bound intermediate formatting. Known literal descriptions plus strict
formats exclude terminal controls and injected lines; invalid collection types
or limits block with no partial report. Optional text/code redaction warns.
Missing descriptions become the fixed unavailable label, never a guessed name.
Journal text is wholly ignored; only 0..100 and a caller-supplied boolean are
permitted, and truncation is visible. No 512-char journal excerpts are retained.

Caller objects are ordinary in-memory data, not an execution sandbox: custom
Mapping implementations may execute their own code. Ordinary failures are
converted to a fixed diagnostic_failed result without exposing their messages.
No auto-conversion of existing Preflight/CLI/Command/Lifecycle objects occurs;
callers must explicitly select safe fields before invoking this library.
"""

from dataclasses import dataclass, field
from collections.abc import Mapping
import re
from types import MappingProxyType


FINDING_CODES = frozenset({
    'kwin_missing', 'session_not_wayland', 'session_not_plasma', 'session_not_local',
    'too_few_active_outputs', 'mirrored_outputs', 'process_conflict',
    'focus_integration_active', 'decky_active', 'missing_gamescope',
    'missing_graphics_client', 'selection_missing', 'selection_invalid',
    'selection_not_found', 'selection_ambiguous', 'outputs_invalid',
    'selected_output_disabled', 'selected_output_disconnected', 'selected_output_mirrored',
    'command_blocked', 'environment_blocked', 'inventory_mismatch',
    'wayland_exposure_unknown', 'wayland_exposure_unsupported', 'planning_failed',
    'spawn_failed', 'identity_invalid', 'identity_mismatch', 'ownership_unverified',
    'ownership_check_failed', 'invalid_transition', 'clock_invalid', 'clock_reversed',
    'termination_timeout',
})
MAX_CODES = 16
MAX_MONITORS = 8
MAX_REPORT_CHARS = 1024
MAX_REPORT_LINES = 32


@dataclass(frozen=True)
class MonitorData:
    label: object = field(repr=False)
    manufacturer: object = field(default=None, repr=False)
    model: object = field(default=None, repr=False)
    width: object = field(default=None, repr=False)
    height: object = field(default=None, repr=False)
    refresh_hz: object = field(default=None, repr=False)


@dataclass(frozen=True)
class DiagnosticData:
    mode: object = field(repr=False)
    result: object = field(repr=False)
    marker: object = field(default=None, repr=False)
    versions: object = field(default=None, repr=False)
    session_type: object = field(default=None, repr=False)
    backend: object = field(default=None, repr=False)
    stage: object = field(default=None, repr=False)
    connected_outputs: object = field(default=None, repr=False)
    active_outputs: object = field(default=None, repr=False)
    journal_entries: object = field(default=None, repr=False)
    journal_truncated: object = field(default=None, repr=False)
    exit_code: object = field(default=None, repr=False)
    codes: object = field(default=(), repr=False)
    monitors: object = field(default=(), repr=False)

    def __post_init__(self):
        for name, value in (('codes', self.codes), ('monitors', self.monitors)):
            if type(value) is list:
                object.__setattr__(self, name, tuple(value))
            elif type(value) is set:
                object.__setattr__(self, name, frozenset(value))
        if type(self.versions) is dict:
            object.__setattr__(self, 'versions', MappingProxyType(self.versions.copy()))


@dataclass(frozen=True)
class DiagnosticResult:
    status: str
    codes: tuple[str, ...] = ()
    report: str | None = field(default=None, repr=False)


def render_report(fields):
    try:
        return _render(fields)
    except Exception:
        return DiagnosticResult('blocked', ('diagnostic_failed',))


def _render(fields):
    if type(fields) is DiagnosticData:
        fields = {
            'mode': fields.mode, 'result': fields.result, 'marker': fields.marker,
            'versions': {} if fields.versions is None else fields.versions,
            'session_type': fields.session_type, 'backend': fields.backend, 'stage': fields.stage,
            'connected_outputs': fields.connected_outputs, 'active_outputs': fields.active_outputs,
            'journal_entries': fields.journal_entries, 'journal_truncated': fields.journal_truncated,
            'exit_code': fields.exit_code, 'codes': fields.codes, 'monitors': fields.monitors,
        }
    if not isinstance(fields, Mapping):
        return DiagnosticResult('blocked', ('schema_invalid',))
    mode, outcome = fields.get('mode'), fields.get('result')
    if (type(mode) is not str or mode not in ('preflight', 'plan')
            or type(outcome) is not str or outcome not in ('success', 'warning', 'blocked')):
        return DiagnosticResult('blocked', ('schema_invalid',))
    warnings = set()
    report = 'schema_version: 1\nmode: ' + mode + '\nresult: ' + outcome + '\n'
    marker = fields.get('marker')
    if marker is not None:
        if type(marker) is str and len(marker) <= 24 and re.fullmatch(r't\+[0-9]{1,9}\.[0-9]{3}s', marker):
            report += 'marker: ' + marker + '\n'
        else:
            warnings.add('marker_redacted')
    versions = fields.get('versions', {})
    if versions is None:
        versions = {}
    if isinstance(versions, Mapping):
        for name in ('os', 'kernel', 'gamescope', 'plasma', 'kwin', 'mesa'):
            value = versions.get(name)
            if value is not None:
                if type(value) is str and len(value) <= 32 and re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,4}){0,2}', value):
                    report += 'version_' + name + ': ' + value + '\n'
                else:
                    warnings.add('versions_redacted')
    else:
        warnings.add('versions_redacted')
    for name, allowed in (('session_type', ('wayland', 'x11', 'tty')),
                          ('backend', ('wayland', 'unconfirmed')),
                          ('stage', ('graphics', 'steam', 'game', 'not_tested'))):
        value = fields.get(name)
        if value is not None:
            if type(value) is not str or value not in allowed:
                return DiagnosticResult('blocked', ('enum_invalid',))
            report += name + ': ' + value + '\n'
    for name, lower, upper in (('connected_outputs', 0, 16), ('active_outputs', 0, 16),
                               ('journal_entries', 0, 100), ('exit_code', -(2**31), 2**31 - 1)):
        value = fields.get(name)
        if value is not None:
            if type(value) is not int or not lower <= value <= upper:
                return DiagnosticResult('blocked', ('number_invalid',))
            report += name + ': ' + str(value) + '\n'
    connected, active = fields.get('connected_outputs'), fields.get('active_outputs')
    if connected is not None and active is not None and active > connected:
        return DiagnosticResult('blocked', ('counts_inconsistent',))
    truncated = fields.get('journal_truncated')
    if truncated is not None:
        if type(truncated) is not bool:
            return DiagnosticResult('blocked', ('boolean_invalid',))
        report += 'journal_truncated: ' + ('true' if truncated else 'false') + '\n'
        if truncated:
            warnings.add('journal_truncated')
    codes = fields.get('codes', ())
    if type(codes) not in (tuple, list, set, frozenset):
        return DiagnosticResult('blocked', ('codes_invalid',))
    if len(codes) > MAX_CODES:
        return DiagnosticResult('blocked', ('item_limit',))
    accepted = set()
    for code in codes:
        if type(code) is str and len(code) <= 32 and code in FINDING_CODES:
            accepted.add(code)
        else:
            warnings.add('codes_redacted')
    for code in sorted(accepted):
        report += 'finding: ' + code + '\n'
    monitors = fields.get('monitors', ())
    if type(monitors) not in (tuple, list, set, frozenset):
        return DiagnosticResult('blocked', ('monitors_invalid',))
    if len(monitors) > MAX_MONITORS:
        return DiagnosticResult('blocked', ('item_limit',))
    rows = []
    for monitor in monitors:
        if type(monitor) is MonitorData:
            monitor = {'label': monitor.label, 'manufacturer': monitor.manufacturer,
                       'model': monitor.model, 'width': monitor.width,
                       'height': monitor.height, 'refresh_hz': monitor.refresh_hz}
        if not isinstance(monitor, Mapping):
            return DiagnosticResult('blocked', ('monitor_invalid',))
        label = monitor.get('label')
        if (type(label) is not str or len(label) > 48
                or re.fullmatch(r'edid:[0-9a-f]{12}…(?: \(Präfix mehrdeutig\))?', label) is None):
            return DiagnosticResult('blocked', ('monitor_label_invalid',))
        names = []
        for key, allowed in (('manufacturer', ('ACI', 'ASUS', 'Dell', 'HP', 'Samsung', '三星')),
                             ('model', ('VG248', 'E2417H', 'P2419H', 'U2415'))):
            value = monitor.get(key)
            if type(value) is str and len(value) <= 32 and value in allowed:
                names.append(value)
            else:
                names.append('unavailable')
                warnings.add('description_redacted')
        geometry = tuple(monitor.get(name) for name in ('width', 'height', 'refresh_hz'))
        suffix = ''
        if any(value is not None for value in geometry):
            if not all(type(value) is int and 1 <= value <= limit
                       for value, limit in zip(geometry, (16384, 16384, 360))):
                return DiagnosticResult('blocked', ('geometry_invalid',))
            suffix = ' ' + str(geometry[0]) + 'x' + str(geometry[1]) + '@' + str(geometry[2])
        rows.append((label, names[0], names[1], suffix))
    rendered = []
    for label, manufacturer, model, suffix in rows:
        if sum(other[0][:17] == label[:17] for other in rows) > 1 or label.endswith('(Präfix mehrdeutig)'):
            label = label[:18] + ' (Präfix mehrdeutig)'
            warnings.add('monitor_prefix_ambiguous')
        rendered.append('monitor: ' + label + ' ' + manufacturer + ' ' + model + suffix + '\n')
    report += ''.join(sorted(rendered))
    if report.count('\n') > MAX_REPORT_LINES:
        return DiagnosticResult('blocked', ('report_line_limit',))
    if len(report) > MAX_REPORT_CHARS:
        return DiagnosticResult('blocked', ('report_size_limit',))
    return DiagnosticResult('warning' if warnings else 'success', tuple(sorted(warnings)), report)
