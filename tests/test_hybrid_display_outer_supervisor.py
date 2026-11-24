"""Only injected clock/process/filesystem primitives; never execute a client."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display import outer_session as session
from hybrid_display import outer_supervisor as supervisor
from tests.test_hybrid_display_outer_session import binaries, output_text


class Clock:
    value = 0.0
    def now(self):
        return self.value
    def sleep(self, amount):
        self.value += amount


class IO:
    def __init__(self):
        self.events = []
        self.replies = [supervisor.Reply(output_text())]
        self.ep = supervisor.Endpoint(1000, '/run/user/1000', 'outer-fixture',
                                      'outer-fixture', 1000, True, True, (1, 2))
        self.ready = True
        self.spawn_error = False
        self.exit = 0
    def endpoint(self):
        self.events.append('endpoint')
        return self.ep
    def query(self, endpoint, remaining, limit):
        self.events.append(('query', remaining, limit))
        return self.replies.pop(0)
    def wait_ready(self, remaining):
        self.events.append('ready')
        return self.ready
    def start(self, argv):
        self.events.append(('start', argv))
        if self.spawn_error:
            raise RuntimeError('synthetic-private')
        return 1
    def poll(self, token):
        self.events.append(('poll', token))
        return self.exit
    def finish(self):
        self.events.append('finish')
        return True


class SupervisorTests(unittest.TestCase):
    def test_runtime_path_owner_symlink_and_socket_binding(self):
        io = IO()
        self.assertTrue(supervisor.endpoint_valid(io.ep))
        for change in ({'runtime': '/tmp/foreign'}, {'runtime': '/run/user/1000/..'},
                       {'safe_components': False}, {'owner': 1001}, {'socket': False},
                       {'name': '../outer'}, {'name': '/tmp/outer'},
                       {'name': 'x'*100}, {'expected_name': 'different'}, {'uid': True}):
            self.assertFalse(supervisor.endpoint_valid(replace(io.ep, **change)))

    def test_capture_two_seconds_and_bounded_combined_output(self):
        io, clock = IO(), Clock()
        result = supervisor.capture(io, clock)
        self.assertTrue(result.ok)
        self.assertIn(('query', 2.0, 262144), io.events)

    def test_retry_only_transient_process_failures_maximum_three(self):
        io, clock = IO(), Clock()
        io.replies = [supervisor.Reply(status=1)]*3
        result = supervisor.capture(io, clock)
        self.assertEqual(result.reason, 'provider_failed')
        self.assertEqual(sum(type(e) is tuple and e[0]=='query' for e in io.events), 3)
        self.assertLessEqual(clock.value, 5)

    def test_parser_error_never_retries_and_raw_output_is_private(self):
        io = IO()
        io.replies = [supervisor.Reply(b'synthetic-private')]
        result = supervisor.capture(io, Clock())
        self.assertEqual(result.reason, 'output_invalid')
        self.assertNotIn('synthetic-private', repr(result))
        self.assertEqual(sum(type(e) is tuple and e[0]=='query' for e in io.events), 1)

    def test_oversize_stderr_timeout_and_endpoint_replacement_block(self):
        for reply in (supervisor.Reply(b'', b'x'*262145),
                      supervisor.Reply(limited=True)):
            io = IO()
            io.replies = [reply]
            self.assertEqual(supervisor.capture(io, Clock()).reason, 'provider_limit')
        io = IO()
        io.replies = [supervisor.Reply(timed_out=True)]*3
        self.assertEqual(supervisor.capture(io, Clock()).reason, 'provider_failed')

    def test_dry_run_does_not_touch_adapter(self):
        io = IO()
        plan = session.make_plan({}, binaries()).value
        result = supervisor.supervise(plan, io, Clock())
        self.assertTrue(result.ok)
        self.assertEqual(io.events, [])

    def test_forged_outer_plan_cannot_enter_privileged_adapter(self):
        calls = []
        class Trap:
            def __getattr__(self, name):
                calls.append(name)
                raise RuntimeError('private')
        bad = session.Plan(inner_width=True, execute=True)
        result = supervisor.launch_outer(bad, Trap(), Clock())
        self.assertEqual(result.reason, 'config_invalid')
        self.assertEqual(calls, [])

    def test_outputs_then_active_script_then_gamescope_with_steam(self):
        io = IO()
        plan = session.make_plan({'execute': True}, binaries()).value
        result = supervisor.supervise(plan, io, Clock())
        self.assertTrue(result.ok)
        argv = supervisor.gamescope_argv(plan)
        self.assertEqual(argv, ('/usr/bin/gamescope','--backend','wayland',
            '-W','1280','-H','720','-w','1280','-h','720','--steam','--','/usr/bin/steam','-gamepadui'))
        start = io.events.index(('start', argv))
        self.assertLess(io.events.index('ready'), start)
        self.assertLess(next(i for i,e in enumerate(io.events) if type(e) is tuple and e[0]=='query'), start)
        self.assertNotIn('placement_success', io.events)
        self.assertEqual(io.events[-1:], ['finish'])

    def test_no_start_after_provider_or_script_failure(self):
        plan = session.make_plan({'execute': True}, binaries()).value
        for fault in ('provider', 'script'):
            io = IO()
            if fault == 'provider': io.replies = [supervisor.Reply(b'bad')]
            else: io.ready = False
            result = supervisor.supervise(plan, io, Clock())
            self.assertFalse(result.ok)
            self.assertFalse(any(type(e) is tuple and e[0]=='start' for e in io.events))
            self.assertEqual(io.events[-1:], ['finish'])

    def test_start_failure_and_premature_payload_end_are_atomic(self):
        plan = session.make_plan({'execute': True}, binaries()).value
        for fault in ('spawn', 'payload'):
            io = IO()
            io.spawn_error = fault == 'spawn'
            io.exit = 1
            result = supervisor.supervise(plan, io, Clock())
            self.assertFalse(result.ok)
            self.assertIsNone(result.value)
            self.assertNotIn('synthetic-private', repr(result))
            self.assertEqual(io.events[-1:], ['finish'])

    def test_cleanup_failure_overrides_an_earlier_failure(self):
        io = IO()
        io.replies = [supervisor.Reply(b'bad')]
        io.finish = lambda: False
        plan = session.make_plan({'execute': True}, binaries()).value
        self.assertEqual(supervisor.supervise(plan, io, Clock()).reason, 'cleanup_failed')

    def test_forged_plan_is_rejected_before_adapter_callbacks(self):
        io = IO()
        bad = session.Plan(inner_width=True, execute=True)
        self.assertEqual(supervisor.supervise(bad, io, Clock()).reason, 'config_invalid')
        self.assertEqual(io.events, [])

    def test_late_success_cannot_bypass_single_call_deadline(self):
        io, clock = IO(), Clock()
        def late(*args):
            clock.value += 2.1
            return supervisor.Reply(output_text())
        io.query = late
        self.assertFalse(supervisor.capture(io, clock).ok)

    def test_kwin_start_and_cleanup_are_one_owned_lifecycle(self):
        class Parent:
            def __init__(self): self.events=[]
            def prepare(self): self.events.append('private')
            def start_kwin(self): self.events.append('kwin'); return 1
            def poll_kwin(self, token): self.events.append(('poll',token)); return 0
            def cleanup(self): self.events.append('cleanup'); return True
        io=Parent()
        result=supervisor.launch_outer(session.Plan(execute=True),io,Clock())
        self.assertTrue(result.ok)
        self.assertEqual(io.events,['private','kwin',('poll',1),'cleanup'])

    def test_kwin_failure_cleans_private_artifacts_without_other_start(self):
        class Parent:
            def __init__(self): self.events=[]
            def prepare(self): self.events.append('private')
            def start_kwin(self): raise OSError('synthetic-private')
            def cleanup(self): self.events.append('cleanup'); return True
        io=Parent()
        result=supervisor.launch_outer(session.Plan(execute=True),io,Clock())
        self.assertEqual(result.reason,'session_failed')
        self.assertIsNone(result.value)
        self.assertEqual(io.events,['private','cleanup'])
