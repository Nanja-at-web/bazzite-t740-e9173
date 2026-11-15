"""Pure CLI planning over synthetic arguments, snapshots and mappings."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype/hybrid-display/src'))

from hybrid_display import cli
from hybrid_display.command import WaylandSupport, ArgvResult, EnvironmentResult
from hybrid_display.model import OutputIdentity, Output, SessionSnapshot

HASH_A = 'ab' * 32
HASH_B = 'cd' * 32


def output(digest=HASH_A, name='DP-1', **changes):
    return replace(Output(OutputIdentity(digest, 'synthetic', 'monitor'),
                          'synthetic-gpu', name, name, True, False, True), **changes)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.outputs = (output(), output(HASH_B, 'DP-2'))
        self.snapshot = SessionSnapshot('wayland', 'KDE', True, True, self.outputs,
                                        (), False, False, frozenset({'gamescope', 'vkcube'}))
        self.argv = ['preflight', '--monitor-edid', HASH_A]
        self.parent = {'LANG': 'C'}

    def call(self, **changes):
        arguments = dict(argv=self.argv, snapshot=self.snapshot, outputs=self.outputs,
                         parent_env=self.parent, expose_wayland=WaylandSupport.SUPPORTED)
        arguments.update(changes)
        return cli.plan_cli(**arguments)

    def plan_args(self, client=('synthetic-client',)):
        return ['plan', '--monitor-edid', HASH_A, '--inner-width', '1920',
                '--inner-height', '1080', '--outer-width', '1920',
                '--outer-height', '1080', '--fps', '60', '--', *client]

    def test_preflight_success_returns_no_launch_plan(self):
        result = self.call()
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.reasons, ())
        self.assertIsNone(result.plan)


    def test_preflight_rejects_failed_session_prerequisites_without_builders(self):
        cases = (dict(session_type='tty'), dict(session_type='x11'),
                 dict(desktop='gamescope'), dict(kwin_running=False),
                 dict(outputs=self.outputs[:1]),
                 dict(outputs=(output(mirrored=True), self.outputs[1])),
                 dict(existing_clients=('steam',)), dict(existing_clients=('gamescope',)),
                 dict(focus_service_active=True), dict(capabilities=frozenset()),
                 dict(decky_active=True))
        for changes in cases:
            current = replace(self.snapshot, **changes)
            result = self.call(snapshot=current, outputs=current.outputs)
            self.assertEqual(result.exit_code, 2)
            self.assertFalse(result.ok)
            self.assertTrue(result.reasons)
            self.assertIsNone(result.plan)


    def test_execution_and_unknown_modes_are_rejected(self):
        for mode in ('run', 'start', 'launch', 'unknown', 'PLAN'):
            result = self.call(argv=[mode, '--monitor-edid', HASH_A])
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.reasons, ('mode_not_allowed',))
            self.assertIsNone(result.plan)


    def test_missing_or_wrong_typed_argument_sequences_are_structured(self):
        for argv in (None, [], (), 'preflight --monitor-edid value', b'preflight',
                     1, {'mode': 'preflight'}, ['preflight', True], ['preflight', None]):
            try:
                result = self.call(argv=argv)
            except (Exception, SystemExit):
                self.fail('Argument data must be rejected without parser exceptions')
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)


    def test_unknown_options_and_extra_operands_are_not_ignored(self):
        for argv in (['preflight', '--monitor', HASH_A],
                     self.argv + ['--unknown', 'private'],
                     self.argv + ['extra'], self.argv + ['--inner-width', '1920']):
            result = self.call(argv=argv)
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)


    def test_missing_or_non_snapshot_data_is_blocked_without_exception(self):
        for snapshot in (None, {}, 'private', SessionSnapshot()):
            try:
                result = self.call(snapshot=snapshot)
            except (Exception, SystemExit):
                self.fail('Malformed snapshots need structured refusal')
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)


    def test_explicit_inventory_must_match_snapshot_without_order_dependency(self):
        for outputs in ((), None, (output(),), (output(enabled=False), self.outputs[1]),
                        (output(name='DP-9'), self.outputs[1])):
            result = self.call(outputs=outputs)
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)
        self.assertTrue(self.call(outputs=tuple(reversed(self.outputs))).ok)


    def test_preflight_explicitly_resolves_monitor_without_building_launch_data(self):
        events = []
        original = cli.resolve_output
        def resolve(values, digest):
            events.append(('monitor', digest))
            return original(values, digest)
        with patch.object(cli, 'resolve_output', side_effect=resolve):
            result = self.call()
        self.assertTrue(result.ok)
        self.assertEqual(events, [('monitor', HASH_A)])
        self.assertIsNone(result.plan)


    def test_successful_plan_contains_fixed_nested_command_and_no_execution(self):
        result = self.call(argv=self.plan_args())
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.argv, (
            'gamescope', '--backend', 'wayland', '--expose-wayland',
            '-w', '1920', '-h', '1080', '-W', '1920', '-H', '1080',
            '-r', '60', '--', 'synthetic-client'))
        self.assertEqual(dict(result.plan.child_env), {'LANG': 'C'})
        self.assertEqual(result.plan.backend, 'wayland')
        self.assertIs(result.plan.expose_wayland, WaylandSupport.SUPPORTED)


    def test_unsupported_or_unknown_capability_blocks_without_partial_plan(self):
        for capability in (WaylandSupport.UNKNOWN, WaylandSupport.UNSUPPORTED, None, True, 'supported'):
            try:
                result = self.call(argv=self.plan_args(), expose_wayland=capability)
            except (Exception, SystemExit):
                self.fail('Blocked command must not become a partial plan or exception')
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.reasons, ('command_blocked',))
            self.assertIsNone(result.plan)


    def test_blocked_environment_never_yields_partial_plan(self):
        for parent in (None, [], {'LANG': 'private\0'}, {'LANG': 1}, {'BAD=KEY': 'private'}):
            try:
                result = self.call(argv=self.plan_args(), parent_env=parent)
            except (Exception, SystemExit):
                self.fail('Blocked environment must not become a partial plan or exception')
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.reasons, ('environment_blocked',))
            self.assertIsNone(result.plan)


    def test_plan_rejects_unknown_and_duplicate_options(self):
        good = self.plan_args()
        for argv in (good[:13] + ['--unknown', 'private'] + good[13:],
                     good[:13] + ['--fps', '60'] + good[13:],
                     good[:13] + ['--monitor-edid', HASH_A] + good[13:],
                     ['plan', '--monitor-edid', HASH_A, '--unknown', '1920',
                      *good[5:]]):
            try:
                result = self.call(argv=argv)
            except (Exception, SystemExit):
                self.fail('Unknown or duplicate options must block structurally')
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)


    def test_numeric_values_are_strict_bounded_and_never_corrected(self):
        for option in ('--inner-width', '--inner-height', '--outer-width', '--outer-height', '--fps'):
            for value in ('+60', '060', ' 60', '60 ', '0', '-1', 'True', '60.0',
                          'NaN', 'inf', '', '９', '9' * 5000, True, 60, None):
                argv = self.plan_args()
                argv[argv.index(option) + 1] = value
                try:
                    result = self.call(argv=argv)
                except (Exception, SystemExit):
                    self.fail('Invalid numeric values need structured refusal')
                self.assertEqual(result.exit_code, 2)
                self.assertIsNone(result.plan)
        for option, value in (('--inner-width', '16385'), ('--fps', '361')):
            argv = self.plan_args()
            argv[argv.index(option) + 1] = value
            self.assertFalse(self.call(argv=argv).ok)


    def test_help_is_constant_and_needs_no_input_snapshot_or_environment(self):
        result = self.call(argv=['--help'], snapshot=None, outputs=None,
                           parent_env={'TOKEN': 'synthetic-secret'}, expose_wayland=None)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.ok)
        self.assertIsNone(result.plan)
        self.assertEqual(result.messages, (cli.HELP_TEXT,))
        self.assertNotIn('synthetic-secret', repr(result))
        self.assertIn('preflight --monitor-edid SHA256', result.messages[0])
        self.assertIn('plan --monitor-edid SHA256', result.messages[0])


    def test_launch_plan_has_only_short_monitor_label_and_redacted_summary(self):
        result = self.call(argv=self.plan_args())
        self.assertTrue(result.ok)
        plan = result.plan
        self.assertTrue(hasattr(plan, 'monitor_label'), 'Plan needs a redacted monitor label')
        self.assertEqual(plan.monitor_label, 'edid:abababababab…')
        self.assertNotIn(HASH_A, repr(result))
        self.assertNotIn(HASH_A, repr(plan))
        self.assertNotIn(HASH_A, plan.summary)
        self.assertIn('edid:abababababab…', plan.summary)
        self.assertNotIn('DP-1', repr(plan))
        self.assertNotIn('synthetic-client', plan.summary)


    def test_colliding_short_labels_are_marked_and_never_used_for_selection(self):
        collision = HASH_A[:12] + 'ef' * 26
        outputs = (output(), output(collision, 'DP-2'))
        result = self.call(argv=self.plan_args(),
                           snapshot=replace(self.snapshot, outputs=outputs), outputs=outputs)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.monitor_label, 'edid:abababababab… (Präfix mehrdeutig)')
        short = self.plan_args()
        short[2] = HASH_A[:12]
        self.assertFalse(self.call(argv=short).ok)


    def test_internal_component_exceptions_are_controlled_and_redacted(self):
        for exception in (RuntimeError('synthetic-private-failure'), SystemExit('synthetic-private-failure')):
            with patch.object(cli, 'build_argv', side_effect=exception):
                try:
                    result = self.call(argv=self.plan_args())
                except (Exception, SystemExit):
                    self.fail('Internal planning error must become exit code 3')
            self.assertEqual(result.exit_code, 3)
            self.assertEqual(result.reasons, ('planning_failed',))
            self.assertIsNone(result.plan)
            self.assertNotIn('synthetic-private', repr(result))


    def test_wrong_component_return_type_is_internal_error_not_success(self):
        with patch.object(cli, 'build_argv', return_value=EnvironmentResult({})):
            result = self.call(argv=self.plan_args())
        self.assertEqual(result.exit_code, 3)
        self.assertIsNone(result.plan)
        with patch.object(cli, 'build_child_env', return_value=ArgvResult(('client',))):
            result = self.call(argv=self.plan_args())
        self.assertEqual(result.exit_code, 3)
        self.assertIsNone(result.plan)
        with patch.object(cli, 'evaluate_preflight', return_value=ArgvResult(('client',))):
            result = self.call()
        self.assertEqual(result.exit_code, 3)
        self.assertIsNone(result.plan)


    def test_preflight_never_calls_command_or_environment_builders(self):
        for snapshot in (self.snapshot, replace(self.snapshot, session_type='tty')):
            with patch.object(cli, 'build_argv', side_effect=AssertionError('forbidden builder')) as command:
                with patch.object(cli, 'build_child_env', side_effect=AssertionError('forbidden builder')) as env:
                    result = self.call(snapshot=snapshot, parent_env=None, expose_wayland=None)
            self.assertEqual(result.exit_code, 0 if snapshot.session_type == 'wayland' else 2)
            self.assertIsNone(result.plan)
            self.assertEqual(command.call_count, 0)
            self.assertEqual(env.call_count, 0)

    def test_real_components_are_called_in_order_only_after_successful_preflight(self):
        events = []
        names = ('evaluate_preflight', 'resolve_output', 'build_argv', 'build_child_env')
        originals = {name: getattr(cli, name) for name in names}
        def wrapper(name):
            def wrapped(*args):
                events.append(name)
                return originals[name](*args)
            return wrapped
        with patch.object(cli, names[0], side_effect=wrapper(names[0])):
            with patch.object(cli, names[1], side_effect=wrapper(names[1])):
                with patch.object(cli, names[2], side_effect=wrapper(names[2])):
                    with patch.object(cli, names[3], side_effect=wrapper(names[3])):
                        result = self.call(argv=self.plan_args())
        self.assertTrue(result.ok)
        self.assertEqual(events, list(names))
        self.assertEqual(result.plan.argv[-1], 'synthetic-client')

    def test_failed_preflight_short_circuits_all_later_components(self):
        with patch.object(cli, 'resolve_output') as monitor:
            with patch.object(cli, 'build_argv') as command:
                with patch.object(cli, 'build_child_env') as env:
                    result = self.call(argv=self.plan_args(),
                                       snapshot=replace(self.snapshot, session_type='tty'))
        self.assertEqual(result.exit_code, 2)
        self.assertIsNone(result.plan)
        self.assertEqual([monitor.call_count, command.call_count, env.call_count], [0, 0, 0])

    def test_blocked_command_short_circuits_environment_and_hides_reason_payload(self):
        with patch.object(cli, 'build_argv', return_value=ArgvResult(reasons=('synthetic-private',))):
            with patch.object(cli, 'build_child_env') as env:
                result = self.call(argv=self.plan_args())
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.reasons, ('command_blocked',))
        self.assertIsNone(result.plan)
        self.assertEqual(env.call_count, 0)
        self.assertNotIn('synthetic-private', repr(result))

    def test_blocked_environment_has_no_plan_or_reason_payload(self):
        with patch.object(cli, 'build_child_env', return_value=EnvironmentResult(reasons=('synthetic-private',))):
            result = self.call(argv=self.plan_args())
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.reasons, ('environment_blocked',))
        self.assertIsNone(result.plan)
        self.assertNotIn('synthetic-private', repr(result))

    def test_monitor_identity_rejects_connector_prefix_missing_and_duplicate_hashes(self):
        for choice in ('DP-1', HASH_A[:12], '', 'g' * 64, 'ef' * 32):
            self.assertFalse(self.call(argv=['preflight', '--monitor-edid', choice]).ok)
        outputs = (output(), output(HASH_A, 'DP-2'))
        result = self.call(snapshot=replace(self.snapshot, outputs=outputs), outputs=outputs)
        self.assertFalse(result.ok)
        self.assertIn('selection_ambiguous', result.reasons)
        outputs = (output(enabled=False), self.outputs[1], output('ef' * 32, 'DP-3'))
        result = self.call(snapshot=replace(self.snapshot, outputs=outputs), outputs=outputs)
        self.assertFalse(result.ok)
        self.assertIn('selected_output_disabled', result.reasons)

    def test_full_hash_case_and_connector_rename_do_not_change_monitor_role(self):
        args = self.plan_args()
        args[2] = HASH_B.upper()
        result = self.call(argv=args)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.monitor_label, 'edid:cdcdcdcdcdcd…')
        outputs = (output(name='DP-9'), self.outputs[1])
        renamed = self.call(argv=self.plan_args(),
                            snapshot=replace(self.snapshot, outputs=outputs), outputs=outputs)
        self.assertTrue(renamed.ok)
        self.assertEqual(renamed.plan.monitor_label, 'edid:abababababab…')

    def test_all_plan_options_are_required_and_missing_values_block(self):
        full = self.plan_args()
        for option in ('--monitor-edid', '--inner-width', '--inner-height',
                       '--outer-width', '--outer-height', '--fps'):
            index = full.index(option)
            for remove in (1, 2):
                argv = full[:index] + full[index + remove:]
                result = self.call(argv=argv)
                self.assertEqual(result.exit_code, 2)
                self.assertIsNone(result.plan)

    def test_duplicate_preflight_option_and_equals_abbreviations_are_rejected(self):
        for argv in (self.argv + ['--monitor-edid', HASH_A],
                     ['preflight', '--monitor-edid=' + HASH_A],
                     ['preflight', '--monitor-e', HASH_A]):
            self.assertEqual(self.call(argv=argv).exit_code, 2)

    def test_distinct_resolutions_and_reordered_options_remain_exact(self):
        args = ['plan', '--fps', '120', '--outer-height', '1440', '--inner-height', '720',
                '--monitor-edid', HASH_A, '--outer-width', '2560', '--inner-width', '1280',
                '--', 'synthetic-client']
        result = self.call(argv=args)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.argv, (
            'gamescope', '--backend', 'wayland', '--expose-wayland', '-w', '1280',
            '-h', '720', '-W', '2560', '-H', '1440', '-r', '120', '--', 'synthetic-client'))

    def test_client_boundaries_shell_syntax_and_responsefile_text_are_literal(self):
        client = ('client with spaces', 'two words', '"quoted"', "'single'", ';',
                  '$(not-executed)', '`literal`', '&&', '@not-a-responsefile', '$HOME',
                  '', '--help', '--monitor-edid', 'literal')
        result = self.call(argv=self.plan_args(client))
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.argv[15:], client)
        self.assertEqual(result.plan.argv[14], '--')
        self.assertNotIn('client with spaces', result.plan.summary)
        self.assertEqual(self.call(argv=['@not-a-responsefile']).exit_code, 2)

    def test_empty_client_missing_separator_or_nul_are_blocked(self):
        for argv in (self.plan_args(())[0:-1], self.plan_args(()),
                     self.plan_args(('',)), self.plan_args((' ',)),
                     self.plan_args(('client', 'x\0y')),
                     self.plan_args(('client', 1))):
            self.assertEqual(self.call(argv=argv).exit_code, 2)
        self.assertEqual(self.call(argv=self.argv + ['--', 'client']).exit_code, 2)

    def test_help_with_extra_arguments_is_not_a_bypass(self):
        for argv in (['--help', 'synthetic-private'], self.argv + ['--help'],
                     ['plan', '--help']):
            result = self.call(argv=argv)
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)
            self.assertNotIn('synthetic-private', repr(result))


    def test_blocked_results_include_fixed_redacted_cli_message(self):
        result = self.call(argv=['run', '--monitor-edid', HASH_A, 'synthetic-private'])
        self.assertEqual(result.exit_code, 2)
        self.assertTrue(result.messages, 'Blocked result needs safe user-facing guidance')
        self.assertNotIn('synthetic-private', repr(result))
        self.assertNotIn(HASH_A, repr(result))


    def test_launch_plan_and_inputs_remain_detached_and_immutable(self):
        args = self.plan_args(('client', 'original'))
        before_args, before_parent = args.copy(), self.parent.copy()
        before_snapshot, before_outputs = self.snapshot, self.outputs
        first = self.call(argv=args)
        second = self.call(argv=tuple(args))
        self.assertEqual(first, second)
        self.assertEqual(args, before_args)
        self.assertEqual(self.parent, before_parent)
        self.assertEqual(self.snapshot, before_snapshot)
        self.assertEqual(self.outputs, before_outputs)
        self.assertIsNone(self.snapshot.gaming_edid_sha256)
        args[-1] = 'changed'
        self.parent['LANG'] = 'changed'
        self.assertEqual(first.plan.argv[-1], 'original')
        self.assertEqual(dict(first.plan.child_env), {'LANG': 'C'})
        self.assertIsInstance(first.plan.argv, tuple)
        with self.assertRaises(FrozenInstanceError):
            first.plan.backend = 'drm'
        with self.assertRaises(TypeError):
            first.plan.child_env['LANG'] = 'changed'
        with self.assertRaises(FrozenInstanceError):
            first.exit_code = 2

    def test_all_sensitive_environment_classes_are_omitted_from_public_output(self):
        names = ('TOKEN', 'SECRET', 'PASSWORD', 'COOKIE', 'CREDENTIAL',
                 'AWS_ACCESS_KEY_ID', 'GH_TOKEN', 'GITHUB_TOKEN', 'SSH_AUTH_SOCK',
                 'STEAM_WEB_COOKIE', 'STEAM_ACCOUNT_PASSWORD',
                 'LANG_TOKEN', 'XDG_RUNTIME_DIR_SECRET')
        for index, name in enumerate(names):
            value = 'synthetic-private-value-' + str(index)
            parent = {'LANG': 'C', name: value}
            result = self.call(argv=self.plan_args(('client', value)), parent_env=parent)
            self.assertTrue(result.ok)
            self.assertEqual(dict(result.plan.child_env), {'LANG': 'C'})
            self.assertEqual(result.plan.argv[-1], value)
            for text in (repr(result), repr(result.plan), str(result.messages),
                         str(result.reasons), result.plan.summary, cli.HELP_TEXT):
                self.assertNotIn(value, text)
                self.assertNotIn(HASH_A, text)

    def test_allowed_environment_and_monitor_descriptions_are_not_printed(self):
        secret = 'synthetic-private-description'
        outputs = (replace(output(), identity=OutputIdentity(HASH_A, secret, secret)), self.outputs[1])
        result = self.call(argv=self.plan_args(('client', secret)), parent_env={'LANG': secret},
                           snapshot=replace(self.snapshot, outputs=outputs), outputs=outputs)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.child_env['LANG'], secret)
        for text in (repr(result), repr(result.plan), str(result.messages), result.plan.summary):
            self.assertNotIn(secret, text)
            self.assertNotIn(HASH_A, text)
        self.assertFalse(hasattr(result.plan, 'pid'))
        self.assertFalse(hasattr(result.plan, 'handle'))
        self.assertFalse(hasattr(result.plan, 'edid_sha256'))
        self.assertFalse(hasattr(result.plan, 'drm_connector'))

    def test_error_paths_never_echo_arguments_environment_or_snapshot(self):
        secret = 'synthetic-private-error-input'
        cases = (
            dict(argv=['preflight', '--monitor-edid', secret]),
            dict(argv=self.plan_args(('client', secret)), parent_env={'LANG': secret + '\0'}),
            dict(argv=['preflight', '--' + secret, secret]),
            dict(snapshot=replace(self.snapshot, desktop=secret)),
        )
        for changes in cases:
            result = self.call(**changes)
            self.assertEqual(result.exit_code, 2)
            self.assertIsNone(result.plan)
            self.assertNotIn(secret, repr(result))
            self.assertNotIn(secret, str(result.messages))
            self.assertNotIn(secret, str(result.reasons))

    def test_warning_is_preserved_without_inventing_monitor_description(self):
        outputs = (replace(output(), identity=OutputIdentity(HASH_A)), self.outputs[1])
        snapshot = replace(self.snapshot, outputs=outputs)
        for argv in (self.argv, self.plan_args()):
            result = self.call(argv=argv, snapshot=snapshot, outputs=outputs)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.warnings, ('monitor_description_missing',))

    def test_actual_builders_accept_boundary_values_without_inventing_defaults(self):
        for size, fps in (('1', '1'), ('16384', '360')):
            args = self.plan_args()
            for option in ('--inner-width', '--inner-height', '--outer-width', '--outer-height'):
                args[args.index(option) + 1] = size
            args[args.index('--fps') + 1] = fps
            result = self.call(argv=args, parent_env={})
            self.assertTrue(result.ok)
            self.assertEqual(result.plan.argv[5], size)
            self.assertEqual(result.plan.argv[13], fps)
            self.assertEqual(dict(result.plan.child_env), {})


    def test_inventory_descriptions_do_not_override_physical_identity(self):
        supplied = (replace(self.outputs[0], identity=OutputIdentity(HASH_A, 'other', 'label')),
                    self.outputs[1])
        result = self.call(argv=self.plan_args(), outputs=supplied)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.monitor_label, 'edid:abababababab…')
        self.assertNotIn('label', result.plan.summary)

    def test_explicit_hash_replaces_prior_request_without_mutating_snapshot(self):
        snapshot = replace(self.snapshot, gaming_edid_sha256=HASH_B)
        result = self.call(argv=self.plan_args(), snapshot=snapshot)
        self.assertTrue(result.ok)
        self.assertEqual(result.plan.monitor_label, 'edid:abababababab…')
        self.assertEqual(snapshot.gaming_edid_sha256, HASH_B)

    def test_inventory_conflict_stops_resolution_and_both_builders(self):
        with patch.object(cli, 'resolve_output') as monitor:
            with patch.object(cli, 'build_argv') as command:
                with patch.object(cli, 'build_child_env') as env:
                    result = self.call(argv=self.plan_args(), outputs=self.outputs[:1])
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.reasons, ('inventory_mismatch',))
        self.assertIsNone(result.plan)
        self.assertEqual([monitor.call_count, command.call_count, env.call_count], [0, 0, 0])
