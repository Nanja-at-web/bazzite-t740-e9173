"""EDID resolution against synthetic data, never host display state."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-display/src"))

from hybrid_display.model import OutputIdentity, Output, OutputResolution
from hybrid_display.outputs import resolve_output

HASH_A = "ab" * 32
HASH_B = "cd" * 32


def output(edid=HASH_A, connector="DP-1", **changes):
    return replace(Output(OutputIdentity(edid, "ACI", "VG248"),
                          "0000:00:02.0", connector, connector, True, False, True),
                   **changes)


class OutputTests(unittest.TestCase):
    def test_unique_active_edid_matches(self):
        wanted = output()
        result = resolve_output([output(HASH_B, "DP-2"), wanted], HASH_A)
        self.assertIsInstance(result, OutputResolution)
        self.assertTrue(result.ok)
        self.assertIs(result.output, wanted)
        self.assertEqual(result.reasons, ())

    def test_no_match_is_blocked_without_first_output_fallback(self):
        result = resolve_output([output()], HASH_B)
        self.assertFalse(result.ok)
        self.assertIsNone(result.output)
        self.assertEqual(result.reasons, ('selection_not_found',))

    def test_duplicate_hashes_are_ambiguous_even_if_one_is_disabled(self):
        for second in (output(HASH_A, 'DP-2'), output(HASH_A, 'DP-2', enabled=False)):
            with self.subTest(second=second):
                result = resolve_output([output(), second], HASH_A)
                self.assertFalse(result.ok)
                self.assertIsNone(result.output)
                self.assertEqual(result.reasons, ('selection_ambiguous',))

    def test_hash_request_is_case_insensitive(self):
        result = resolve_output([output()], HASH_A.upper())
        self.assertTrue(result.ok)
        self.assertEqual(result.output.identity.edid_sha256, HASH_A)

    def test_identity_stores_normalized_hash(self):
        actual = output(HASH_A.upper())
        self.assertEqual(actual.identity.edid_sha256, HASH_A)
        self.assertTrue(resolve_output([actual], HASH_A).ok)

    def test_invalid_hash_length_is_rejected(self):
        for value in ('a' * 63, 'a' * 65, ''):
            with self.subTest(value=value):
                result = resolve_output([output(value)], value)
                self.assertFalse(result.ok)
                self.assertIsNone(result.output)
                self.assertEqual(result.reasons, ('selection_invalid',))

    def test_invalid_hex_characters_are_rejected(self):
        for value in ('g' * 64, 'é' * 64, ' ' + 'a' * 63):
            with self.subTest(value=value):
                result = resolve_output([output(value)], value)
                self.assertFalse(result.ok)
                self.assertEqual(result.reasons, ('selection_invalid',))

    def test_missing_or_wrong_type_hash_is_rejected_without_exceptions(self):
        for value in (None, 64, b'a' * 64, [], {}):
            with self.subTest(value=value):
                try:
                    result = resolve_output([output()], value)
                except (TypeError, AttributeError, ValueError) as error:
                    self.fail('Expected structured rejection, got ' + type(error).__name__)
                self.assertFalse(result.ok)
                self.assertEqual(result.reasons, ('selection_invalid',))

    def test_connected_but_disabled_match_is_fully_rejected(self):
        result = resolve_output([output(enabled=False)], HASH_A)
        self.assertFalse(result.ok)
        self.assertIsNone(result.output)
        self.assertEqual(result.reasons, ('selected_output_disabled',))

    def test_disconnected_match_is_blocked(self):
        result = resolve_output([output(connected=False, enabled=False)], HASH_A)
        self.assertFalse(result.ok)
        self.assertIsNone(result.output)
        self.assertIn('selected_output_disconnected', result.reasons)
        self.assertIn('selected_output_disabled', result.reasons)

    def test_mirrored_match_is_blocked(self):
        result = resolve_output([output(mirrored=True)], HASH_A)
        self.assertFalse(result.ok)
        self.assertIsNone(result.output)
        self.assertIn('selected_output_mirrored', result.reasons)

    def test_malformed_output_data_is_blocked_without_exceptions(self):
        for outputs in (None, 'DP-1', [None], [output(identity=None)],
                        [output(enabled='yes')], [output(mirrored=0)],
                        [output(connected=None)], [output(gpu_pci='')],
                        [output(kwin_name='')], [output(drm_connector='')],
                        [output(identity=OutputIdentity(None))],
                        [output(connected=False, enabled=True)]):
            with self.subTest(outputs=outputs):
                try:
                    result = resolve_output(outputs, HASH_A)
                except (TypeError, AttributeError, ValueError) as error:
                    self.fail('Expected structured rejection, got ' + type(error).__name__)
                self.assertFalse(result.ok)
                self.assertIsNone(result.output)
                self.assertIn('outputs_invalid', result.reasons)

    def test_duplicate_output_addresses_are_inconsistent(self):
        for second in (output(HASH_B), output(HASH_B, 'DP-2', kwin_name='DP-1')):
            with self.subTest(second=second):
                result = resolve_output([output(), second], HASH_A)
                self.assertFalse(result.ok)
                self.assertEqual(result.reasons, ('outputs_invalid',))

    def test_descriptive_metadata_does_not_change_primary_identity(self):
        first = OutputIdentity(HASH_A, 'ACI', 'VG248')
        second = OutputIdentity(HASH_A.upper(), 'renamed', 'other label')
        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))

    def test_full_hash_is_not_accidentally_exposed_by_model_repr(self):
        self.assertNotIn(HASH_A, repr(output()))
        self.assertNotIn(HASH_A, repr(output().identity))

    def test_identity_does_not_retain_invalid_or_raw_hash_values(self):
        for value in (None, b'raw-edid', 'not-a-hash', 'g' * 64, 'a' * 63):
            with self.subTest(value=value):
                self.assertIsNone(OutputIdentity(value).edid_sha256)

    def test_connector_change_preserves_identity_and_resolves_new_address(self):
        before = output()
        after = replace(before, drm_connector="DP-9", kwin_name="DP-9")
        self.assertEqual(before.identity, after.identity)
        self.assertIs(resolve_output([after], HASH_A).output, after)

    def test_same_model_is_not_an_identity_or_a_fallback(self):
        first, second = output(), output(HASH_B, "DP-2")
        self.assertEqual(first.identity.model, second.identity.model)
        self.assertNotEqual(first.identity, second.identity)
        self.assertIs(resolve_output([first, second], HASH_B).output, second)
        self.assertFalse(resolve_output([first, second], "VG248").ok)
        self.assertFalse(resolve_output([first, second], "DP-1").ok)

    def test_resolver_leaves_input_list_and_objects_unchanged(self):
        from copy import deepcopy
        values = [output(HASH_B, "DP-2"), output()]
        before = deepcopy(values)
        chosen = values[1]
        for wanted in (HASH_A, HASH_B, None, "not-a-hash", "ef" * 32):
            resolve_output(values, wanted)
            self.assertEqual(values, before)
        self.assertIs(values[1], chosen)

    def test_missing_hash_and_empty_inventory_never_match(self):
        self.assertEqual(resolve_output([], HASH_A).reasons, ("selection_not_found",))
        self.assertEqual(resolve_output([output()], None).reasons, ("selection_invalid",))
        self.assertFalse(resolve_output([output(identity=OutputIdentity(None))], HASH_A).ok)
