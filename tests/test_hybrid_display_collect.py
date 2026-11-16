"""Collector contracts over synthetic in-memory facts; no host data or I/O."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype/hybrid-display/src'))

from hybrid_display import collect
from hybrid_display.model import Output, OutputIdentity, SessionSnapshot
from hybrid_display.preflight import evaluate_preflight


HASH_A = 'a1' * 32
HASH_B = 'b2' * 32


def output(digest=HASH_A, connector='DP-1', **changes):
    return replace(Output(OutputIdentity(digest), '0000:fa:01.0', connector,
                          connector, True, False, True), **changes)


def facts(**changes):
    values = dict(session_type='wayland', desktop='KDE', own_local_session=True,
                  kwin_running=True, outputs=[output(), output(HASH_B, 'DP-2')],
                  existing_clients=[], focus_service_active=False, decky_active=False,
                  capabilities={'gamescope', 'vkcube'})
    values.update(changes)
    return values


class CollectTests(unittest.TestCase):
    def assert_metaclass_container_rejected(self, field, reason):
        calls = []

        class TrapMeta(type):
            def __eq__(cls, other):
                calls.append('type-equality')
                return True

        class TrapList(list, metaclass=TrapMeta):
            def __len__(self):
                calls.append('len')
                return super().__len__()

            def __iter__(self):
                calls.append('iter')
                return super().__iter__()

            def __getitem__(self, key):
                calls.append('getitem')
                return super().__getitem__(key)

            def __bool__(self):
                calls.append('bool')
                return True

            def __repr__(self):
                calls.append('repr')
                return 'synthetic-private'

        source = facts(**{field: TrapList(['synthetic-private'])})
        result = collect.collect_snapshot(source)
        self.assertEqual(calls, [], 'Container must be rejected before any callback')
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.snapshot)
        self.assertEqual(result.reasons, (reason,))
        self.assertNotIn('synthetic-private', repr(result))
        self.assertNotIn('synthetic-private', str(result))
        self.assertEqual(calls, [])

    def test_output_container_metaclass_never_executes_callbacks(self):
        self.assert_metaclass_container_rejected('outputs', 'outputs_invalid')

    def test_client_container_metaclass_never_executes_callbacks(self):
        self.assert_metaclass_container_rejected('existing_clients', 'clients_invalid')

    def test_capability_container_metaclass_never_executes_callbacks(self):
        self.assert_metaclass_container_rejected('capabilities', 'capabilities_invalid')

    def blocked(self, source, reason=None):
        try:
            result = collect.collect_snapshot(source)
        except (Exception, SystemExit):
            self.fail('Collector must return fixed codes, never an input exception')
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 'blocked')
        self.assertIsNone(result.snapshot)
        self.assertTrue(result.reasons)
        if reason is not None:
            self.assertIn(reason, result.reasons)
        self.assertNotIn('synthetic-private', repr(result))
        return result

    def test_known_facts_translate_to_existing_snapshot_model(self):
        source = facts()
        result = collect.collect_snapshot(source)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.reasons, ())
        self.assertIs(type(result.snapshot), SessionSnapshot)
        for name in ('session_type', 'desktop', 'own_local_session', 'kwin_running',
                     'focus_service_active', 'decky_active', 'capabilities'):
            self.assertEqual(getattr(result.snapshot, name), source[name])
        self.assertEqual(result.snapshot.outputs, tuple(source['outputs']))
        self.assertEqual(result.snapshot.existing_clients, ())
        self.assertIsNone(result.snapshot.gaming_edid_sha256)

    def test_collection_success_is_not_preflight_permission(self):
        result = collect.collect_snapshot(facts(session_type='x11', own_local_session=False,
                                               existing_clients=['steam'], kwin_running=False))
        self.assertTrue(result.ok, result.reasons)
        preflight = evaluate_preflight(result.snapshot)
        self.assertFalse(preflight.ok)
        for reason in ('session_not_wayland', 'session_not_local', 'process_conflict',
                       'kwin_missing', 'selection_missing'):
            self.assertIn(reason, preflight.reasons)

    def test_all_nine_fields_are_required_no_host_defaults(self):
        for name in facts():
            source = facts()
            del source[name]
            with self.subTest(field=name):
                self.blocked(source, 'fields_missing')

    def test_unknown_fields_and_selection_are_rejected_not_retained(self):
        for name in ('extra', 'gaming_edid_sha256', 'raw_edid', 'serial', 'argv', 'environment'):
            source = facts()
            source[name] = 'synthetic-private'
            with self.subTest(field=name):
                self.blocked(source, 'fields_unknown')

    def test_scalar_types_and_closed_enums_are_strict(self):
        for name in ('session_type', 'desktop'):
            for value in (None, True, 1, [], b'wayland', 'unknown', 'synthetic-private'):
                with self.subTest(field=name, kind=type(value).__name__):
                    self.blocked(facts(**{name: value}), name + '_invalid')
        for name in ('own_local_session', 'kwin_running', 'focus_service_active', 'decky_active'):
            for value in (None, 0, 1, 'true', [], {}):
                with self.subTest(field=name, kind=type(value).__name__):
                    self.blocked(facts(**{name: value}), 'session_flags_invalid')

    def test_mapping_and_string_subclasses_are_rejected_without_callbacks(self):
        calls = []

        class TrapDict(dict):
            def get(self, *args):
                calls.append('get')
                raise RuntimeError('synthetic-private')

            def keys(self):
                calls.append('keys')
                raise SystemExit('synthetic-private')

            def __iter__(self):
                calls.append('iter')
                raise RuntimeError('synthetic-private')

        class TrapString(str):
            def __eq__(self, other):
                calls.append('eq')
                raise RuntimeError('synthetic-private')

        for source in (None, [], SessionSnapshot(), TrapDict(facts()),
                       facts(session_type=TrapString('wayland')),
                       facts(desktop=TrapString('KDE'))):
            self.blocked(source)
        self.assertEqual(calls, [])

    def test_output_records_must_be_complete_strict_and_address_only(self):
        invalid = [None, {}, 'synthetic-private', output(identity=None),
                   output(identity=OutputIdentity(None)), output(connected=False),
                   output(gpu_pci='/synthetic/private'), output(gpu_pci='not-a-pci-address'),
                   output(drm_connector='DP-1 --synthetic-private'),
                   output(kwin_name='synthetic-private description'),
                   output(identity=OutputIdentity(HASH_A, 'synthetic-private', 'free description'))]
        for name in ('enabled', 'mirrored', 'connected'):
            invalid.extend(output(**{name: value}) for value in (None, 0, 1, 'true'))
        for record in invalid:
            self.blocked(facts(outputs=[record]), 'output_invalid')
        for inventory in (None, 'synthetic-private', {}, [output()] * 1024):
            self.blocked(facts(outputs=inventory))

    def test_disconnected_unused_output_can_explicitly_have_no_edid(self):
        record = output(None, 'DP-3', enabled=False, connected=False)
        result = collect.collect_snapshot(facts(outputs=[record]))
        self.assertTrue(result.ok, result.reasons)
        self.assertIsNone(result.snapshot.outputs[0].identity.edid_sha256)
        self.assertIsNone(result.snapshot.gaming_edid_sha256)

    def test_duplicate_connector_kwin_name_and_active_edid_are_blocked(self):
        cases = (
            ([output(), output(HASH_B, 'DP-1', kwin_name='DP-2')], 'output_address_duplicate'),
            ([output(), output(HASH_B, 'DP-2', kwin_name='DP-1')], 'output_name_duplicate'),
            ([output(), output(HASH_A, 'DP-2')], 'output_active_identity_duplicate'),
        )
        for inventory, reason in cases:
            with self.subTest(reason=reason):
                self.blocked(facts(outputs=inventory), reason)

    def test_repeated_inactive_identity_is_not_silently_selected(self):
        result = collect.collect_snapshot(facts(outputs=[output(), output(HASH_A, 'DP-2', enabled=False)]))
        self.assertTrue(result.ok, result.reasons)
        self.assertIsNone(result.snapshot.gaming_edid_sha256)
        self.assertFalse(evaluate_preflight(result.snapshot).ok)

    def test_output_limits_are_checked_before_iteration(self):
        self.blocked(facts(outputs=[output()] * 1024), 'outputs_limit')

    def test_snapshot_outputs_are_fresh_objects_and_inputs_untouched(self):
        source = facts()
        records = source['outputs']
        before = list(records)
        result = collect.collect_snapshot(source)
        self.assertTrue(result.ok)
        self.assertIsNot(result.snapshot.outputs, records)
        for copied, original in zip(result.snapshot.outputs, before):
            self.assertIsNot(copied, original)
            self.assertIsNot(copied.identity, original.identity)
        self.assertEqual(records, before)
        records.clear()
        source['existing_clients'].append('steam')
        source['capabilities'].clear()
        self.assertEqual(result.snapshot.outputs, tuple(before))
        self.assertEqual(result.snapshot.existing_clients, ())
        self.assertEqual(result.snapshot.capabilities, frozenset({'gamescope', 'vkcube'}))
        with self.assertRaises(FrozenInstanceError):
            result.snapshot = None
        with self.assertRaises(FrozenInstanceError):
            result.snapshot.outputs[0].enabled = False

    def test_output_sequence_subclass_never_executes_user_code(self):
        calls = []

        class TrapList(list):
            def __iter__(self):
                calls.append('iter')
                raise SystemExit('synthetic-private')

            def __len__(self):
                calls.append('len')
                raise RuntimeError('synthetic-private')

        self.blocked(facts(outputs=TrapList([output()])), 'outputs_invalid')
        self.assertEqual(calls, [])

    def test_clients_and_capabilities_are_closed_typed_and_bounded(self):
        for clients in (None, 'steam', {}, [1], [True], [b'steam'],
                        ['synthetic-private'], ['/synthetic/private'], ['steam --private']):
            self.blocked(facts(existing_clients=clients), 'clients_invalid')
        for capabilities in (None, 'gamescope', {}, [1], [True], [b'gamescope'],
                             ['synthetic-private'], ['gamescope --private']):
            self.blocked(facts(capabilities=capabilities), 'capabilities_invalid')
        self.blocked(facts(existing_clients=['steam'] * 1024), 'clients_limit')
        self.blocked(facts(capabilities=['gamescope'] * 1024), 'capabilities_limit')

    def test_inventory_order_does_not_change_result_and_collections_are_detached(self):
        first = facts(existing_clients=['steam', 'gamescope'], capabilities=['vkcube', 'gamescope'])
        second = dict(reversed(tuple(first.items())))
        second['outputs'] = list(reversed(first['outputs']))
        second['existing_clients'] = list(reversed(first['existing_clients']))
        second['capabilities'] = list(reversed(first['capabilities']))
        a = collect.collect_snapshot(first)
        b = collect.collect_snapshot(second)
        self.assertTrue(a.ok, a.reasons)
        self.assertEqual(a, b)
        self.assertEqual(first['existing_clients'], ['steam', 'gamescope'])
        self.assertEqual(first['capabilities'], ['vkcube', 'gamescope'])
        first['existing_clients'].clear()
        first['capabilities'].clear()
        self.assertEqual(a.snapshot.existing_clients, ('gamescope', 'steam'))
        self.assertEqual(a.snapshot.capabilities, frozenset({'gamescope', 'vkcube'}))

    def test_multiple_failures_are_atomic_sorted_and_deduplicated(self):
        source = facts(session_type=None, desktop=None, kwin_running=1, decky_active=0,
                       outputs=[None, None], existing_clients=[False], capabilities=[False])
        result = self.blocked(source)
        self.assertEqual(result.reasons, ('capabilities_invalid', 'clients_invalid', 'desktop_invalid',
                                          'output_invalid', 'session_flags_invalid', 'session_type_invalid'))
        self.assertEqual(result.reasons, tuple(sorted(set(result.reasons))))
        self.assertEqual(result, collect.collect_snapshot(dict(reversed(tuple(source.items())))))

    def test_client_and_capability_container_subclasses_are_never_visited(self):
        calls = []

        class TrapTuple(tuple):
            def __iter__(self):
                calls.append('iter')
                raise RuntimeError('synthetic-private')

        class TrapSet(set):
            def __len__(self):
                calls.append('len')
                raise SystemExit('synthetic-private')

        self.blocked(facts(existing_clients=TrapTuple(('steam',))), 'clients_invalid')
        self.blocked(facts(capabilities=TrapSet({'gamescope'})), 'capabilities_invalid')
        self.assertEqual(calls, [])

    def test_unknown_fields_in_typed_output_records_are_rejected(self):
        for field in ('serial', 'raw_edid', 'path', 'argv', 'description'):
            for target in ('output', 'identity'):
                record = output()
                object.__setattr__(record if target == 'output' else record.identity,
                                   field, 'synthetic-private')
                self.blocked(facts(outputs=[record]), 'output_invalid')

    def test_private_input_is_never_rendered_or_retained_on_failure(self):
        marker = 'synthetic-private'

        class Opaque:
            def __str__(self):
                raise AssertionError('must not stringify input')

            def __repr__(self):
                raise AssertionError('must not represent input')

        for name in ('raw_edid', 'serial', 'path', 'argv', 'environment', 'description'):
            source = facts()
            source[name] = Opaque()
            result = self.blocked(source, 'fields_unknown')
            self.assertNotIn(name, result.reasons)
        for source in (facts(outputs=[output(identity=OutputIdentity(HASH_A, marker, marker))]),
                       facts(outputs=[output(gpu_pci='/synthetic/private')]),
                       facts(existing_clients=['steam --synthetic-private']),
                       facts(capabilities=[Opaque()])):
            self.blocked(source)
        success = collect.collect_snapshot(facts())
        self.assertNotIn(HASH_A, repr(success))
        self.assertNotIn(HASH_B, repr(success))
        self.assertNotIn('0000:fa:01.0', repr(success))
        self.assertNotIn('DP-1', repr(success))

    def test_unexpected_constructor_failures_return_fixed_code_without_partial_snapshot(self):
        for exception in (RuntimeError('synthetic-private'), SystemExit('synthetic-private')):
            with patch.object(collect, 'SessionSnapshot', side_effect=exception):
                result = self.blocked(facts(), 'collector_failed')
                self.assertEqual(result.reasons, ('collector_failed',))

    def test_exact_limits_and_known_negative_facts_remain_representable(self):
        records = [output(format(index + 1, '064x'), 'DP-' + str(index + 1)) for index in range(16)]
        result = collect.collect_snapshot(facts(outputs=records, existing_clients=['steam'] * 16,
                                               capabilities=['gamescope', 'steam', 'vkcube']))
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(len(result.snapshot.outputs), 16)
        self.assertEqual(len(result.snapshot.existing_clients), 16)
        empty = collect.collect_snapshot(facts(outputs=[], existing_clients=[], capabilities=[],
                                              session_type='tty', desktop='gamescope',
                                              own_local_session=False, kwin_running=False,
                                              focus_service_active=True, decky_active=True))
        self.assertTrue(empty.ok, empty.reasons)
        self.assertEqual(empty.snapshot.outputs, ())
        self.assertEqual(empty.snapshot.capabilities, frozenset())
        self.assertFalse(evaluate_preflight(empty.snapshot).ok)

    def test_malformed_model_and_identity_subclasses_are_not_interrogated(self):
        calls = []

        class OutputSubclass(Output):
            def __getattribute__(self, name):
                calls.append(name)
                raise RuntimeError('synthetic-private')

        class IdentitySubclass(OutputIdentity):
            pass

        bad = object.__new__(OutputSubclass)
        self.blocked(facts(outputs=[bad]), 'output_invalid')
        self.assertEqual(calls, [])
        self.blocked(facts(outputs=[output(identity=IdentitySubclass(HASH_A))]), 'output_invalid')
