"""Atomic synthetic orchestration, never live host or launch acceptance."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display.adapter import assemble_facts, read_inventory
from hybrid_display.collect import FIELDS
from hybrid_display.host_reader import QueryKey, KScreenProfile
from hybrid_display.preflight import evaluate_preflight
from tests.test_hybrid_display_reader_fixtures import adapter_fixture, frame, koutput

class AdapterTests(unittest.TestCase):

    def test_session_properties_share_one_half_second_budget(self):
        reader, declarations = adapter_fixture()
        original = reader.query
        def delayed(query):
            result = original(query)
            if query.key is QueryKey.SESSION_PROPERTY:
                reader.clock.value += 0.1
            return result
        reader.query = delayed
        result = read_inventory(reader, declarations)
        self.assertEqual(result.reasons, ('source_timeout',))
        self.assertIsNone(result.snapshot)

    def test_session_properties_are_bound_to_resolved_object_path(self):
        reader, declarations = adapter_fixture()
        result = read_inventory(reader, declarations)
        self.assertTrue(result.ok, result.reasons)
        properties = [call[1] for call in reader.transport.calls
                      if call[0] == 'query' and call[1].key is QueryKey.SESSION_PROPERTY]
        self.assertTrue(properties)
        self.assertTrue(all(getattr(query, 'object_path', None) == '/session/s1'
                            for query in properties))

    def test_exact_nine_facts_actual_collector_detachment_and_no_permission(self):
        reader, declarations = adapter_fixture()
        facts = assemble_facts(reader, declarations)
        self.assertTrue(facts.ok, facts.reasons)
        self.assertEqual(set(facts.value.to_collector()), FIELDS)
        reader, declarations = adapter_fixture()
        result = read_inventory(reader, declarations)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(len(result.snapshot.outputs), 2)
        self.assertIsNone(result.snapshot.gaming_edid_sha256)
        self.assertIn('selection_missing', evaluate_preflight(result.snapshot).reasons)
        self.assertFalse(hasattr(result, 'expose_wayland'))
        self.assertNotIn('0000:01:00.0', repr(result))

    def test_session_gate_precedes_gui_and_unknown_declarations_block(self):
        reader, declarations = adapter_fixture(session_changes={'Remote': True})
        result = assemble_facts(reader, declarations)
        self.assertEqual(result.reasons, ('session_unverified',))
        self.assertFalse(any((call[0] == 'query' and call[1].bus == 'session' for call in reader.transport.calls)))
        for changes, reason in (({'focus_service_active': None}, 'declaration_missing'), ({'clients_complete': False}, 'client_inventory_unverified'), ({'kscreen_profile': KScreenProfile.UNKNOWN}, 'kscreen_profile_unverified')):
            reader, declarations = adapter_fixture()
            result = read_inventory(reader, replace(declarations, **changes))
            self.assertEqual(result.reasons, (reason,))
            self.assertIsNone(result.snapshot)
            self.assertEqual(reader.transport.calls, [])

    def test_generic_reader_and_public_complete_bool_cannot_grant_live_success(self):
        reader, declarations = adapter_fixture()

        class OrdinaryReader:

            def read_env(self, key):
                raise AssertionError('must remain blocked')

            def read_file(self, source):
                raise AssertionError('must remain blocked')

            def query(self, query):
                raise AssertionError('must remain blocked')
        result = read_inventory(OrdinaryReader(), declarations)
        self.assertEqual(result.reasons, ('client_inventory_unverified',))
        self.assertIsNone(result.snapshot)

    def test_any_second_pass_owner_or_output_change_discards_everything(self):
        for options in ({'owner_changed': True}, {'second_config': frame([koutput(1), koutput(2, scale=1.25)])}):
            reader, declarations = adapter_fixture(**options)
            result = read_inventory(reader, declarations)
            self.assertEqual(result.reasons, ('inventory_changed',))
            self.assertIsNone(result.snapshot)

    def test_uid_card_variation_client_conflict_and_immutable_declarations(self):
        reader, declarations = adapter_fixture(uid=1234, card=3, client_pids=(20,))
        result = read_inventory(reader, declarations)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(result.snapshot.existing_clients, ('steam',))
        self.assertIn('process_conflict', evaluate_preflight(result.snapshot).reasons)
        reader, declarations = adapter_fixture()
        result = read_inventory(reader, replace(declarations, client_pids=[20]))
        self.assertEqual(result.reasons, ('input_invalid',))
        self.assertEqual(reader.transport.calls, [])

    def test_success_invokes_real_collector_exactly_once(self):
        from unittest.mock import patch
        from hybrid_display import collect
        reader, declarations = adapter_fixture()
        with patch.object(collect, 'collect_snapshot', wraps=collect.collect_snapshot) as observed:
            result = read_inventory(reader, declarations)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(observed.call_count, 1)

    def test_total_bytes_are_shared_across_both_passes(self):
        reader, declarations = adapter_fixture(output_count=16, edid_blocks=32)
        result = read_inventory(reader, declarations)
        self.assertEqual(result.reasons, ('source_limit',))
        self.assertIsNone(result.snapshot)
        self.assertLessEqual(reader.bytes_used, 262144)
        configs = [call for call in reader.transport.calls if call[0] == 'query' and call[1].key is QueryKey.CONFIG]
        self.assertEqual(len(configs), 2)
        self.assertFalse(reader.transport._handles)

    def test_total_deadline_is_shared_across_passes_and_stops_next_read(self):
        reader, declarations = adapter_fixture()
        body = reader.transport.read_body
        file_open = reader.transport.open_readonly

        def advance_body(handle, size):
            # Exercise the global budget without tripping the separate B4 gate.
            reader.clock.value += 0.05
            return body(handle, size)

        def advance_file(source):
            reader.clock.value += 0.075
            return file_open(source)
        reader.transport.read_body = advance_body
        reader.transport.open_readonly = advance_file
        result = read_inventory(reader, declarations)
        self.assertEqual(result.reasons, ('source_timeout',))
        self.assertIsNone(result.snapshot)
        configs = [call for call in reader.transport.calls if call[0] == 'query' and call[1].key is QueryKey.CONFIG]
        self.assertEqual(len(configs), 2)
        self.assertFalse(reader.transport._handles)

    def test_missing_source_and_collector_error_discard_all_payloads(self):
        from unittest.mock import patch
        from hybrid_display import collect
        reader, declarations = adapter_fixture(omit_edid=True)
        result = read_inventory(reader, declarations)
        self.assertEqual(result.reasons, ('reader_failed',))
        self.assertIsNone(result.snapshot)
        reader, declarations = adapter_fixture()
        with patch.object(collect, 'collect_snapshot', side_effect=RuntimeError('private')):
            result = read_inventory(reader, declarations)
        self.assertEqual(result.reasons, ('collector_blocked',))
        self.assertIsNone(result.snapshot)
        self.assertNotIn('private', repr(result))

    def test_malformed_declaration_slots_and_metaclass_never_callback(self):
        from hybrid_display.host_reader import DeclaredFacts
        calls = []

        class Meta(type):

            def __eq__(self, other):
                calls.append('type-eq')
                return True

        class Trap(tuple, metaclass=Meta):

            def __iter__(self):
                calls.append('iter')
                raise RuntimeError('private')

            def __len__(self):
                calls.append('len')
                raise RuntimeError('private')
        for source in (object.__new__(DeclaredFacts),):
            reader, declarations = adapter_fixture()
            result = read_inventory(reader, source)
            self.assertEqual(result.reasons, ('input_invalid',))
            self.assertEqual(reader.transport.calls, [])
        reader, declarations = adapter_fixture()
        result = read_inventory(reader, replace(declarations, capabilities=Trap(('gamescope',))))
        self.assertEqual(result.reasons, ('input_invalid',))
        self.assertEqual(reader.transport.calls, [])
        self.assertEqual(calls, [])
