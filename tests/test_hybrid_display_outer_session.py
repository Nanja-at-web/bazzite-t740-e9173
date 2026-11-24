"""Synthetic plan and wayland-utils 1.3 output contracts; no host probing."""
from pathlib import Path
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display import outer_session as session


def binaries():
    return tuple(session.Binary(path, True, True, False) for path in session.PROGRAMS)


def output_text(names=('DP-1', 'DP-2')):
    text = ''
    for index, name in enumerate(names, 41):
        text += (f"interface: 'wl_output', version: 4, name: {index}\n"
                 f"\tname: {name}\n\tdescription: synthetic display\n"
                 "\tx: 0, y: 0, scale: 1,\n"
                 "\tphysical_width: 500 mm, physical_height: 300 mm,\n"
                 "\tmake: 'SYN', model: 'fixture',\n"
                 "\tsubpixel_orientation: unknown, output_transform: normal,\n"
                 "\tmode:\n\t\twidth: 1920 px, height: 1080 px, refresh: 144.000 Hz,\n"
                 "\t\tflags: current preferred\n")
    text += "interface: 'zxdg_output_manager_v1', version: 3, name: 9\n"
    for index, name in enumerate(names, 41):
        text += (f"\txdg_output_v1\n\t\toutput: {index}\n\t\tname: '{name}'\n"
                 "\t\tdescription: 'synthetic display'\n"
                 f"\t\tlogical_x: {(index - 41) * 1920}, logical_y: 0\n"
                 "\t\tlogical_width: 1920, logical_height: 1080\n")
    return text.encode()


class SessionTests(unittest.TestCase):
    def test_parser_finalizes_incomplete_sections_at_interface_and_eof(self):
        valid = output_text()
        truncated_logical = valid + b"\txdg_output_v1\n\t\tname: 'DP-3'\n"
        truncated_mode = valid.replace(b"interface: 'zxdg_output_manager_v1'",
                                      b"\tmode:\n\t\tflags: preferred\ninterface: 'zxdg_output_manager_v1'")
        for raw in (truncated_logical, truncated_mode,
                    truncated_logical + b"interface: 'wl_shm', version: 1, name: 50\n"):
            with self.subTest(raw=raw[-80:]):
                self.assertFalse(session.parse_outputs(raw).ok)

    def test_overlapping_or_forged_output_geometry_cannot_authorize_gaming(self):
        plan = session.make_plan({}, binaries()).value
        outputs = session.parse_outputs(output_text()).value
        for change in ({'position': outputs[0].position}, {'size': (0, 1080)},
                       {'scale': True}, {'current_mode': (0, 1080, 144000)}):
            with self.subTest(change=change):
                bad = (outputs[0], replace(outputs[1], **change))
                self.assertFalse(session.select_outputs(plan, bad).ok)

    def test_service_starter_is_an_explicit_required_binary(self):
        self.assertIn('/usr/bin/systemd-run', session.PROGRAMS)
        missing = tuple(x for x in binaries() if x.path != '/usr/bin/systemd-run')
        self.assertFalse(session.make_plan({}, missing).ok)

    def test_only_fixed_own_user_service_cgroup_authorizes_execution(self):
        own = b'0::/user.slice/user-1000.slice/user@1000.service/app.slice/bazzite-hybrid-display-outer-kwin.service\n'
        self.assertTrue(session.service_membership(own, 1000))
        for raw in (own.replace(b'user-1000', b'user-1001'),
                    own.replace(b'outer-kwin.service', b'outer-kwin.scope'),
                    own.replace(b'outer-kwin.service', b'other.service'),
                    own.replace(b'outer-kwin.service', b'outer-kwin.service/foreign'),
                    own + own, b'', b'x' * 4097):
            self.assertFalse(session.service_membership(raw, 1000))

    def test_transient_service_has_closed_cgroup_cleanup_contract(self):
        argv = session.transient_argv()
        expected = ('/usr/bin/systemd-run', '--user', '--wait', '--collect',
                    '--service-type=exec', '--unit=bazzite-hybrid-display-outer-kwin',
                    '--property=KillMode=control-group', '--property=KillSignal=SIGTERM',
                    '--property=TimeoutStopSec=5s', '--property=SendSIGKILL=yes',
                    '--property=FinalKillSignal=SIGKILL', '--property=Restart=no',
                    '--property=ExitType=main', '--property=Delegate=no',
                    '--setenv=XDG_RUNTIME_DIR', '--setenv=XDG_SESSION_ID', '--setenv=XDG_SESSION_TYPE',
                    '--', '/usr/libexec/bazzite-hybrid-display-outer-kwin', '--execute')
        self.assertEqual(argv, expected)
        self.assertNotIn('--scope', argv)
        self.assertEqual(argv.count('--execute'), 1)

    def test_session_environment_accepts_only_required_named_values(self):
        valid = {'XDG_RUNTIME_DIR': '/run/user/1000', 'XDG_SESSION_ID': 'c3', 'XDG_SESSION_TYPE': 'wayland'}
        result = session.session_environment(valid, 1000)
        self.assertTrue(result.ok)
        self.assertEqual(result.value, (('/run/user/1000'), 'c3'))
        for update in ({'LD_PRELOAD': 'private'}, {'WAYLAND_DISPLAY': 'wayland-1'},
                       {'XDG_CONFIG_HOME': 'private'}, {'XDG_SESSION_ID': '../session'},
                       {'XDG_RUNTIME_DIR': '/run/user/1001'}, {'SSH_AUTH_SOCK': 'private'},
                       {'XDG_SESSION_TYPE': 'tty'}):
            result = session.session_environment(valid | update, 1000)
            self.assertFalse(result.ok)
            self.assertNotIn('private', repr(result))
        for values in ({}, {'XDG_SESSION_ID': 'c3'}, valid | {'XDG_SEAT': 'seat0'}):
            self.assertFalse(session.session_environment(values, 1000).ok)

    def test_wayland_utils_degree_transform_spelling(self):
        for transform in ('90°', '180°', '270°', 'flipped 90°'):
            parsed = session.parse_outputs(output_text().replace(
                b'output_transform: normal', ('output_transform: ' + transform).encode()))
            self.assertTrue(parsed.ok, transform)

    def test_valid_plan_is_immutable_default_dry_run(self):
        result = session.make_plan({}, binaries())
        self.assertTrue(result.ok)
        self.assertFalse(result.value.execute)
        self.assertEqual(result.value.gaming_output_name, 'DP-2')
        self.assertEqual(result.value.side_output_name, 'DP-1')
        with self.assertRaises(AttributeError):
            result.value.execute = True

    def test_names_and_configuration_are_closed(self):
        for change in ({'gaming_output_name': 'DP-1'}, {'gaming_output_name': '*'},
                       {'gaming_output_name': '../DP-2'}, {'unknown': 1},
                       {'payload': '/bin/sh'}, {'execute': 1},
                       {'inner_width': True}, {'outer_height': 100000}):
            with self.subTest(change=change):
                result = session.make_plan(change, binaries())
                self.assertFalse(result.ok)
                self.assertIsNone(result.value)

    def test_binary_receipts_are_exact_complete_and_absolute(self):
        for receipts in ((), binaries()[:-1], binaries() + (binaries()[0],),
                         tuple(session.Binary(x.path, False, True, False) for x in binaries()),
                         (session.Binary('gamescope', True, True, False),)):
            self.assertFalse(session.make_plan({}, receipts).ok)

    def test_callbacks_and_private_values_never_escape(self):
        calls = []
        class Trap(dict):
            def items(self):
                calls.append('items')
                raise RuntimeError('synthetic-private')
        result = session.make_plan(Trap(), binaries())
        self.assertFalse(result.ok)
        self.assertEqual(calls, [])
        self.assertNotIn('synthetic-private', repr(result))

    def check_bad_output(self, raw):
        result = session.parse_outputs(raw)
        self.assertFalse(result.ok)
        self.assertIsNone(result.value)
        self.assertEqual(result.reason, 'output_invalid')

    def test_two_outputs_and_name_selection_not_registry_index(self):
        plan = session.make_plan({}, binaries()).value
        for names in (('DP-1', 'DP-2'), ('DP-2', 'DP-1')):
            parsed = session.parse_outputs(output_text(names))
            self.assertTrue(parsed.ok)
            selected = session.select_outputs(plan, parsed.value)
            self.assertTrue(selected.ok)
            self.assertEqual(tuple(o.name for o in selected.value), ('DP-2', 'DP-1'))

    def test_zero_one_or_extra_outputs_block_atomically(self):
        for names in ((), ('DP-1',), ('DP-1', 'DP-2', 'DP-3')):
            self.check_bad_output(output_text(names))

    def test_duplicate_global_or_name(self):
        raw = output_text()
        self.check_bad_output(raw.replace(b"name: 42", b"name: 41"))
        self.check_bad_output(output_text(('DP-1', 'DP-1')))

    def test_missing_name_mode_scale_or_logical_geometry(self):
        raw = output_text()
        for old, new in ((b'\tname: DP-2\n', b''), (b'flags: current preferred', b'flags: preferred'),
                         (b'scale: 1', b'scale: 0'), (b'logical_width: 1920', b'logical_width: 0')):
            self.check_bad_output(raw.replace(old, new))

    def test_conflicting_unknown_and_repeated_fields(self):
        raw = output_text()
        for source in (raw.replace(b'\tname: DP-1', b'\tname: DP-1\n\tname: DP-2'),
                       raw.replace(b'logical_x: 0', b'unexpected: 0'),
                       raw.replace(b"\t\tname: 'DP-2'", b"\t\tname: 'DP-3'")):
            self.check_bad_output(source)

    def test_non_utf8_oversize_and_callback_bytes(self):
        self.check_bad_output(b'\xff')
        self.check_bad_output(b'x' * (262144 + 1))
        class Bytes(bytes):
            def decode(self, *args):
                raise AssertionError('callback')
        self.check_bad_output(Bytes(output_text()))

    def test_raw_description_not_retained(self):
        result = session.parse_outputs(output_text().replace(b'synthetic display', b'synthetic-private-description'))
        self.assertTrue(result.ok)
        self.assertNotIn('synthetic-private-description', repr(result))
        self.assertFalse(any(hasattr(o, 'description') for o in result.value))

    def test_missing_or_ambiguous_output_name_never_falls_back(self):
        plan = session.make_plan({}, binaries()).value
        for names in (('DP-1', 'HDMI-A-1'), ('DP-2', 'HDMI-A-1')):
            outputs = session.parse_outputs(output_text(names)).value
            result = session.select_outputs(plan, outputs)
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'output_invalid')
