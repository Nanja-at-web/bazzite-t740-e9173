"""Diagnostics are strings over synthetic data, never probes or exports."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype/hybrid-display/src'))

from hybrid_display import diagnostics as diag


class PrivacyTests(unittest.TestCase):
    def test_minimal_report_uses_fixed_schema_and_only_explicit_fields(self):
        result = diag.render_report({'mode': 'plan', 'result': 'success', 'schema_version': 'private'})
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.codes, ())
        self.assertEqual(result.report, 'schema_version: 1\nmode: plan\nresult: success\n')


    def test_missing_wrong_typed_or_private_required_fields_block_safely(self):
        for fields in (None, [], 'private', {}, {'mode': 'run', 'result': 'success'},
                       {'mode': 'plan', 'result': 'TOKEN_private'},
                       {'mode': ['plan'], 'result': 'success'},
                       {'mode': 'plan', 'result': RuntimeError('SECRET_private')}):
            try:
                result = diag.render_report(fields)
            except Exception:
                self.fail('Invalid diagnostic data must produce a safe blocking result')
            self.assertEqual(result.status, 'blocked')
            self.assertIsNone(result.report)
            self.assertNotIn('private', repr(result))


    def test_known_enums_are_rendered_but_free_text_is_blocked(self):
        fields = dict(mode='preflight', result='blocked', session_type='wayland',
                      backend='wayland', stage='graphics')
        result = diag.render_report(fields)
        self.assertIn('session_type: wayland\n', result.report)
        self.assertIn('backend: wayland\n', result.report)
        self.assertIn('stage: graphics\n', result.report)
        for key in ('session_type', 'backend', 'stage'):
            bad = diag.render_report({**fields, key: 'PRIVATE_KEY_private'})
            self.assertEqual(bad.status, 'blocked')
            self.assertIsNone(bad.report)
            self.assertNotIn('private', repr(bad))


    def test_numeric_counts_exit_and_boolean_fields_are_typed_and_bounded(self):
        fields = dict(mode='plan', result='success', connected_outputs=2, active_outputs=2,
                      journal_entries=0, journal_truncated=False, exit_code=-15)
        result = diag.render_report(fields)
        self.assertIn('active_outputs: 2\n', result.report)
        self.assertIn('exit_code: -15\n', result.report)
        self.assertIn('journal_truncated: false\n', result.report)
        for key, value in (('active_outputs', True), ('active_outputs', -1),
                           ('connected_outputs', 17), ('active_outputs', 3),
                           ('journal_entries', 101), ('journal_truncated', 0),
                           ('exit_code', True), ('exit_code', '0'), ('exit_code', 2**31)):
            bad = diag.render_report({**fields, key: value})
            self.assertEqual(bad.status, 'blocked')
            self.assertIsNone(bad.report)


    def test_closed_finding_codes_are_sorted_deduplicated_and_private_codes_omitted(self):
        result = diag.render_report(dict(mode='plan', result='blocked',
                                        codes=['kwin_missing', 'session_not_wayland', 'kwin_missing']))
        self.assertIn('finding: kwin_missing\nfinding: session_not_wayland\n', result.report)
        for value in ('TOKEN_private', 'secret', 'alice', 'path/name', 'free text', 'error: private',
                      'line\nbreak', 'a' * 1000, RuntimeError('private'), ['private']):
            bad = diag.render_report(dict(mode='plan', result='blocked', codes=[value]))
            self.assertEqual(bad.status, 'warning')
            self.assertEqual(bad.codes, ('codes_redacted',))
            self.assertNotIn('private', bad.report)
            self.assertNotIn('private', repr(bad))


    def test_marker_and_versions_accept_only_narrow_formats_and_known_keys(self):
        fields = dict(mode='plan', result='success', marker='t+12.500s',
                      versions={'os': '45', 'kernel': '7.2.15', 'kwin': '6.8.2',
                                'gamescope': '3.17.0', 'plasma': '6.8.2', 'mesa': '26.2.6',
                                'unknown': 'TOKEN_private'})
        result = diag.render_report(fields)
        self.assertIn('marker: t+12.500s\n', result.report)
        self.assertIn('version_kernel: 7.2.15\n', result.report)
        self.assertNotIn('TOKEN_private', result.report)
        bad = diag.render_report(dict(mode='plan', result='success', marker='alice',
                                      versions={'kernel': '1.2-SECRET_private', 'kwin': ['private']}))
        self.assertEqual(bad.status, 'warning')
        self.assertEqual(bad.codes, ('marker_redacted', 'versions_redacted'))
        self.assertNotIn('private', bad.report)
        self.assertNotIn('alice', bad.report)


    def test_monitor_report_uses_redacted_labels_and_fixed_description_catalog(self):
        fields = dict(mode='plan', result='success', monitors=[
            dict(label='edid:abababababab…', manufacturer='ACI', model='VG248',
                 width=1920, height=1080, refresh_hz=60),
            dict(label='edid:cdcdcdcdcdcd…', manufacturer='ACI', model='VG248',
                 width=1920, height=1080, refresh_hz=60)])
        result = diag.render_report(fields)
        self.assertEqual(result.status, 'success')
        self.assertIn('monitor: edid:abababababab… ACI VG248 1920x1080@60\n', result.report)
        self.assertIn('monitor: edid:cdcdcdcdcdcd… ACI VG248 1920x1080@60\n', result.report)
        for label in ('ab' * 32, 'DP-1', 'edid:abababababab', 'edid:abcd…', 'edid:abababababab…\nprivate'):
            bad = diag.render_report(dict(mode='plan', result='success', monitors=[dict(label=label)]))
            self.assertEqual(bad.status, 'blocked')
            self.assertIsNone(bad.report)
            self.assertNotIn('private', repr(bad))


    def test_prefix_collision_is_marked_even_when_caller_omits_marker(self):
        monitors = [dict(label='edid:abababababab…', manufacturer='ACI', model='VG248'),
                    dict(label='edid:abababababab…', manufacturer='Dell', model='P2419H')]
        result = diag.render_report(dict(mode='plan', result='success', monitors=monitors))
        self.assertEqual(result.status, 'warning')
        self.assertEqual(result.codes, ('monitor_prefix_ambiguous',))
        self.assertEqual(result.report.count('edid:abababababab… (Präfix mehrdeutig)'), 2)
        self.assertFalse(hasattr(result, 'monitor_selection'))


    def test_code_and_monitor_cardinality_limits_block_before_output(self):
        for extra in (dict(codes=['kwin_missing'] * 17),
                      dict(monitors=[dict(label='edid:abababababab…')] * 9)):
            result = diag.render_report(dict(mode='plan', result='success', **extra))
            self.assertEqual(result.status, 'blocked')
            self.assertIsNone(result.report)
            self.assertIn('item_limit', result.codes)


    def test_total_character_limit_blocks_dense_valid_fields_without_partial_report(self):
        codes = ['selected_output_disconnected', 'selected_output_disabled',
                 'selected_output_mirrored', 'focus_integration_active', 'wayland_exposure_unsupported',
                 'wayland_exposure_unknown', 'ownership_check_failed', 'missing_graphics_client',
                 'session_not_wayland', 'session_not_plasma', 'session_not_local',
                 'too_few_active_outputs', 'environment_blocked', 'inventory_mismatch',
                 'ownership_unverified', 'termination_timeout']
        monitors = [dict(label='edid:' + format(i, '012x') + '…', manufacturer='Samsung',
                         model='P2419H', width=16384, height=16384, refresh_hz=360) for i in range(8)]
        result = diag.render_report(dict(mode='plan', result='blocked', codes=codes, monitors=monitors))
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.report)
        self.assertIn('report_size_limit', result.codes)


    def test_line_limit_is_independent_of_character_limit(self):
        fields = dict(mode='plan', result='blocked', marker='t+1.000s',
                      versions={name: '1' for name in ('os', 'kernel', 'gamescope', 'plasma', 'kwin', 'mesa')},
                      session_type='tty', backend='unconfirmed', stage='not_tested',
                      connected_outputs=0, active_outputs=0, journal_entries=0,
                      journal_truncated=False, exit_code=0,
                      codes=['kwin_missing', 'session_not_wayland', 'session_not_plasma',
                             'session_not_local', 'too_few_active_outputs', 'mirrored_outputs',
                             'process_conflict', 'decky_active', 'missing_gamescope',
                             'selection_missing', 'selection_invalid', 'outputs_invalid',
                             'clock_invalid', 'clock_reversed', 'spawn_failed', 'identity_invalid'])
        result = diag.render_report(fields)
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.report)
        self.assertIn('report_line_limit', result.codes)


    def test_mapping_failures_do_not_leak_exception_text_or_escape(self):
        class BrokenMapping(dict):
            def get(self, key, default=None):
                raise ValueError('TOKEN_synthetic_private_exception')
        try:
            result = diag.render_report(BrokenMapping(mode='plan', result='success'))
        except Exception:
            self.fail('Mapping failure must be controlled without exception disclosure')
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(result.codes, ('diagnostic_failed',))
        self.assertIsNone(result.report)
        self.assertNotIn('synthetic_private', repr(result))


    def test_data_models_detach_lists_hide_payload_and_render_like_explicit_mapping(self):
        self.assertTrue(hasattr(diag, 'MonitorData') and hasattr(diag, 'DiagnosticData'),
                        'Typed diagnostic inputs are missing')
        monitor = diag.MonitorData('edid:abababababab…', 'ACI', 'VG248', 1920, 1080, 60)
        codes, monitors = ['kwin_missing'], [monitor]
        data = diag.DiagnosticData('plan', 'blocked', codes=codes, monitors=monitors)
        codes.clear()
        monitors.clear()
        result = diag.render_report(data)
        self.assertEqual(result.status, 'success')
        self.assertIn('finding: kwin_missing\n', result.report)
        self.assertIn('monitor: edid:abababababab… ACI VG248 1920x1080@60\n', result.report)
        with self.assertRaises(FrozenInstanceError):
            data.mode = 'preflight'
        bad = diag.MonitorData('TOKEN_private', 'SECRET_private', 'PASSWORD_private')
        self.assertNotIn('private', repr(bad))
        self.assertNotIn('private', repr(diag.DiagnosticData('private', 'private')))


    def test_enum_string_subclasses_cannot_bypass_closed_values(self):
        class PretendAllowed(str):
            def __eq__(self, other):
                return True
        for key in ('mode', 'result', 'session_type', 'backend', 'stage'):
            fields = dict(mode='plan', result='success')
            fields[key] = PretendAllowed('TOKEN_synthetic_private')
            result = diag.render_report(fields)
            self.assertEqual(result.status, 'blocked')
            self.assertIsNone(result.report)
            self.assertNotIn('synthetic_private', repr(result))


    def test_rendered_required_values_are_the_values_actually_validated(self):
        class SplitMapping(dict):
            def __getitem__(self, key):
                return 'TOKEN_synthetic_private'
        result = diag.render_report(SplitMapping(mode='plan', result='success'))
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.report, 'schema_version: 1\nmode: plan\nresult: success\n')
        self.assertNotIn('synthetic_private', result.report)


    def test_collection_subclasses_cannot_bypass_cardinality_bounds(self):
        class HiddenLength(list):
            def __len__(self):
                return 0
        result = diag.render_report(dict(mode='plan', result='success',
                                        codes=HiddenLength(['kwin_missing'] * 100)))
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.report)
        self.assertEqual(result.codes, ('codes_invalid',))


    def test_unknown_sensitive_fields_and_recursive_containers_are_never_visited(self):
        secret = 'TOKEN_synthetic_private_piece'
        class Opaque:
            def __str__(self):
                raise AssertionError('must not stringify')
            def __repr__(self):
                raise AssertionError('must not represent')
        nested = {'secret': secret}
        nested['self'] = nested
        fields = dict(mode='plan', result='success', raw_edid=b'raw-private',
                      edid_sha256='ab' * 32, serial=secret, argv=[secret],
                      environment=nested, exception=RuntimeError(secret), object=Opaque(),
                      journal=[secret], core_dump=secret, pid=123, run_token=Opaque(),
                      DBUS_SESSION_BUS_ADDRESS=secret, XDG_RUNTIME_DIR=secret)
        result = diag.render_report(fields)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.report, 'schema_version: 1\nmode: plan\nresult: success\n')
        self.assertNotIn('private_piece', repr(result))
        self.assertNotIn('ab' * 32, result.report)

    def test_synthetic_secret_classes_are_redacted_from_every_text_field(self):
        tags = ('TOKEN', 'SECRET', 'PASSWORD', 'COOKIE', 'CREDENTIAL', 'PRIVATE_KEY',
                'AUTH', 'AWS_', 'GH_', 'GITHUB_', 'STEAM_', 'SSH_')
        for tag in tags:
            secret = tag + '_synthetic_private_piece'
            fields = dict(mode='plan', result='success', marker=secret,
                          versions={name: secret for name in ('os', 'kernel', 'gamescope', 'plasma', 'kwin', 'mesa')},
                          codes=[secret], monitors=[dict(label='edid:abababababab…',
                                                         manufacturer=secret, model=secret)])
            result = diag.render_report(fields)
            self.assertEqual(result.status, 'warning')
            for rendered in (result.report, repr(result), str(result.codes)):
                self.assertNotIn(secret, rendered)
                self.assertNotIn('synthetic_private', rendered)
                self.assertNotIn('private_piece', rendered)

    def test_paths_usernames_network_addresses_and_exceptions_are_not_display_names(self):
        for value in ('alice', '/home/alice/private', '/var/home/alice',
                      'https://private.invalid', '192.0.2.1', 'alice@example.invalid',
                      'unix:path=/private/socket', 'SSH_AUTH_SOCK=/private',
                      RuntimeError('SECRET_synthetic_private'), {'argv': ['private']}, ['private']):
            result = diag.render_report(dict(mode='plan', result='success', marker=value,
                        versions={'kernel': value}, codes=[value],
                        monitors=[dict(label='edid:abababababab…', manufacturer=value, model=value)]))
            self.assertEqual(result.status, 'warning')
            for text in (result.report, repr(result), str(result.codes)):
                self.assertNotIn('alice', text)
                self.assertNotIn('private', text)
                self.assertNotIn('192.0.2.1', text)

    def test_description_controls_overlength_and_bidi_are_wholly_omitted(self):
        for value in ('ACI\nSECRET_private', '\x1b[31mACI', 'ACI\rprivate', 'A' * 10000,
                      'ACI\u202eprivate', 'ACI\u200b', 'VG248\x00private', 'Dell\tprivate',
                      'ＡＣＩ', 'Dеll', 'HP\x7f'):
            result = diag.render_report(dict(mode='plan', result='success',
                          monitors=[dict(label='edid:abababababab…', manufacturer=value, model=value)]))
            self.assertEqual(result.status, 'warning')
            self.assertIn('unavailable unavailable', result.report)
            self.assertNotIn('private', result.report)
            self.assertNotIn('\x1b', result.report)
            self.assertNotIn('\u202e', result.report)

    def test_known_unicode_description_is_safe_but_unknown_unicode_is_not_echoed(self):
        result = diag.render_report(dict(mode='plan', result='success',
                      monitors=[dict(label='edid:abababababab…', manufacturer='三星', model='VG248')]))
        self.assertEqual(result.status, 'success')
        self.assertIn('三星 VG248', result.report)
        self.assertNotIn('\x1b', result.report)
        self.assertNotIn('\u202e', result.report)

    def test_missing_description_and_preexisting_ambiguous_label_are_visible(self):
        result = diag.render_report(dict(mode='preflight', result='blocked',
                      monitors=[dict(label='edid:abababababab… (Präfix mehrdeutig)')]))
        self.assertEqual(result.status, 'warning')
        self.assertEqual(result.codes, ('description_redacted', 'monitor_prefix_ambiguous'))
        self.assertIn('(Präfix mehrdeutig) unavailable unavailable', result.report)

    def test_geometry_has_no_bool_float_nan_zero_or_partial_fallback(self):
        for name in ('width', 'height', 'refresh_hz'):
            for value in (True, False, 0, -1, 1.0, float('nan'), float('inf'), '60', None):
                monitor = dict(label='edid:abababababab…', manufacturer='ACI', model='VG248',
                               width=1920, height=1080, refresh_hz=60)
                monitor[name] = value
                result = diag.render_report(dict(mode='plan', result='success', monitors=[monitor]))
                self.assertEqual(result.status, 'blocked')
                self.assertIsNone(result.report)
        for name, value in (('width', 16385), ('height', 16385), ('refresh_hz', 361)):
            monitor = dict(label='edid:abababababab…', width=1, height=1, refresh_hz=1)
            monitor[name] = value
            self.assertEqual(diag.render_report(dict(mode='plan', result='success',
                                                      monitors=[monitor])).status, 'blocked')

    def test_mapping_set_and_monitor_order_do_not_change_report(self):
        a = diag.MonitorData('edid:abababababab…', 'ACI', 'VG248', 1920, 1080, 60)
        b = diag.MonitorData('edid:cdcdcdcdcdcd…', 'ACI', 'VG248', 1920, 1080, 60)
        first = dict(mode='plan', result='blocked', versions={'kwin': '6.8.2', 'kernel': '7.2.15'},
                     codes=['session_not_wayland', 'kwin_missing'], monitors=[b, a])
        second = dict(reversed(tuple(first.items())))
        second['versions'] = {'kernel': '7.2.15', 'kwin': '6.8.2'}
        second['codes'] = {'kwin_missing', 'session_not_wayland'}
        second['monitors'] = frozenset({a, b})
        self.assertEqual(diag.render_report(first), diag.render_report(second))

    def test_rendering_does_not_mutate_input_and_retains_no_input_references(self):
        codes = ['kwin_missing']
        monitor = dict(label='edid:abababababab…', manufacturer='ACI', model='VG248')
        fields = dict(mode='plan', result='blocked', codes=codes, monitors=[monitor])
        first = diag.render_report(fields)
        self.assertEqual(codes, ['kwin_missing'])
        self.assertEqual(monitor, dict(label='edid:abababababab…', manufacturer='ACI', model='VG248'))
        codes.clear()
        monitor['model'] = 'SECRET_private'
        self.assertIn('finding: kwin_missing', first.report)
        self.assertIn('ACI VG248', first.report)
        with self.assertRaises(FrozenInstanceError):
            first.report = 'private'

    def test_noncollections_and_malformed_monitor_entries_block_without_payload(self):
        for extra in (dict(codes=None), dict(codes='SECRET_private'), dict(monitors=None),
                      dict(monitors='private'), dict(monitors=[None]),
                      dict(monitors=[RuntimeError('private')]), dict(monitors=[{}])):
            result = diag.render_report(dict(mode='plan', result='success', **extra))
            self.assertEqual(result.status, 'blocked')
            self.assertIsNone(result.report)
            self.assertNotIn('private', repr(result))

    def test_version_and_marker_limits_reject_instead_of_disclosing_prefixes(self):
        for value in ('7.2.15-private', '7.2.15\nprivate', '7.2.15/private', '7.2.15:private',
                      '7.' + '1' * 10000, '\x1b7.2', '7.2.15\u202e', '７.２'):
            result = diag.render_report(dict(mode='plan', result='success', marker=value,
                                            versions={'kernel': value}))
            self.assertEqual(result.status, 'warning')
            self.assertEqual(result.codes, ('marker_redacted', 'versions_redacted'))
            self.assertNotIn('private', result.report)
            self.assertNotIn('version_kernel:', result.report)
            self.assertNotIn('marker:', result.report)


    def test_absent_optional_versions_are_identical_for_model_and_mapping(self):
        model = diag.DiagnosticData('plan', 'success')
        mapping = dict(mode='plan', result='success', versions=None)
        self.assertEqual(diag.render_report(model), diag.render_report(mapping))
        self.assertEqual(diag.render_report(mapping).status, 'success')


    def test_supplied_journal_truncation_is_visible_as_safe_warning(self):
        result = diag.render_report(dict(mode='plan', result='success',
                                         journal_entries=100, journal_truncated=True,
                                         journal=['TOKEN_private_full_line']))
        self.assertEqual(result.status, 'warning')
        self.assertEqual(result.codes, ('journal_truncated',))
        self.assertIn('journal_truncated: true\n', result.report)
        self.assertIn('journal_entries: 100\n', result.report)
        self.assertNotIn('private', result.report)


    def test_exact_code_monitor_and_line_limits_remain_usable(self):
        monitors = [diag.MonitorData('edid:' + format(i, '012x') + '…', 'ACI', 'VG248')
                    for i in range(8)]
        result = diag.render_report(dict(mode='plan', result='blocked',
                                         codes=['kwin_missing'] * 16, monitors=monitors))
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.report.count('monitor: '), 8)
        self.assertEqual(result.report.count('finding: '), 1)
        fields = dict(mode='plan', result='blocked', marker='t+1.000s',
                      versions={name: '1' for name in ('os', 'kernel', 'gamescope', 'plasma')},
                      session_type='tty', backend='unconfirmed', stage='not_tested',
                      connected_outputs=0, active_outputs=0, journal_entries=0,
                      journal_truncated=False, exit_code=0,
                      codes=['kwin_missing', 'session_not_wayland', 'session_not_plasma',
                             'session_not_local', 'too_few_active_outputs', 'mirrored_outputs',
                             'process_conflict', 'decky_active', 'missing_gamescope',
                             'selection_missing', 'selection_invalid', 'outputs_invalid',
                             'clock_invalid', 'clock_reversed', 'spawn_failed', 'identity_invalid'])
        result = diag.render_report(fields)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.report.count('\n'), 32)
        self.assertLessEqual(len(result.report), 1024)

    def test_diagnostic_models_copy_versions_without_rendering_unknown_values(self):
        versions = {'kernel': '7.2.15', 'TOKEN': 'synthetic_private'}
        data = diag.DiagnosticData('plan', 'success', versions=versions)
        versions['kernel'] = 'SECRET_private'
        result = diag.render_report(data)
        self.assertEqual(result.status, 'success')
        self.assertIn('version_kernel: 7.2.15\n', result.report)
        self.assertNotIn('private', repr(data))
        self.assertNotIn('private', result.report)
        with self.assertRaises(TypeError):
            data.versions['kernel'] = 'changed'
