"""Pure command/environment contracts; synthetic inputs only."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-display/src"))

from hybrid_display.command import (
    ArgvResult, EnvironmentResult, LaunchOptions, WaylandSupport,
    build_argv, build_child_env,
)


def options(**changes):
    return replace(LaunchOptions(("vkcube",)), **changes)


class CommandTests(unittest.TestCase):
    def test_valid_1080p60_has_explicit_nested_wayland_and_separator(self):
        result = build_argv(options(), WaylandSupport.SUPPORTED)
        self.assertIsInstance(result, ArgvResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.argv, (
            "gamescope", "--backend", "wayland", "--expose-wayland",
            "-w", "1920", "-h", "1080", "-W", "1920", "-H", "1080",
            "-r", "60", "--", "vkcube",
        ))

    def test_distinct_inner_outer_sizes_and_fps_are_preserved(self):
        result = build_argv(options(inner_width=1280, inner_height=720,
                                    outer_width=2560, outer_height=1440, fps=120),
                            WaylandSupport.SUPPORTED)
        self.assertEqual(result.argv, (
            'gamescope', '--backend', 'wayland', '--expose-wayland',
            '-w', '1280', '-h', '720', '-W', '2560', '-H', '1440',
            '-r', '120', '--', 'vkcube',
        ))

    def test_unsupported_wayland_exposure_blocks_without_partial_argv(self):
        result = build_argv(options(), WaylandSupport.UNSUPPORTED)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.argv)
        self.assertEqual(result.reasons, ('wayland_exposure_unsupported',))

    def test_unknown_wayland_exposure_and_default_block(self):
        for result in (build_argv(options(), WaylandSupport.UNKNOWN), build_argv(options())):
            self.assertFalse(result.ok)
            self.assertIsNone(result.argv)
            self.assertEqual(result.reasons, ('wayland_exposure_unknown',))

    def test_truthy_or_untyped_capability_never_enables_exposure(self):
        for capability in (None, True, 1, 'supported', {}, []):
            with self.subTest(capability=capability):
                result = build_argv(options(), capability)
                self.assertFalse(result.ok)
                self.assertIsNone(result.argv)
                self.assertEqual(result.reasons, ('wayland_capability_invalid',))

    def test_zero_negative_bool_and_huge_dimensions_are_rejected(self):
        for field in ('inner_width', 'inner_height', 'outer_width', 'outer_height'):
            for value in (0, -1, True, False, 16385, 10**100, '1920', 1920.0, None):
                with self.subTest(field=field, value=value):
                    result = build_argv(options(**{field: value}), WaylandSupport.SUPPORTED)
                    self.assertFalse(result.ok)
                    self.assertIsNone(result.argv)
                    self.assertEqual(result.reasons, (field + '_invalid',))

    def test_refresh_policy_blocks_zero_negative_bool_and_over_360(self):
        for value in (0, -60, True, False, 361, 10**100, '60', 60.0, None):
            with self.subTest(value=value):
                result = build_argv(options(fps=value), WaylandSupport.SUPPORTED)
                self.assertFalse(result.ok)
                self.assertIsNone(result.argv)
                self.assertEqual(result.reasons, ('fps_invalid',))

    def test_wrong_options_type_is_structured_and_blocked(self):
        for value in (None, {}, (), 'vkcube'):
            with self.subTest(value=value):
                try:
                    result = build_argv(value, WaylandSupport.SUPPORTED)
                except (TypeError, AttributeError, ValueError) as error:
                    self.fail('Expected structured rejection, got ' + type(error).__name__)
                self.assertFalse(result.ok)
                self.assertIsNone(result.argv)
                self.assertEqual(result.reasons, ('options_invalid',))

    def test_client_arguments_keep_exact_element_boundaries(self):
        client = ['client with spaces', 'two words', '"quoted"', "'single'",
                  ';', '$(touch nowhere)', '`literal`', '&&', '', '--backend', 'drm']
        before = client.copy()
        result = build_argv(options(client_argv=client), WaylandSupport.SUPPORTED)
        self.assertTrue(result.ok)
        self.assertEqual(result.argv[15:], tuple(before))
        self.assertEqual(result.argv[14], '--')
        self.assertEqual(client, before)
        self.assertIsInstance(result.argv, tuple)
        self.assertEqual(result, build_argv(options(client_argv=client), WaylandSupport.SUPPORTED))
        self.assertEqual(result.argv[:4], ('gamescope', '--backend', 'wayland', '--expose-wayland'))

    def test_missing_or_non_sequence_client_argv_blocks(self):
        for client in ((), [], None, 'vkcube', {'program': 'vkcube'}, 123):
            with self.subTest(client=client):
                try:
                    result = build_argv(options(client_argv=client), WaylandSupport.SUPPORTED)
                except (TypeError, AttributeError, ValueError) as error:
                    self.fail('Expected structured rejection, got ' + type(error).__name__)
                self.assertFalse(result.ok)
                self.assertIsNone(result.argv)
                self.assertEqual(result.reasons, ('client_argv_invalid',))

    def test_empty_client_program_is_blocked(self):
        for program in ('', ' ', '\t'):
            with self.subTest(program=program):
                result = build_argv(options(client_argv=(program,)), WaylandSupport.SUPPORTED)
                self.assertFalse(result.ok)
                self.assertIsNone(result.argv)
                self.assertEqual(result.reasons, ('client_program_empty',))

    def test_nul_or_non_string_client_elements_block_atomically(self):
        for client in (('client\0suffix',), ('vkcube', 'x\0y'), (None,),
                       ('vkcube', 42), ('vkcube', b'bytes'), ('vkcube', True)):
            with self.subTest(client=client):
                result = build_argv(options(client_argv=client), WaylandSupport.SUPPORTED)
                self.assertFalse(result.ok)
                self.assertIsNone(result.argv)
                self.assertEqual(result.reasons, ('client_argument_invalid',))

    def test_options_detach_caller_client_list(self):
        client = ['vkcube', 'original']
        current = options(client_argv=client)
        client[0] = 'changed'
        client.append('extra')
        result = build_argv(current, WaylandSupport.SUPPORTED)
        self.assertEqual(result.argv[15:], ('vkcube', 'original'))
        self.assertEqual(current.client_argv, ('vkcube', 'original'))

    def test_invalid_option_payload_is_not_exposed_in_repr(self):
        secret = 'synthetic-private-option-value'
        current = options(inner_width=secret, client_argv=('client', secret))
        result = build_argv(current, WaylandSupport.SUPPORTED)
        self.assertFalse(result.ok)
        self.assertNotIn(secret, repr(current))
        self.assertNotIn(secret, repr(result))
        self.assertNotIn(secret, str(result.reasons))

    def test_environment_is_a_detached_successful_mapping(self):
        parent = {'XDG_RUNTIME_DIR': '/run/user/synthetic', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/synthetic/bus',
                  'LANG': 'de_DE.UTF-8', 'LC_ALL': 'C.UTF-8', 'LC_CTYPE': 'C'}
        before = parent.copy()
        result = build_child_env(parent)
        self.assertIsInstance(result, EnvironmentResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.reasons, ())
        self.assertEqual(dict(result.child_env), before)
        self.assertIsNot(result.child_env, parent)
        self.assertEqual(parent, before)
        parent['LANG'] = 'changed'
        self.assertEqual(result.child_env['LANG'], 'de_DE.UTF-8')

    def test_unknown_variables_are_not_copied(self):
        parent = {'LANG': 'C', 'UNRELATED': 'private-data', 'HOME': '/synthetic/home', 'PATH': '/synthetic/bin'}
        result = build_child_env(parent)
        self.assertTrue(result.ok)
        self.assertEqual(dict(result.child_env), {'LANG': 'C'})
        self.assertEqual(parent['UNRELATED'], 'private-data')

    def test_non_mapping_parent_is_blocked_without_exceptions(self):
        for parent in (None, [], [('LANG', 'C')], 'LANG=C', 42):
            with self.subTest(parent_type=type(parent).__name__):
                try:
                    result = build_child_env(parent)
                except (TypeError, ValueError, AttributeError) as error:
                    self.fail('Expected structured rejection, got ' + type(error).__name__)
                self.assertFalse(result.ok)
                self.assertEqual(result.status, 'blocked')
                self.assertIsNone(result.child_env)
                self.assertEqual(result.reasons, ('environment_mapping_invalid',))

    def test_non_string_environment_keys_or_values_block_atomically(self):
        for invalid in ({1: 'value'}, {'LANG': 42}, {'LANG': None},
                        {'UNKNOWN': b'bytes'}, {False: 'value'}):
            with self.subTest(invalid_type=type(next(iter(invalid))).__name__):
                result = build_child_env({'LC_CTYPE': 'C', **invalid})
                self.assertFalse(result.ok)
                self.assertIsNone(result.child_env)
                self.assertEqual(result.reasons, ('environment_entry_type_invalid',))

    def test_nul_in_environment_key_or_value_blocks_atomically(self):
        for invalid in ({'LANG\0TOKEN': 'synthetic'}, {'LANG': 'x\0y'},
                        {'UNRELATED': 'x\0y'}):
            result = build_child_env({'LC_CTYPE': 'C', **invalid})
            self.assertFalse(result.ok)
            self.assertIsNone(result.child_env)
            self.assertEqual(result.reasons, ('environment_nul',))

    def test_empty_or_invalid_environment_keys_are_blocked(self):
        for key in ('', '=', 'LANG=oops', 'BAD KEY', '9INVALID', 'LÄNG', '-LANG'):
            with self.subTest(key=key):
                result = build_child_env({'LANG': 'C', key: 'synthetic'})
                self.assertFalse(result.ok)
                self.assertIsNone(result.child_env)
                self.assertEqual(result.reasons, ('environment_key_invalid',))

    def test_empty_runtime_addresses_are_blocked_without_defaults(self):
        for key in ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS'):
            with self.subTest(key=key):
                result = build_child_env({key: ''})
                self.assertFalse(result.ok)
                self.assertIsNone(result.child_env)
                self.assertEqual(result.reasons, ('environment_value_empty',))

    def test_environment_result_is_immutable_and_does_not_alias_parent(self):
        parent = {'LANG': 'C'}
        result = build_child_env(parent)
        with self.assertRaises(TypeError):
            result.child_env['LANG'] = 'changed'
        self.assertEqual(parent, {'LANG': 'C'})
        self.assertEqual(result.child_env['LANG'], 'C')

    def test_policy_boundary_values_are_accepted(self):
        for size, fps in ((1, 1), (16384, 360)):
            result = build_argv(options(inner_width=size, inner_height=size,
                                        outer_width=size, outer_height=size, fps=fps),
                                WaylandSupport.SUPPORTED)
            self.assertTrue(result.ok, result.reasons)
            self.assertEqual(result.argv[5], str(size))
            self.assertEqual(result.argv[13], str(fps))

    def test_no_backend_placement_or_wrapper_options_are_inserted(self):
        result = build_argv(options(), WaylandSupport.SUPPORTED)
        prefix = result.argv[:result.argv.index('--')]
        self.assertEqual(prefix[:4], ('gamescope', '--backend', 'wayland', '--expose-wayland'))
        for forbidden in ('drm', 'sdl', '--prefer-output', '--display-index',
                          '--force-orientation', '--generate-drm-mode', '--grab',
                          'sh', 'bash', 'env', 'eval'):
            self.assertNotIn(forbidden, prefix)

    def test_argument_errors_are_complete_deduplicated_and_deterministic(self):
        current = options(inner_width=0, outer_height=-1, fps=False, client_argv=('vkcube', 1))
        expected = ('client_argument_invalid', 'fps_invalid', 'inner_width_invalid',
                    'outer_height_invalid', 'wayland_exposure_unknown')
        result = build_argv(current)
        self.assertFalse(result.ok)
        self.assertIsNone(result.argv)
        self.assertEqual(result.reasons, expected)
        self.assertEqual(result, build_argv(current))

    def test_secret_classes_and_allowlist_lookalikes_are_discarded(self):
        names = ('TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'COOKIE', 'SSH_AUTH_SOCK',
                 'GITHUB_TOKEN', 'GITHUB_OTHER', 'GH_TOKEN', 'GH_OTHER', 'AWS_PROFILE',
                 'AWS_ACCESS_KEY_ID', 'STEAM_WEB_COOKIE', 'STEAM_ACCOUNT_PASSWORD',
                 'LANG_TOKEN', 'LANG_SECRET', 'LC_CTYPE_PASSWORD', 'LC_ALL_CREDENTIAL',
                 'XDG_RUNTIME_DIR_COOKIE', 'DBUS_SESSION_BUS_ADDRESS_TOKEN',
                 'API_KEY', 'LANGUAGE', 'LANG_EXTRA', 'LC_PRIVATE', 'lang')
        parent = {name: 'synthetic-private-value' for name in names}
        parent['LANG'] = 'C'
        before = parent.copy()
        result = build_child_env(parent)
        self.assertTrue(result.ok)
        self.assertEqual(dict(result.child_env), {'LANG': 'C'})
        self.assertEqual(parent, before)
        self.assertNotIn('synthetic-private-value', repr(result))
        self.assertNotIn('synthetic-private-value', str(result.reasons))

    def test_display_gpu_and_backend_overrides_are_not_inherited_or_fabricated(self):
        names = ('WLR_DRM_DEVICES', 'DRI_PRIME', 'MESA_VK_DEVICE_SELECT', 'VK_ICD_FILENAMES',
                 'AMD_VULKAN_ICD', 'SDL_VIDEODRIVER', 'GAMESCOPE_WSI', 'DISPLAY',
                 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP',
                 'GAMESCOPE_BACKEND', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONPATH')
        parent = {name: 'synthetic-existing-value' for name in names}
        result = build_child_env(parent)
        self.assertTrue(result.ok)
        self.assertEqual(dict(result.child_env), {})
        self.assertEqual(dict(build_child_env({}).child_env), {})
        self.assertEqual(parent, {name: 'synthetic-existing-value' for name in names})

    def test_environment_order_and_result_do_not_depend_on_mapping_order(self):
        from types import MappingProxyType
        first = {'LANG': 'C', 'XDG_RUNTIME_DIR': '/synthetic/runtime', 'UNKNOWN': 'ignored'}
        second = MappingProxyType(dict(reversed(tuple(first.items()))))
        a, b = build_child_env(first), build_child_env(second)
        self.assertEqual(a, b)
        self.assertEqual(tuple(a.child_env.items()),
                         (('LANG', 'C'), ('XDG_RUNTIME_DIR', '/synthetic/runtime')))
        self.assertIsNot(a.child_env, b.child_env)

    def test_no_payload_values_appear_in_result_representations(self):
        secret = 'synthetic-private-result-value'
        argv = build_argv(options(client_argv=('client', secret)), WaylandSupport.SUPPORTED)
        env = build_child_env({'LANG': secret})
        self.assertTrue(argv.ok)
        self.assertTrue(env.ok)
        self.assertNotIn(secret, repr(argv))
        self.assertNotIn(secret, str(argv))
        self.assertNotIn(secret, repr(env))
        self.assertNotIn(secret, str(env))
        invalid = build_child_env({'LANG': secret, 'BAD=KEY': secret + '\0'})
        self.assertFalse(invalid.ok)
        self.assertIsNone(invalid.child_env)
        self.assertEqual(invalid.reasons, ('environment_key_invalid', 'environment_nul'))
        self.assertNotIn(secret, repr(invalid))
        self.assertNotIn('BAD=KEY', str(invalid.reasons))

    def test_empty_locale_values_are_preserved_without_blocking(self):
        for key in ('LANG', 'LC_ALL', 'LC_CTYPE'):
            with self.subTest(key=key):
                parent = {'LANG': 'C', key: ''}
                result = build_child_env(parent)
                self.assertTrue(result.ok, result.reasons)
                self.assertEqual(result.status, 'success')
                self.assertEqual(result.reasons, ())
                self.assertEqual(dict(result.child_env), parent)
                self.assertEqual(result.child_env[key], '')
