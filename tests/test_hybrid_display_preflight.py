"""Hardware-independent foundation contracts; all snapshots are synthetic."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-display/src"))

from hybrid_display.model import OutputIdentity, Output, SessionSnapshot, PreflightResult
from hybrid_display.preflight import evaluate_preflight

HASH_A = "a1" * 32
HASH_B = "b2" * 32


def output(edid=HASH_A, connector="DP-1", **changes):
    return replace(Output(OutputIdentity(edid, "ACI", "VG248"),
                          "0000:00:02.0", connector, connector, True, False, True),
                   **changes)


def snapshot(**changes):
    return replace(SessionSnapshot("wayland", "KDE", True, True,
                   (output(), output(HASH_B, "DP-2")), (), False, False,
                   frozenset({"gamescope", "vkcube"}), HASH_A), **changes)


class PreflightTests(unittest.TestCase):
    def test_models_cannot_be_mutated(self):
        objects = ((output().identity, "model", "other"),
                   (output(), "enabled", False),
                   (snapshot(), "desktop", "gamescope"),
                   (PreflightResult(()), "findings", ("changed",)))
        for instance, field, value in objects:
            with self.subTest(model=type(instance).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(instance, field, value)

    def test_valid_plasma_wayland_is_ready(self):
        result = evaluate_preflight(snapshot())
        self.assertIsInstance(result, PreflightResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.reasons, ())

    def test_tty_and_x11_are_blocked(self):
        for mode in ('tty', 'x11'):
            with self.subTest(mode=mode):
                result = evaluate_preflight(snapshot(session_type=mode))
                self.assertIn('session_not_wayland', result.reasons)
                self.assertFalse(result.ok)

    def test_direct_gaming_mode_and_non_plasma_are_blocked(self):
        for desktop in ('gamescope', 'GNOME', '', None):
            with self.subTest(desktop=desktop):
                self.assertIn('session_not_plasma', evaluate_preflight(snapshot(desktop=desktop)).reasons)

    def test_missing_kwin_is_blocked(self):
        result = evaluate_preflight(snapshot(kwin_running=False))
        self.assertFalse(result.ok)
        self.assertIn('kwin_missing', result.reasons)

    def test_foreign_or_unknown_local_session_is_blocked(self):
        for own in (False, None, 1, 'yes'):
            with self.subTest(own=own):
                self.assertIn('session_not_local', evaluate_preflight(snapshot(own_local_session=own)).reasons)

    def test_fewer_than_two_active_outputs_are_blocked(self):
        for outputs in ((), (output(),), (output(), output(HASH_B, 'DP-2', enabled=False))):
            with self.subTest(outputs=outputs):
                self.assertIn('too_few_active_outputs', evaluate_preflight(snapshot(outputs=outputs)).reasons)

    def test_more_than_two_active_outputs_are_allowed(self):
        result = evaluate_preflight(snapshot(outputs=(output(), output(HASH_B, 'DP-2'), output('c3' * 32, 'DP-3'))))
        self.assertTrue(result.ok, result.reasons)

    def test_mirrored_active_outputs_are_blocked(self):
        result = evaluate_preflight(snapshot(outputs=(output(), output(HASH_B, 'DP-2', mirrored=True))))
        self.assertIn('mirrored_outputs', result.reasons)
        self.assertFalse(result.ok)

    def test_existing_clients_block_start(self):
        for clients in (('steam',), ('gamescope',), ('steam', 'gamescope')):
            with self.subTest(clients=clients):
                result = evaluate_preflight(snapshot(existing_clients=clients))
                self.assertIn('process_conflict', result.reasons)
                self.assertFalse(result.ok)

    def test_focus_integration_blocks_start(self):
        self.assertIn('focus_integration_active', evaluate_preflight(snapshot(focus_service_active=True)).reasons)

    def test_decky_blocks_start(self):
        self.assertIn('decky_active', evaluate_preflight(snapshot(decky_active=True)).reasons)

    def test_missing_gamescope_is_reported(self):
        self.assertIn('missing_gamescope', evaluate_preflight(snapshot(capabilities=frozenset({'vkcube'}))).reasons)

    def test_missing_graphics_client_is_reported(self):
        self.assertIn('missing_graphics_client', evaluate_preflight(snapshot(capabilities=frozenset({'gamescope'}))).reasons)

    def test_missing_selection_never_chooses_a_default(self):
        self.assertIn('selection_missing', evaluate_preflight(snapshot(gaming_edid_sha256=None)).reasons)

    def test_all_reasons_are_returned_in_deterministic_order(self):
        bad = snapshot(session_type='tty', kwin_running=False, existing_clients=('steam',),
                       focus_service_active=True, capabilities=frozenset(), gaming_edid_sha256=None)
        result = evaluate_preflight(bad)
        self.assertEqual(result.reasons, ('focus_integration_active', 'kwin_missing',
                         'missing_gamescope', 'missing_graphics_client', 'process_conflict',
                         'selection_missing', 'session_not_wayland'))
        self.assertEqual(result, evaluate_preflight(bad))

    def test_missing_description_warns_without_blocking(self):
        sparse = replace(output(), identity=OutputIdentity(HASH_A))
        result = evaluate_preflight(snapshot(outputs=(sparse, output(HASH_B, 'DP-2'))))
        self.assertTrue(hasattr(result, 'status'), 'No explicit result classification')
        self.assertEqual(result.status, 'warning')
        self.assertTrue(result.ok)
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.warnings, ('monitor_description_missing',))
        self.assertEqual(result.findings[0].severity, 'warning')
        ready = evaluate_preflight(snapshot())
        self.assertEqual(ready.status, 'success')
        blocked = evaluate_preflight(snapshot(session_type='tty', outputs=(sparse, output(HASH_B, 'DP-2'))))
        self.assertEqual(blocked.status, 'blocked')
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.warnings, ('monitor_description_missing',))

    def test_incomplete_and_wrong_typed_snapshot_is_blocked_without_exceptions(self):
        for bad in (None, {}, SessionSnapshot(),
                    snapshot(outputs=None), snapshot(outputs=('not-an-output',)),
                    snapshot(capabilities=None), snapshot(existing_clients=None),
                    snapshot(kwin_running=1), snapshot(focus_service_active=None)):
            with self.subTest(bad=bad):
                try:
                    result = evaluate_preflight(bad)
                except (TypeError, AttributeError, ValueError) as error:
                    self.fail('Expected structured rejection, got ' + type(error).__name__)
                self.assertFalse(result.ok)
                self.assertIn('snapshot_invalid', result.reasons)

    def test_snapshot_detaches_mutable_input_collections(self):
        outputs = [output(), output(HASH_B, 'DP-2')]
        clients = []
        capabilities = {'gamescope', 'vkcube'}
        current = snapshot(outputs=outputs, existing_clients=clients, capabilities=capabilities)
        outputs.clear()
        clients.append('steam')
        capabilities.clear()
        self.assertEqual(len(current.outputs), 2)
        self.assertEqual(current.existing_clients, ())
        self.assertEqual(current.capabilities, frozenset({'gamescope', 'vkcube'}))
        self.assertTrue(evaluate_preflight(current).ok)

    def test_preflight_blocks_inconsistent_output_records(self):
        for outputs in ((output(), output(HASH_B, 'DP-2', connected=False)),
                        (output(), output(HASH_B, 'DP-2', enabled=1)),
                        (output(), output(HASH_B)),
                        (output(), output(HASH_B, 'DP-2', identity=OutputIdentity(None)))):
            with self.subTest(outputs=outputs):
                result = evaluate_preflight(snapshot(outputs=outputs))
                self.assertFalse(result.ok)
                self.assertIn('outputs_invalid', result.reasons)

    def test_unknown_ambiguous_or_invalid_monitor_choice_blocks(self):
        cases = (
            (snapshot(gaming_edid_sha256='c3' * 32), 'selection_not_found'),
            (snapshot(outputs=(output(), output(HASH_A, 'DP-2'))), 'selection_ambiguous'),
            (snapshot(gaming_edid_sha256='not-a-hash'), 'selection_invalid'),
            (snapshot(gaming_edid_sha256=42), 'selection_invalid'),
            (snapshot(outputs=(output(enabled=False), output(HASH_B, 'DP-2'))), 'selected_output_disabled'),
        )
        for current, reason in cases:
            with self.subTest(reason=reason):
                result = evaluate_preflight(current)
                self.assertFalse(result.ok)
                self.assertIn(reason, result.reasons)

    def test_unknown_flags_and_missing_snapshot_fields_fail_closed(self):
        for field, value in (('session_type', None), ('desktop', None),
                             ('own_local_session', None), ('kwin_running', None),
                             ('focus_service_active', None), ('decky_active', None),
                             ('existing_clients', (None,)), ('capabilities', 'gamescope'),
                             ('outputs', (None,))):
            with self.subTest(field=field):
                result = evaluate_preflight(snapshot(**{field: value}))
                self.assertFalse(result.ok)
                self.assertIn('snapshot_invalid', result.reasons)
        blocked = evaluate_preflight(SessionSnapshot())
        self.assertIn('selection_missing', blocked.reasons)
        self.assertIn('missing_gamescope', blocked.reasons)
        self.assertIn('missing_graphics_client', blocked.reasons)

    def test_rejection_reasons_are_unique(self):
        result = evaluate_preflight(snapshot(outputs=(output(), output(HASH_B))))
        self.assertEqual(result.reasons.count('outputs_invalid'), 1)

    def test_snapshot_repr_does_not_expose_full_selected_hash(self):
        self.assertNotIn(HASH_A, repr(snapshot()))

    def test_preflight_does_not_change_inputs_and_is_order_independent(self):
        from copy import deepcopy
        current = snapshot(outputs=(output(), output(HASH_B, "DP-2")),
                           session_type="tty", existing_clients=("steam", "gamescope"))
        before = deepcopy(current)
        result = evaluate_preflight(current)
        reversed_data = replace(current, outputs=tuple(reversed(current.outputs)),
                                existing_clients=tuple(reversed(current.existing_clients)))
        self.assertEqual(result, evaluate_preflight(reversed_data))
        self.assertEqual(current, before)
        self.assertEqual(result.findings, evaluate_preflight(current).findings)
