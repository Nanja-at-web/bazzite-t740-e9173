"""Pure outer-session interfaces. No host lookup, process or display action."""
from dataclasses import dataclass, field
import re

PROGRAMS = ('/usr/bin/kwin_wayland', '/usr/bin/gamescope',
            '/usr/bin/steam', '/usr/bin/wayland-info', '/usr/bin/python3', '/usr/bin/systemd-run')


def transient_argv():
    """Static future SDDM entry; no manager request or environment lookup.

    StartTransientUnit atomically rejects any non-pristine named unit. This is
    the collision check, not a racy check-then-stop/replace sequence.
    """
    return ('/usr/bin/systemd-run', '--user', '--wait', '--collect',
            '--service-type=exec', '--unit=bazzite-hybrid-display-outer-kwin',
            '--property=KillMode=control-group', '--property=KillSignal=SIGTERM',
            '--property=TimeoutStopSec=5s', '--property=SendSIGKILL=yes',
            '--property=FinalKillSignal=SIGKILL', '--property=Restart=no',
            '--property=ExitType=main', '--property=Delegate=no',
            '--setenv=XDG_RUNTIME_DIR', '--setenv=XDG_SESSION_ID', '--setenv=XDG_SESSION_TYPE',
            '--', '/usr/libexec/bazzite-hybrid-display-outer-kwin', '--execute')


def session_environment(values, uid):
    if (type(values) is not dict or len(values) != 3 or type(uid) is not int
            or not 1 <= uid <= 2147483647
            or any(type(k) is not str or k not in ('XDG_RUNTIME_DIR', 'XDG_SESSION_ID', 'XDG_SESSION_TYPE') for k in values)):
        return Result(reason='config_invalid')
    runtime, session = values.get('XDG_RUNTIME_DIR'), values.get('XDG_SESSION_ID')
    kind = values.get('XDG_SESSION_TYPE')
    if (type(runtime) is not str or runtime != '/run/user/' + str(uid)
            or type(session) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', session) is None
            or type(kind) is not str or kind != 'wayland'):
        return Result(reason='config_invalid')
    return Result((runtime, session))


def service_membership(raw, uid):
    if type(raw) is not bytes or not 1 <= len(raw) <= 4096 or type(uid) is not int or not 1 <= uid <= 2147483647:
        return False
    prefix = ('0::/user.slice/user-' + str(uid) + '.slice/user@' + str(uid) + '.service/').encode('ascii')
    suffix = b'bazzite-hybrid-display-outer-kwin.service\n'
    return raw in (prefix + suffix, prefix + b'app.slice/' + suffix)


@dataclass(frozen=True, slots=True, repr=False)
class Binary:
    path: str
    executable: bool
    trusted_owner: bool
    writable: bool


@dataclass(frozen=True, slots=True)
class Result:
    value: object = field(default=None, repr=False)
    reason: str = ''

    @property
    def ok(self):
        return self.value is not None and not self.reason


@dataclass(frozen=True, slots=True, repr=False)
class Plan:
    gaming_output_name: str = 'DP-2'
    side_output_name: str = 'DP-1'
    inner_width: int = 1280
    inner_height: int = 720
    outer_width: int = 1280
    outer_height: int = 720
    execute: bool = False


def make_plan(config, binaries):
    if type(config) is not dict or len(config) > 7:
        return Result(reason='config_invalid')
    defaults = {'gaming_output_name': 'DP-2', 'side_output_name': 'DP-1',
                'inner_width': 1280, 'inner_height': 720,
                'outer_width': 1280, 'outer_height': 720, 'execute': False}
    if any(type(key) is not str or key not in defaults for key in config):
        return Result(reason='config_invalid')
    defaults.update(config)
    for name in ('gaming_output_name', 'side_output_name'):
        value = defaults[name]
        if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}', value) is None:
            return Result(reason='config_invalid')
    if defaults['gaming_output_name'] == defaults['side_output_name']:
        return Result(reason='config_invalid')
    if type(defaults['execute']) is not bool:
        return Result(reason='config_invalid')
    for name in ('inner_width', 'inner_height', 'outer_width', 'outer_height'):
        if type(defaults[name]) is not int or not 64 <= defaults[name] <= 4096:
            return Result(reason='config_invalid')
    if type(binaries) is not tuple or len(binaries) != len(PROGRAMS):
        return Result(reason='binary_invalid')
    seen = set()
    for item in binaries:
        if (type(item) is not Binary or type(item.path) is not str
                or item.path not in PROGRAMS or item.path in seen
                or item.executable is not True or item.trusted_owner is not True
                or item.writable is not False):
            return Result(reason='binary_invalid')
        seen.add(item.path)
    return Result(Plan(**defaults))


def valid_plan(plan):
    if type(plan) is not Plan:
        return False
    values = {k: getattr(plan, k) for k in ('gaming_output_name', 'side_output_name',
              'inner_width', 'inner_height', 'outer_width', 'outer_height', 'execute')}
    return make_plan(values, tuple(Binary(p, True, True, False) for p in PROGRAMS)).ok


@dataclass(frozen=True, slots=True, repr=False)
class Output:
    global_id: int
    name: str
    position: tuple
    size: tuple
    scale: int
    transform: str
    current_mode: tuple


def parse_outputs(raw):
    """Strict wayland-utils 1.3.0 output subset; discard all unneeded data.

    Descriptions/make/model are syntax-checked then discarded. Globals of other
    protocols are not facts and are never returned. No registry-index placement.
    """
    if type(raw) is not bytes or len(raw) > 262144:
        return Result(reason='output_invalid')
    try:
        text = raw.decode('utf-8', errors='strict')
        return _parse(text)
    except (UnicodeError, ValueError, KeyError, IndexError):
        return Result(reason='output_invalid')


def _number(text, low=-100000, high=100000):
    if len(text) > 8 or re.fullmatch(r'-?[0-9]+', text) is None:
        raise ValueError()
    value = int(text)
    if not low <= value <= high:
        raise ValueError()
    return value


def _put(mapping, key, value):
    if key in mapping:
        raise ValueError()
    mapping[key] = value


def _parse(text):
    if '\0' in text or len(text.splitlines()) > 8192:
        raise ValueError()
    records, logical, globals_seen = {}, {}, set()
    section, record, xdg, mode = '', None, None, None
    def finalize():
        if mode is not None and set(mode) != {'size', 'flags'}:
            raise ValueError()
        if xdg is not None and not {'id', 'name', 'position', 'size'} <= set(xdg):
            raise ValueError()
    for line in text.splitlines():
        if len(line) > 2048:
            raise ValueError()
        if not line.strip():
            continue
        match = re.fullmatch(r"interface: '([A-Za-z0-9_]+)',\s+version:\s+([0-9]+), name:\s+([0-9]+)", line)
        if match:
            finalize()
            section = match[1]
            ident = _number(match[3], 1, 100000)
            if ident in globals_seen or len(globals_seen) >= 512:
                raise ValueError()
            globals_seen.add(ident)
            record, xdg, mode = None, None, None
            if section == 'wl_output':
                if not 4 <= _number(match[2], 1, 100) <= 4 or len(records) >= 2:
                    raise ValueError()
                record = {'id': ident, 'modes': []}
                records[ident] = record
            continue
        if not line.startswith(('\t', ' ')) or not section:
            raise ValueError()
        if section == 'wl_output':
            if line.startswith('\tname: '):
                value = line[7:]
                if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}', value) is None:
                    raise ValueError()
                _put(record, 'name', value)
            elif re.fullmatch(r'\tdescription: [^\x00-\x1f]{1,256}', line):
                _put(record, 'description_seen', True)
            elif (m := re.fullmatch(r'\tx: (-?[0-9]+), y: (-?[0-9]+), scale: ([0-9]+),', line)):
                _put(record, 'position', (_number(m[1]), _number(m[2])))
                _put(record, 'scale', _number(m[3], 1, 8))
            elif re.fullmatch(r'\tphysical_width: [0-9]{1,4} mm, physical_height: [0-9]{1,4} mm,', line):
                _put(record, 'physical_seen', True)
            elif re.fullmatch(r"\tmake: '[^'\x00-\x1f]{0,128}', model: '[^'\x00-\x1f]{0,128}',", line):
                _put(record, 'make_seen', True)
            elif (m := re.fullmatch(r'\tsubpixel_orientation: (unknown|none|horizontal rgb|horizontal bgr|vertical rgb|vertical bgr), output_transform: ([^,]+),', line)):
                if m[2] not in ('normal', '90°', '180°', '270°', 'flipped', 'flipped 90°', 'flipped 180°', 'flipped 270°'):
                    raise ValueError()
                _put(record, 'transform', m[2])
            elif line == '\tmode:':
                if mode is not None and set(mode) != {'size', 'flags'}:
                    raise ValueError()
                mode = {}
                record['modes'].append(mode)
                if len(record['modes']) > 128:
                    raise ValueError()
            elif (m := re.fullmatch(r'\t\twidth: ([0-9]+) px, height: ([0-9]+) px, refresh: ([0-9]+)\.([0-9]{3}) Hz,', line)):
                if mode is None:
                    raise ValueError()
                _put(mode, 'size', (_number(m[1], 1, 16384), _number(m[2], 1, 16384),
                                   _number(m[3], 0, 1000) * 1000 + int(m[4])))
            elif (m := re.fullmatch(r'\t\tflags:((?: current)?(?: preferred)?)', line)):
                if mode is None:
                    raise ValueError()
                _put(mode, 'flags', m[1].split())
            else:
                raise ValueError()
        elif section == 'zxdg_output_manager_v1':
            if line == '\txdg_output_v1':
                finalize()
                xdg = {}
            elif (m := re.fullmatch(r'\t\toutput: ([0-9]+)', line)):
                if xdg is None:
                    raise ValueError()
                ident = _number(m[1], 1, 100000)
                _put(xdg, 'id', ident)
                _put(logical, ident, xdg)
            elif (m := re.fullmatch(r"\t\tname: '([A-Za-z0-9][A-Za-z0-9_-]{0,31})'", line)):
                if xdg is None:
                    raise ValueError()
                _put(xdg, 'name', m[1])
            elif re.fullmatch(r"\t\tdescription: '[^'\x00-\x1f]{1,256}'", line):
                if xdg is None:
                    raise ValueError()
                _put(xdg, 'description_seen', True)
            elif (m := re.fullmatch(r'\t\tlogical_x: (-?[0-9]+), logical_y: (-?[0-9]+)', line)):
                if xdg is None:
                    raise ValueError()
                _put(xdg, 'position', (_number(m[1]), _number(m[2])))
            elif (m := re.fullmatch(r'\t\tlogical_width: ([0-9]+), logical_height: ([0-9]+)', line)):
                if xdg is None:
                    raise ValueError()
                _put(xdg, 'size', (_number(m[1], 1, 16384), _number(m[2], 1, 16384)))
            else:
                raise ValueError()
    finalize()
    if len(records) != 2 or set(records) != set(logical):
        raise ValueError()
    outputs = []
    for ident, item in records.items():
        other = logical[ident]
        if not {'name', 'scale', 'transform', 'position', 'physical_seen', 'make_seen'} <= set(item):
            raise ValueError()
        if not {'id', 'name', 'position', 'size'} <= set(other) or item['name'] != other['name']:
            raise ValueError()
        current = [m['size'] for m in item['modes'] if 'current' in m['flags']]
        if len(current) != 1 or current[0][2] <= 0:
            raise ValueError()
        outputs.append(Output(ident, item['name'], other['position'], other['size'],
                              item['scale'], item['transform'], current[0]))
    if len({o.name for o in outputs}) != 2:
        raise ValueError()
    return Result(tuple(outputs))


def select_outputs(plan, outputs):
    if not valid_plan(plan) or type(outputs) is not tuple or len(outputs) != 2:
        return Result(reason='output_invalid')
    if any(type(o) is not Output for o in outputs):
        return Result(reason='output_invalid')
    for item in outputs:
        if (type(item.position) is not tuple or len(item.position) != 2
                or any(type(n) is not int or not -65536 <= n <= 65536 for n in item.position)
                or type(item.size) is not tuple or len(item.size) != 2
                or any(type(n) is not int or not 1 <= n <= 16384 for n in item.size)
                or type(item.scale) is not int or not 1 <= item.scale <= 8
                or type(item.current_mode) is not tuple or len(item.current_mode) != 3
                or any(type(n) is not int or n <= 0 for n in item.current_mode)):
            return Result(reason='output_invalid')
    a, b = outputs
    if not (a.position[0] + a.size[0] <= b.position[0] or b.position[0] + b.size[0] <= a.position[0]
            or a.position[1] + a.size[1] <= b.position[1] or b.position[1] + b.size[1] <= a.position[1]):
        return Result(reason='output_invalid')
    names = [o.name for o in outputs]
    if any(type(n) is not str for n in names) or len(set(names)) != 2:
        return Result(reason='output_invalid')
    if set(names) != {plan.gaming_output_name, plan.side_output_name}:
        return Result(reason='output_invalid')
    return Result(tuple(next(o for o in outputs if o.name == name)
                        for name in (plan.gaming_output_name, plan.side_output_name)))
