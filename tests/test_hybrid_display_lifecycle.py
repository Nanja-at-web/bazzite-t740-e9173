"""Lifecycle contracts using in-memory adapters only; no real test children."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype/hybrid-display/src'))

from hybrid_display.command import ArgvResult, EnvironmentResult, build_child_env
from hybrid_display.runner import Lifecycle, State, OwnedIdentity, Observation


class FakeClock:
    def __init__(self):
        self.value = 10.0

    def now(self):
        return self.value


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.identity = None
        self.observation = None
        self.receipt = None
        self.failure = None

    def spawn(self, argv, child_env, run_id, run_token):
        self.calls.append(('spawn', argv, dict(child_env), run_id))
        if self.failure == 'spawn':
            raise RuntimeError('synthetic-private-adapter-error')
        self.identity = OwnedIdentity(object(), 123, 'generation-A', run_id, run_token)
        return self.identity

    def inspect(self, handle):
        self.calls.append(('inspect', handle))
        if self.failure == 'inspect':
            raise RuntimeError('synthetic-private-adapter-error')
        return self.observation or Observation(self.identity, 'running')

    def verify_ownership(self, handle):
        self.calls.append(('verify', handle))
        if self.failure == 'verify':
            raise RuntimeError('synthetic-private-adapter-error')
        return self.receipt if self.receipt is not None else self.identity

    def request_terminate(self, handle):
        self.calls.append(('terminate', handle))
        if self.failure == 'terminate':
            raise RuntimeError('synthetic-private-adapter-error')
        return True

    def wait(self, handle, timeout):
        self.calls.append(('wait', handle, timeout))
        if self.failure == 'wait':
            raise RuntimeError('synthetic-private-adapter-error')
        return self.observation or Observation(self.identity, 'running')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FakeAdapter()
        self.clock = FakeClock()
        self.run = Lifecycle('run-A', self.adapter, self.clock, timeout=5)
        self.command = ArgvResult(('synthetic-client', 'two words'))
        self.env = build_child_env({'LANG': 'C'})

    def start(self):
        return self.run.start(self.command, self.env)

    def test_valid_start_uses_one_adapter_handle_and_detached_inputs(self):
        result = self.start()
        self.assertTrue(result.ok)
        self.assertEqual(result.state, State.START_REQUESTED)
        self.assertIs(result.handle, self.adapter.identity)
        self.assertIsNone(result.exit_code)
        self.assertEqual(self.adapter.calls,
                         [('spawn', ('synthetic-client', 'two words'), {'LANG': 'C'}, 'run-A')])
        self.assertEqual(self.command.argv, ('synthetic-client', 'two words'))
        self.assertEqual(dict(self.env.child_env), {'LANG': 'C'})

    def test_blocked_command_cannot_spawn(self):
        result = self.run.start(ArgvResult(('client',), ('synthetic-private-reason',)), self.env)
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('command_blocked',))
        self.assertEqual(self.adapter.calls, [])

    def test_blocked_environment_cannot_spawn(self):
        result = self.run.start(self.command, EnvironmentResult({'LANG': 'C'}, ('private',)))
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('environment_blocked',))
        self.assertEqual(self.adapter.calls, [])

    def test_empty_or_malformed_argv_never_spawns(self):
        for argv in ((), ('',), (' ',), ('client', 1), ('client\0',), 'client', None):
            with self.subTest(argv=argv):
                adapter = FakeAdapter()
                result = Lifecycle('run-A', adapter, self.clock).start(ArgvResult(argv), self.env)
                self.assertFalse(result.ok)
                self.assertEqual(adapter.calls, [])

    def test_environment_result_cannot_smuggle_unvalidated_payload(self):
        for payload in ({'LANG': 'x\0'}, {'PATH': 'private'}, {'LANG': 1}, []):
            adapter = FakeAdapter()
            result = Lifecycle('run-A', adapter, self.clock).start(
                self.command, EnvironmentResult(payload))
            self.assertFalse(result.ok)
            self.assertEqual(result.reasons, ('environment_blocked',))
            self.assertEqual(adapter.calls, [])

    def test_second_start_is_blocked_without_adapter_action(self):
        self.start()
        before = self.adapter.calls.copy()
        result = self.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('invalid_transition',))
        self.assertEqual(self.adapter.calls, before)

    def test_spawn_error_is_sanitized_and_never_retried(self):
        self.adapter.failure = 'spawn'
        try:
            result = self.start()
        except Exception:
            self.fail('Expected a structured start failure, not an adapter exception')
        self.assertEqual(result.state, State.START_FAILED)
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('spawn_failed',))
        self.assertIsNone(result.handle)
        self.assertNotIn('synthetic-private', repr(result))
        before = self.adapter.calls.copy()
        self.assertFalse(self.start().ok)
        self.assertEqual(self.adapter.calls, before)

    def test_missing_malformed_or_previous_run_handle_blocks(self):
        bad = (None, 123, OwnedIdentity(None, 123, 'gen', 'run-A'),
               OwnedIdentity(object(), True, 'gen', 'run-A'),
               OwnedIdentity(object(), 0, 'gen', 'run-A'),
               OwnedIdentity(object(), 123, '', 'run-A'),
               OwnedIdentity(object(), 123, 'gen', 'previous-run'))
        for identity in bad:
            class BadSpawn(FakeAdapter):
                def spawn(inner, argv, env, run_id, run_token):
                    inner.calls.append(('spawn',))
                    return identity
            adapter = BadSpawn()
            run = Lifecycle('run-A', adapter, self.clock)
            result = run.start(self.command, self.env)
            self.assertFalse(result.ok)
            self.assertEqual(result.state, State.OWNERSHIP_LOST)
            self.assertIsNone(result.handle)
            self.assertEqual(adapter.calls, [('spawn',)])

    def test_running_poll_never_respawns_and_snapshots_are_immutable(self):
        requested = self.start()
        for _ in range(3):
            result = self.run.poll()
            self.assertTrue(result.ok)
            self.assertEqual(result.state, State.RUNNING)
            self.assertIs(result.handle, self.adapter.identity)
        self.assertEqual(requested.state, State.START_REQUESTED)
        self.assertEqual(sum(c[0] == 'spawn' for c in self.adapter.calls), 1)
        with self.assertRaises(FrozenInstanceError):
            requested.state = State.BLOCKED
        with self.assertRaises(FrozenInstanceError):
            requested.handle.pid = 999

    def test_exit_classification_distinguishes_early_and_nonzero_exit(self):
        for confirmed, code, state, reasons in (
                (True, 0, State.EXITED, ()),
                (True, 7, State.UNEXPECTED_EXIT, ('nonzero_exit',)),
                (False, 0, State.UNEXPECTED_EXIT, ('early_exit',)),
                (False, 7, State.UNEXPECTED_EXIT, ('early_exit',))):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock)
            run.start(self.command, self.env)
            if confirmed:
                run.poll()
            adapter.observation = Observation(adapter.identity, 'exited', code)
            result = run.poll()
            self.assertEqual(result.state, state)
            self.assertEqual(result.exit_code, code)
            self.assertEqual(result.reasons, reasons)
            self.assertIsNone(result.handle)

    def test_unknown_or_malformed_observation_is_blocked(self):
        for status, code in (('unknown', None), ('running', 0), ('exited', None),
                             ('exited', True), ('exited', '0')):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock)
            run.start(self.command, self.env)
            adapter.observation = Observation(adapter.identity, status, code)
            result = run.poll()
            self.assertFalse(result.ok)
            self.assertEqual(result.reasons, ('observation_invalid',))
            self.assertIsNone(result.handle)
            self.assertIsNone(result.exit_code)

    def test_status_error_returns_sanitized_block_without_retry(self):
        self.start()
        self.adapter.failure = 'inspect'
        try:
            result = self.run.poll()
        except Exception:
            self.fail('Status adapter failure must be structured')
        self.assertEqual(result.reasons, ('inspect_failed',))
        self.assertFalse(result.ok)
        self.assertNotIn('synthetic-private', repr(result))

    def test_stop_checks_live_owned_handle_then_requests_termination_once(self):
        self.start()
        self.run.poll()
        self.adapter.calls.clear()
        result = self.run.stop()
        self.assertTrue(result.ok)
        self.assertEqual(result.state, State.TERMINATION_REQUESTED)
        handle = self.adapter.identity
        self.assertEqual(self.adapter.calls,
                         [('inspect', handle), ('verify', handle), ('terminate', handle)])
        before = self.adapter.calls.copy()
        self.assertFalse(self.run.stop().ok)
        self.assertEqual(self.adapter.calls, before)

    def test_foreign_pid_reuse_or_other_run_receipts_never_terminate(self):
        for field, value in (('handle', object()), ('pid', 456),
                             ('generation', 'reused-pid-generation'), ('run_id', 'old-run')):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock)
            run.start(self.command, self.env)
            adapter.receipt = replace(adapter.identity, **{field: value})
            result = run.stop()
            self.assertFalse(result.ok)
            self.assertEqual(result.state, State.OWNERSHIP_LOST)
            self.assertIsNone(result.handle)
            self.assertFalse(any(c[0] == 'terminate' for c in adapter.calls))

    def test_mismatched_observation_cannot_authorize_stop(self):
        self.start()
        self.adapter.observation = Observation(
            replace(self.adapter.identity, generation='other-generation'), 'running')
        result = self.run.stop()
        self.assertEqual(result.state, State.OWNERSHIP_LOST)
        self.assertFalse(any(c[0] in ('verify', 'terminate') for c in self.adapter.calls))

    def test_terminal_or_prepared_states_refuse_all_invalid_actions(self):
        result = self.run.poll()
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('invalid_transition',))
        self.assertEqual(self.adapter.calls, [])
        self.assertFalse(self.run.stop().ok)
        self.start()
        self.run.poll()
        self.adapter.observation = Observation(self.adapter.identity, 'exited', 0)
        ended = self.run.poll()
        self.assertEqual(ended.state, State.EXITED)
        before = self.adapter.calls.copy()
        for action in (self.run.poll, self.run.stop, self.start):
            self.assertFalse(action().ok)
            self.assertEqual(self.adapter.calls, before)

    def test_ownership_adapter_exception_blocks_without_termination(self):
        self.start()
        self.adapter.failure = 'verify'
        try:
            result = self.run.stop()
        except Exception:
            self.fail('Ownership failure must be structured')
        self.assertEqual(result.state, State.OWNERSHIP_LOST)
        self.assertEqual(result.reasons, ('ownership_check_failed',))
        self.assertFalse(any(c[0] == 'terminate' for c in self.adapter.calls))

    def test_termination_error_is_not_retried(self):
        self.start()
        self.adapter.failure = 'terminate'
        try:
            result = self.run.stop()
        except Exception:
            self.fail('Termination failure must be structured')
        self.assertEqual(result.reasons, ('termination_failed',))
        self.assertFalse(result.ok)
        before = self.adapter.calls.copy()
        self.assertFalse(self.run.stop().ok)
        self.assertEqual(self.adapter.calls, before)

    def test_confirmed_termination_returns_reported_exit_without_second_request(self):
        self.start()
        self.run.stop()
        self.adapter.observation = Observation(self.adapter.identity, 'exited', -15)
        result = self.run.wait()
        self.assertTrue(result.ok)
        self.assertEqual(result.state, State.TERMINATED)
        self.assertEqual(result.exit_code, -15)
        self.assertIsNone(result.handle)
        self.assertEqual(sum(c[0] == 'terminate' for c in self.adapter.calls), 1)

    def test_invalid_timeout_and_run_identity_prevent_start(self):
        for timeout in (0, -1, True, False, 301, '5', None, float('nan'), float('inf'), -float('inf')):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock, timeout=timeout)
            result = run.start(self.command, self.env)
            self.assertFalse(result.ok)
            self.assertEqual(adapter.calls, [])

    def test_invalid_or_backwards_clock_blocks_without_adapter_action(self):
        for value in (None, True, '10', -1, float('nan'), float('inf'), 10**1000):
            adapter = FakeAdapter()
            clock = FakeClock()
            clock.value = value
            result = Lifecycle('run-A', adapter, clock).start(self.command, self.env)
            self.assertFalse(result.ok)
            self.assertEqual(result.reasons, ('clock_invalid',))
            self.assertEqual(adapter.calls, [])

    def test_wait_progress_is_bounded_and_timeout_never_escalates(self):
        self.start()
        self.run.stop()
        self.clock.value = 12
        result = self.run.wait()
        self.assertEqual(result.state, State.TERMINATION_REQUESTED)
        self.assertEqual(self.adapter.calls[-1], ('wait', self.adapter.identity, 3))
        self.clock.value = 15
        before = self.adapter.calls.copy()
        result = self.run.wait()
        self.assertEqual(result.state, State.TIMEOUT)
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('termination_timeout',))
        self.assertIsNone(result.exit_code)
        self.assertIsNone(result.handle)
        self.assertEqual(self.adapter.calls, before)
        self.assertFalse(self.run.stop().ok)
        self.assertFalse(self.run.wait().ok)
        self.assertEqual(self.adapter.calls, before)

    def test_backwards_clock_blocks_stop_before_adapter_access(self):
        self.start()
        self.clock.value = 9
        before = self.adapter.calls.copy()
        result = self.run.stop()
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('clock_reversed',))
        self.assertEqual(self.adapter.calls, before)

    def test_invalid_run_identity_prevents_start(self):
        for run_id in ('', ' ', None, 1, 'a\0b'):
            adapter = FakeAdapter()
            result = Lifecycle(run_id, adapter, self.clock).start(self.command, self.env)
            self.assertFalse(result.ok)
            self.assertEqual(adapter.calls, [])


    def test_wait_detects_elapsed_deadline_after_adapter_progress(self):
        self.start()
        self.run.stop()
        original_wait = self.adapter.wait
        def progress(handle, timeout):
            self.clock.value = 15
            return original_wait(handle, timeout)
        self.adapter.wait = progress
        result = self.run.wait()
        self.assertEqual(result.state, State.TIMEOUT)
        self.assertEqual(result.reasons, ('termination_timeout',))
        self.assertEqual(sum(c[0] == 'terminate' for c in self.adapter.calls), 1)


    def test_wait_adapter_error_is_sanitized_without_repeated_wait(self):
        self.start()
        self.run.stop()
        self.adapter.failure = 'wait'
        try:
            result = self.run.wait()
        except Exception:
            self.fail('Wait failure must be structured')
        self.assertEqual(result.reasons, ('wait_failed',))
        self.assertFalse(result.ok)
        self.assertIsNone(result.handle)
        self.assertNotIn('synthetic-private', repr(result))
        before = self.adapter.calls.copy()
        self.assertFalse(self.run.wait().ok)
        self.assertEqual(self.adapter.calls, before)


    def test_false_or_wrong_type_termination_acknowledgement_blocks(self):
        for acknowledgement in (False, None, 1, 'yes'):
            adapter = FakeAdapter()
            def reject(handle):
                adapter.calls.append(('terminate', handle))
                return acknowledgement
            adapter.request_terminate = reject
            run = Lifecycle('run-A', adapter, self.clock)
            run.start(self.command, self.env)
            result = run.stop()
            self.assertFalse(result.ok)
            self.assertEqual(result.reasons, ('termination_unconfirmed',))
            self.assertIsNone(result.handle)
            before = adapter.calls.copy()
            self.assertFalse(run.stop().ok)
            self.assertEqual(adapter.calls, before)


    def test_numeric_or_text_pid_surrogates_are_not_process_handles(self):
        for token in (123, '123', True, b'handle', (), []):
            adapter = FakeAdapter()
            original = adapter.spawn
            def surrogate(argv, env, run_id, run_token):
                return replace(original(argv, env, run_id, run_token), handle=token)
            adapter.spawn = surrogate
            result = Lifecycle('run-A', adapter, self.clock).start(self.command, self.env)
            self.assertFalse(result.ok)
            self.assertEqual(result.state, State.OWNERSHIP_LOST)
            self.assertIsNone(result.handle)


    def test_previous_run_handle_rejected_even_with_reused_run_label(self):
        first = self.start()
        adapter = FakeAdapter()
        def stale(argv, env, run_id, run_token):
            adapter.calls.append(('spawn',))
            return first.handle
        adapter.spawn = stale
        result = Lifecycle('run-A', adapter, self.clock).start(self.command, self.env)
        self.assertFalse(result.ok)
        self.assertEqual(result.state, State.OWNERSHIP_LOST)
        self.assertIsNone(result.handle)
        self.assertEqual(adapter.calls, [('spawn',)])


    def test_poll_cannot_bypass_termination_deadline(self):
        self.start()
        self.run.stop()
        self.clock.value = 15
        before = self.adapter.calls.copy()
        result = self.run.poll()
        self.assertEqual(result.state, State.TIMEOUT)
        self.assertEqual(result.reasons, ('termination_timeout',))
        self.assertEqual(self.adapter.calls, before)


    def test_stop_deadline_must_be_representable_before_termination(self):
        self.clock.value = 1e300
        self.start()
        result = self.run.stop()
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('deadline_invalid',))
        self.assertFalse(any(c[0] == 'terminate' for c in self.adapter.calls))


    def test_already_exited_process_is_not_terminated(self):
        for confirmed in (False, True):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock)
            run.start(self.command, self.env)
            if confirmed:
                run.poll()
            adapter.observation = Observation(adapter.identity, 'exited', 0)
            result = run.stop()
            self.assertEqual(result.state, State.EXITED if confirmed else State.UNEXPECTED_EXIT)
            self.assertEqual(result.exit_code, 0)
            self.assertFalse(any(c[0] in ('verify', 'terminate', 'wait') for c in adapter.calls))

    def test_false_missing_or_wrong_type_ownership_receipt_blocks(self):
        for receipt in (False, True, 123, 'private', {}, []):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock)
            run.start(self.command, self.env)
            adapter.receipt = receipt
            result = run.stop()
            self.assertEqual(result.state, State.OWNERSHIP_LOST)
            self.assertEqual(result.reasons, ('ownership_unverified',))
            self.assertFalse(any(c[0] == 'terminate' for c in adapter.calls))
        self.start()
        self.adapter.verify_ownership = lambda handle: None
        self.assertEqual(self.run.stop().state, State.OWNERSHIP_LOST)

    def test_wrong_type_inspect_and_wait_observations_are_structured(self):
        for wrong in (None, 1, True, 'private', {}, []):
            for action in ('poll', 'wait'):
                adapter = FakeAdapter()
                run = Lifecycle('run-A', adapter, self.clock)
                run.start(self.command, self.env)
                if action == 'wait':
                    run.stop()
                    adapter.wait = lambda handle, timeout: wrong
                else:
                    adapter.inspect = lambda handle: wrong
                result = getattr(run, action)()
                self.assertEqual(result.reasons, ('observation_invalid',))
                self.assertFalse(result.ok)
                self.assertIsNone(result.handle)
                self.assertIsNone(result.exit_code)

    def test_lost_ownership_before_wait_prevents_progress(self):
        self.start()
        self.run.stop()
        self.adapter.receipt = replace(self.adapter.identity, generation='reused')
        result = self.run.wait()
        self.assertEqual(result.state, State.OWNERSHIP_LOST)
        self.assertFalse(any(c[0] == 'wait' for c in self.adapter.calls))
        self.assertEqual(sum(c[0] == 'terminate' for c in self.adapter.calls), 1)

    def test_poll_preserves_stop_pending_and_can_confirm_exit(self):
        self.start()
        self.run.stop()
        self.assertEqual(self.run.poll().state, State.TERMINATION_REQUESTED)
        self.assertFalse(self.run.stop().ok)
        self.adapter.observation = Observation(self.adapter.identity, 'exited', 0)
        self.assertEqual(self.run.poll().state, State.TERMINATED)
        self.assertEqual(sum(c[0] == 'terminate' for c in self.adapter.calls), 1)

    def test_clock_exception_is_sanitized_and_stops_before_spawn(self):
        def fail():
            raise ValueError('synthetic-private-clock-error')
        self.clock.now = fail
        result = self.start()
        self.assertEqual(result.reasons, ('clock_failed',))
        self.assertFalse(result.ok)
        self.assertEqual(self.adapter.calls, [])
        self.assertNotIn('synthetic-private', repr(result))

    def test_bad_clock_after_wait_withholds_handle_and_exit(self):
        for value, reason in ((9, 'clock_reversed'), (True, 'clock_invalid'),
                              (float('nan'), 'clock_invalid'), (float('inf'), 'clock_invalid')):
            adapter, clock = FakeAdapter(), FakeClock()
            run = Lifecycle('run-A', adapter, clock)
            run.start(self.command, self.env)
            run.stop()
            def progress(handle, timeout):
                clock.value = value
                return Observation(adapter.identity, 'exited', 0)
            adapter.wait = progress
            result = run.wait()
            self.assertFalse(result.ok)
            self.assertEqual(result.reasons, (reason,))
            self.assertIsNone(result.handle)
            self.assertIsNone(result.exit_code)

    def test_wait_before_stop_or_after_completion_has_no_adapter_action(self):
        for stage in ('prepared', 'started', 'running', 'terminated'):
            adapter = FakeAdapter()
            run = Lifecycle('run-A', adapter, self.clock)
            if stage != 'prepared':
                run.start(self.command, self.env)
            if stage in ('running', 'terminated'):
                run.poll()
            if stage == 'terminated':
                run.stop()
                adapter.observation = Observation(adapter.identity, 'exited', 0)
                run.wait()
            before = adapter.calls.copy()
            self.assertFalse(run.wait().ok)
            self.assertEqual(adapter.calls, before)

    def test_synthetic_payload_and_adapter_metadata_stay_out_of_representations(self):
        secret = 'synthetic-private-payload'
        command = ArgvResult(('synthetic-client', secret))
        env = build_child_env({'LANG': secret})
        result = self.run.start(command, env)
        self.assertTrue(result.ok)
        self.assertNotIn(secret, repr(self.run))
        self.assertNotIn(secret, repr(result))
        self.assertNotIn(secret, repr(result.handle))
        self.adapter.receipt = replace(self.adapter.identity, generation=secret)
        blocked = self.run.stop()
        self.assertEqual(blocked.reasons, ('ownership_unverified',))
        self.assertNotIn(secret, repr(blocked))
        self.assertNotIn(secret, str(blocked.reasons))
        self.assertEqual(command.argv, ('synthetic-client', secret))
        self.assertEqual(dict(env.child_env), {'LANG': secret})

    def test_codes_are_deterministic_and_no_adapter_message_is_forwarded(self):
        results = []
        for _ in range(2):
            adapter = FakeAdapter()
            adapter.failure = 'spawn'
            run = Lifecycle('run-A', adapter, self.clock)
            results.append(run.start(self.command, self.env))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0].reasons, ('spawn_failed',))
        self.assertEqual(results[0].status, 'blocked')


    def test_clock_reversal_during_ownership_check_prevents_termination(self):
        self.start()
        def verify(handle):
            self.clock.value = 9
            return self.adapter.identity
        self.adapter.verify_ownership = verify
        result = self.run.stop()
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('clock_reversed',))
        self.assertFalse(any(c[0] == 'terminate' for c in self.adapter.calls))


    def test_wait_rechecks_remaining_budget_after_ownership_verification(self):
        self.start()
        self.run.stop()
        def verify(handle):
            self.clock.value = 15
            return self.adapter.identity
        self.adapter.verify_ownership = verify
        result = self.run.wait()
        self.assertEqual(result.state, State.TIMEOUT)
        self.assertFalse(any(c[0] == 'wait' for c in self.adapter.calls))


    def test_wait_budget_and_clock_errors_after_verification(self):
        for value, reason, budget in ((14, None, 1), (15, 'termination_timeout', None),
                                     (9, 'clock_reversed', None), (float('nan'), 'clock_invalid', None)):
            adapter, clock = FakeAdapter(), FakeClock()
            run = Lifecycle('run-A', adapter, clock)
            run.start(self.command, self.env)
            run.stop()
            def verify(handle):
                clock.value = value
                return adapter.identity
            adapter.verify_ownership = verify
            result = run.wait()
            waits = [c for c in adapter.calls if c[0] == 'wait']
            if reason:
                self.assertEqual(result.reasons, (reason,))
                self.assertEqual(waits, [])
            else:
                self.assertTrue(result.ok)
                self.assertEqual(waits, [('wait', adapter.identity, budget)])


    def test_poll_checks_clock_after_inspection_before_publishing_status(self):
        self.start()
        def inspect(handle):
            self.clock.value = 9
            return Observation(self.adapter.identity, 'running')
        self.adapter.inspect = inspect
        result = self.run.poll()
        self.assertFalse(result.ok)
        self.assertEqual(result.reasons, ('clock_reversed',))
        self.assertIsNone(result.handle)


    def test_pending_poll_reports_deadline_crossed_during_inspection(self):
        self.start()
        self.run.stop()
        def inspect(handle):
            self.clock.value = 15
            return Observation(self.adapter.identity, 'running')
        self.adapter.inspect = inspect
        result = self.run.poll()
        self.assertEqual(result.state, State.TIMEOUT)
        self.assertEqual(result.reasons, ('termination_timeout',))
        self.assertEqual(sum(c[0] == 'terminate' for c in self.adapter.calls), 1)
