"""Pure CLI planning over supplied ordinary Python data, never an entrypoint.

Syntax (explicit list/tuple of strings, no program-name prefix):
  preflight --monitor-edid SHA256
  plan --monitor-edid SHA256 --inner-width N --inner-height N
       --outer-width N --outer-height N --fps N -- CLIENT [ARG ...]
  --help

Plan sizes/FPS are mandatory; canonical positive ASCII decimal only, no signs,
leading zeros or whitespace correction. Bounds are enforced by build_argv.
Option order is free before --, names are exact, each is allowed once. After
the first -- every element is literal client data, including another --/@/$.
No response files, expansion, path search, output/printing or execution occurs.

The explicit full CLI hash supplies the requested role on a COPY of snapshot;
snapshot.gaming_edid_sha256 is a prior request, not measured display identity.
The separately supplied inventories must agree (order/description independent)
on full identities and current output addresses/flags. Preflight runs first,
then explicit resolution, then command, then environment. Existing preflight
program requirements remain unchanged; no extra program discovery is inferred.
Preflight never builds launch data or validates the environment/exposure input.
Those are checked only by the plan builders, and confer no runtime permission.

Only the selection prefix is retained in the resulting plan; it is a label,
never a lookup key. Full hashes, connectors, descriptions and snapshots are not
retained as monitor metadata. Opaque client/env payloads remain private to their
explicit fields and are never rendered. This is not a serialization/export API.
No runner import, executable bin script or operating-system adapter is present.
"""

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from collections.abc import Mapping
from .command import LaunchOptions, build_argv, build_child_env, WaylandSupport
from .preflight import evaluate_preflight
from .model import SessionSnapshot
from .outputs import outputs_are_valid, resolve_output


@dataclass(frozen=True)
class LaunchPlan:
    """Detached immutable payload; safe repr/summary without argv/env values.

    monitor_label is edid: + first 12 lowercase hex digits + …; prefix collisions
    are marked. It cannot identify a monitor for a future executable launcher.
    A future launch still needs fresh full-identity checks and its own approval.
    """
    argv: tuple[str, ...] = field(repr=False)
    child_env: Mapping[str, str] = field(repr=False)
    monitor_label: str
    backend: str = 'wayland'
    expose_wayland: WaylandSupport = WaylandSupport.SUPPORTED

    def __post_init__(self):
        object.__setattr__(self, 'argv', tuple(self.argv))
        object.__setattr__(self, 'child_env', MappingProxyType(dict(self.child_env)))

    @property
    def summary(self):
        return 'Nested-Wayland-Plan für ' + self.monitor_label + '; keine Ausführung.'


@dataclass(frozen=True)
class PlanningResult:
    """0 success, 2 argument/prerequisite refusal, 3 controlled internal failure.

    Nonblocking preflight warnings are preserved separately. No partial plan is
    returned on failure. Messages never interpolate unvalidated input values.
    """
    exit_code: int
    reasons: tuple[str, ...] = ()
    plan: LaunchPlan | None = None
    messages: tuple[str, ...] = ('Argument oder Voraussetzung blockiert; keine Planung verfügbar.',)
    warnings: tuple[str, ...] = ()

    @property
    def ok(self):
        return self.exit_code == 0

    @property
    def status(self):
        return 'success' if self.ok else 'blocked'


NUMERIC_OPTIONS = ('--inner-width', '--inner-height', '--outer-width', '--outer-height', '--fps')
HELP_TEXT = (
    'preflight --monitor-edid SHA256\n'
    'plan --monitor-edid SHA256 --inner-width N --inner-height N '
    '--outer-width N --outer-height N --fps N -- CLIENT [ARG ...]\n'
    'Nur Datenprüfung und Planung; keine Ausführung. Alle Planoptionen sind Pflicht.'
)


def _parse(argv):
    if (not isinstance(argv, (list, tuple)) or not argv
            or any(not isinstance(a, str) or '\0' in a for a in argv)):
        return PlanningResult(2, ('arguments_invalid',))
    if tuple(argv) == ('--help',):
        return PlanningResult(0, messages=(HELP_TEXT,))
    mode = argv[0]
    if mode not in ('preflight', 'plan'):
        return PlanningResult(2, ('mode_not_allowed',))
    delimiter = argv.index('--') if '--' in argv else len(argv)
    if mode == 'preflight' and delimiter != len(argv):
        return PlanningResult(2, ('preflight_client_not_allowed',))
    if mode == 'plan' and delimiter == len(argv):
        return PlanningResult(2, ('client_separator_missing',))
    header = argv[:delimiter]
    allowed = ('--monitor-edid',) + (NUMERIC_OPTIONS if mode == 'plan' else ())
    values = {}
    index = 1
    while index < len(header):
        name = header[index]
        if name not in allowed:
            return PlanningResult(2, ('option_unknown',))
        if name in values:
            return PlanningResult(2, ('option_duplicate',))
        if index + 1 >= len(header) or header[index + 1].startswith('--'):
            return PlanningResult(2, ('option_value_missing',))
        values[name] = header[index + 1]
        index += 2
    if set(values) != set(allowed):
        return PlanningResult(2, ('option_required',))
    for name in NUMERIC_OPTIONS if mode == 'plan' else ():
        value = values[name]
        if (not 1 <= len(value) <= 5 or not value.isascii()
                or not value.isdecimal() or value[0] == '0'):
            return PlanningResult(2, ('numeric_argument_invalid',))
    return mode, values, tuple(argv[delimiter + 1:])


def plan_cli(argv, snapshot, parent_env, expose_wayland, outputs):
    """Assess explicit data only. No sys.argv, global environment or host reads.

    Normal invalid arguments return 2. Unexpected pure-component exceptions,
    including SystemExit, return a fixed redacted 3; exception text is discarded.
    KeyboardInterrupt and other unrelated BaseExceptions are not swallowed.
    """
    try:
        return _plan(argv, snapshot, parent_env, expose_wayland, outputs)
    except (Exception, SystemExit):
        return PlanningResult(3, ('planning_failed',),
                              messages=('Interner Planungsfehler; keine Planung verfügbar.',))


def _plan(argv, snapshot, parent_env, expose_wayland, outputs):
    parsed = _parse(argv)
    if isinstance(parsed, PlanningResult):
        return parsed
    mode, values, client = parsed
    if not isinstance(snapshot, SessionSnapshot):
        return PlanningResult(2, ('snapshot_invalid',))
    current = replace(snapshot, gaming_edid_sha256=values['--monitor-edid'])
    preflight = evaluate_preflight(current)
    if preflight.ok and (not outputs_are_valid(outputs)
                         or set(outputs) != set(current.outputs)):
        return PlanningResult(2, ('inventory_mismatch',))
    if preflight.ok:
        monitor = resolve_output(outputs, values['--monitor-edid'])
        if not monitor.ok:
            return PlanningResult(2, ('monitor_blocked',))
    if mode == 'plan' and preflight.ok:
        options = LaunchOptions(client, *(int(values[name]) for name in NUMERIC_OPTIONS))
        command = build_argv(options, expose_wayland)
        if not command.ok:
            return PlanningResult(2, ('command_blocked',))
        environment = build_child_env(parent_env)
        if not environment.ok:
            return PlanningResult(2, ('environment_blocked',))
        label = 'edid:' + monitor.output.identity.edid_sha256[:12] + '…'
        prefix = monitor.output.identity.edid_sha256[:12]
        if sum(o.identity.edid_sha256 is not None and o.identity.edid_sha256.startswith(prefix)
               for o in outputs) > 1:
            label += ' (Präfix mehrdeutig)'
        plan = LaunchPlan(command.argv, environment.child_env, label)
        return PlanningResult(0, plan=plan, messages=(plan.summary,), warnings=preflight.warnings)
    return PlanningResult(0 if preflight.ok else 2, preflight.reasons,
                          messages=('Preflight ausgewertet; keine Ausführung.',),
                          warnings=preflight.warnings)
