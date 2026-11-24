"""Launcher tests inject every process and filesystem operation."""
import importlib.util
import ast
import configparser
import shlex
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from tests.test_hybrid_display_outer_session import binaries, output_text

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'prototype/hybrid-display/outer-kwin-session.py'
spec = importlib.util.spec_from_file_location('outer_launcher_fixture', FILE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class Native:
    def __init__(self):
        self.events = []
    def binaries(self):
        self.events.append('binaries')
        return binaries()
    def execute(self, plan):
        self.events.append('execute')
        return launcher.Result('ended')


class FS:
    def __init__(self, uid=1000, symlink=False):
        self.uid, self.symlink = uid, symlink
        self.closed = []
    def open(self, path, flags, **kwargs):
        if self.symlink:
            raise OSError('synthetic-private')
        return 11
    def fstat(self, fd):
        return SimpleNamespace(st_uid=self.uid, st_mode=stat.S_IFDIR | 0o700)
    def close(self, fd):
        self.closed.append(fd)


class TreeFS(FS):
    def __init__(self):
        super().__init__()
        self.events = []
        self.next_fd = 20
    def mkdir(self, name, mode, **kwargs): self.events.append(('mkdir', name, mode))
    def open(self, name, flags, *args, **kwargs):
        self.events.append(('open', name, flags))
        self.next_fd += 1
        return self.next_fd
    def fstat(self, fd):
        return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=fd)
    def write(self, fd, data): self.events.append(('write', bytes(data))); return len(data)
    def stat(self, name, **kwargs):
        return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o700,
                               st_dev=1, st_ino=self.next_fd + 1)


class LauncherTests(unittest.TestCase):
    def test_execution_requires_full_explicit_option(self):
        for option in ('--e', '--exec', '--execut'):
            adapter = Native()
            self.assertEqual(launcher.main([option], adapter, lambda value: None), 1)
            self.assertNotIn('execute', adapter.events)

    def test_kwin_socket_cannot_collide_with_private_directory(self):
        root = '/run/user/1000/hybrid-outer-0123456789abcdef'
        display = 'hybrid-outer-wl-0123456789abcdef'
        try:
            argv = launcher.kwin_argv(root, display)
        except launcher.Blocked:
            self.fail('Distinct private directory and socket names must be supported')
        self.assertEqual(argv[argv.index('--socket') + 1], display)
        self.assertNotEqual(root.rsplit('/', 1)[1], display)

    def test_launcher_end_never_attests_live_cgroup_cleanup(self):
        output = []
        self.assertEqual(launcher.main(['--execute'], Native(), output.append), 0)
        result = launcher.json.loads(output[0])
        self.assertIs(result.get('live_cgroup_cleanup_verified'), False)
        self.assertEqual(result['status'], 'launcher_ended')

    def test_broken_output_sink_is_not_retried_or_exposed_as_traceback(self):
        calls = []
        def sink(message): calls.append('emit'); raise RuntimeError('private')
        try:
            status = launcher.main([], Native(), sink)
        except RuntimeError:
            self.fail('Output failure escaped the fixed failure boundary')
        self.assertEqual(status, 1)
        self.assertEqual(calls, ['emit'])

    def test_failed_root_open_removes_only_the_confirmed_new_inode(self):
        class OpenFailureFS(TreeFS):
            def open(self, name, flags, *args, **kwargs):
                if name.startswith('hybrid-outer-'): raise OSError('private')
                return super().open(name, flags, *args, **kwargs)
            def stat(self, name, **kwargs):
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o700, st_dev=1, st_ino=99)
            def rmdir(self, name, **kwargs): self.events.append(('remove', name))
        fs = OpenFailureFS()
        tree = launcher.PrivateTree(1000, '0123456789abcdef', fs)
        with self.assertRaises(OSError): tree.create({'config/kwinrc': b'x'})
        self.assertTrue(tree.cleanup())
        self.assertIn(('remove', 'hybrid-outer-0123456789abcdef'), fs.events)

    def test_real_entry_is_guarded_and_interpreter_ignores_python_environment(self):
        source = FILE.read_text()
        self.assertTrue(source.startswith('#!/usr/bin/python3 -IB\n'))
        self.assertEqual(FILE.stat().st_mode & 0o111, 0o111)
        tree = ast.parse(source)
        self.assertTrue(any(isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
                            and any(isinstance(call, ast.Call) and ast.unparse(call.func) == 'entry'
                                    for call in ast.walk(node)) for node in tree.body))

    def test_first_stage_closes_owned_log_pipe_even_when_group_times_out(self):
        pipe = SimpleNamespace(closed=False)
        pipe.close = lambda: setattr(pipe, 'closed', True)
        group = SimpleNamespace(process=SimpleNamespace(stdout=pipe), close=lambda **kwargs: False)
        system = launcher._System(1000, {}, FS())
        self.assertFalse(system.terminate(group))
        self.assertTrue(pipe.closed)

    def test_child_display_is_a_single_validated_name_never_caller_path(self):
        system = launcher._System(1000, {}, FS(), display='hybrid-outer-wl-0123456789abcdef')
        system.checked = True
        self.assertEqual(system.child_display(), 'hybrid-outer-wl-0123456789abcdef')
        for value in ('../foreign', '/run/user/1000/foreign', 'a/b', '.', 'x' * 65):
            system.display_value = value
            with self.assertRaises(launcher.Blocked): system.child_display()

    def test_entry_defaults_to_plan_and_internal_child_still_requires_execute(self):
        io, output, calls = Native(), [], []
        self.assertEqual(launcher.entry([], io, output.append), 0)
        self.assertEqual(io.events, ['binaries'])
        root = '/run/user/1000/hybrid-outer-0123456789abcdef'
        def child(path, execute=False): calls.append((path, execute)); return 0
        self.assertEqual(launcher.entry(['--session-child', root], io, output.append, child), 1)
        self.assertEqual(calls, [])
        self.assertEqual(launcher.entry(['--execute', '--session-child', root], io, output.append, child), 0)
        self.assertEqual(calls, [(root, True)])
    def test_internal_child_requires_execute_own_parent_and_closes_directory_handles(self):
        events = []
        class BootFS(TreeFS):
            def __init__(self): super().__init__(); self.live = set()
            def open(self, *args, **kwargs):
                fd = super().open(*args, **kwargs); self.live.add(fd); return fd
            def close(self, fd): self.live.discard(fd); super().close(fd)
            def stat(self, path, **kwargs):
                return SimpleNamespace(st_uid=0 if path.startswith('/usr/bin/') else 1000,
                    st_mode=(stat.S_IFREG | 0o755) if path.startswith('/usr/bin/') else (stat.S_IFSOCK | 0o600),
                    st_dev=1, st_ino=23)
            def getppid(self): return 73
            def getpgid(self, pid): return 73
            def getsid(self, pid): return 73
        class Clock:
            def now(self): return 0
            def sleep(self, seconds): pass
        fs = BootFS()
        plan = launcher.make_plan({'execute': True}, binaries()).value
        system = SimpleNamespace(uid=1000, checked=True, fs=fs, clock=Clock(),
            ensure=lambda: events.append('boundary'),
            read=lambda *args, **kwargs: launcher.json.dumps(launcher._config(plan)).encode(),
            child_display=lambda: 'hybrid-outer-wl-0123456789abcdef')
        def runner(plan, child, clock): events.append('supervise'); return launcher.Result('ended')
        root = '/run/user/1000/hybrid-outer-0123456789abcdef'
        self.assertEqual(launcher.session_child(root, system=system, runner=runner), 1)
        self.assertEqual(events, [])
        self.assertEqual(launcher.session_child(root, True, system, runner), 0)
        self.assertEqual(events, ['boundary', 'supervise'])
        self.assertEqual(fs.live, set())
        fs.getppid = lambda: 99
        events.clear()
        self.assertEqual(launcher.session_child(root, True, system, runner), 1)
        self.assertNotIn('supervise', events)
        self.assertEqual(fs.live, set())

    def test_native_child_observes_only_owned_payload_exit(self):
        calls = []
        class Kernel:
            P_PID, WEXITED, WNOHANG, WNOWAIT, CLD_EXITED = 1, 2, 4, 8, 1
            def waitid(self, kind, pid, flags):
                calls.append((kind, pid, flags)); return SimpleNamespace(si_code=1, si_status=0)
        system = SimpleNamespace(uid=1000, checked=True, fs=Kernel())
        plan = launcher.make_plan({'execute': True}, binaries()).value
        child = launcher._Child(system, plan, '/run/user/1000/hybrid-outer-0123456789abcdef',
                                11, 12, 'hybrid-outer-wl-0123456789abcdef')
        child.game = SimpleNamespace(pid=73)
        self.assertEqual(child.poll(1), 0)
        self.assertEqual(calls, [(1, 73, 14)])

    def test_native_child_finish_is_idempotent_and_forbids_new_starts(self):
        system = SimpleNamespace(uid=1000, checked=True)
        plan = launcher.make_plan({'execute': True}, binaries()).value
        child = launcher._Child(system, plan, '/run/user/1000/hybrid-outer-0123456789abcdef',
                                11, 12, 'hybrid-outer-wl-0123456789abcdef')
        self.assertTrue(child.finish())
        self.assertTrue(child.closed)
        self.assertTrue(child.finish())
        with self.assertRaises(launcher.Blocked): child.start(launcher.gamescope_argv(plan))

    def test_native_query_uses_only_wayland_info_and_closes_probe_resources(self):
        calls = []
        class Clock:
            value = 0
            def now(self): return self.value
            def sleep(self, seconds): self.value += seconds
        class Pipe:
            def __init__(self, fd): self.fd, self.closed = fd, False
            def fileno(self): return self.fd
            def close(self): self.closed = True
        class Kernel:
            P_PID, WEXITED, WNOHANG, WNOWAIT, CLD_EXITED = 1, 2, 4, 8, 1
            def __init__(self): self.data = {41: output_text(), 42: b''}
            def stat(self, *args, **kwargs):
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFSOCK | 0o600, st_dev=1, st_ino=23)
            def read(self, fd, size):
                chunk, self.data[fd] = self.data[fd][:size], self.data[fd][size:]
                return chunk
            def waitid(self, *args): return SimpleNamespace(si_code=1, si_status=0)
            def getpgid(self, pid): return pid
            def killpg(self, pid, number):
                if number == 0: raise ProcessLookupError()
        process = SimpleNamespace(pid=73, stdout=Pipe(41), stderr=Pipe(42), wait=lambda **kwargs: 0)
        def spawn(argv, **kwargs): calls.append((argv, kwargs)); return process
        clock, kernel = Clock(), Kernel()
        system = SimpleNamespace(uid=1000, checked=True, fs=kernel, clock=clock, spawn=spawn,
            poller=lambda streams, *args: (list(streams), [], []))
        plan = launcher.make_plan({'execute': True}, binaries()).value
        child = launcher._Child(system, plan, '/run/user/1000/hybrid-outer-0123456789abcdef',
                                11, 12, 'hybrid-outer-wl-0123456789abcdef')
        reply = child.query(child.endpoint(), 2.0, 262144)
        self.assertEqual(reply.status, 0)
        self.assertEqual(reply.stdout, output_text())
        self.assertEqual(calls[0][0], ('/usr/bin/wayland-info',))
        self.assertEqual(set(calls[0][1]['env']), {'XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'LC_ALL'})
        self.assertTrue(calls[0][1]['start_new_session'])
        self.assertTrue(process.stdout.closed and process.stderr.closed)
        kernel.data = {41: b'x' * 262145, 42: b''}
        process.stdout.closed = process.stderr.closed = False
        other = launcher._Child(system, plan, child.root, 11, 12, child.display)
        overflow = other.query(other.endpoint(), 2.0, 262144)
        self.assertTrue(overflow.limited)
        self.assertLessEqual(len(overflow.stdout) + len(overflow.stderr), 262145)
        self.assertTrue(process.stdout.closed and process.stderr.closed)
        def slow(streams, unused_a, unused_b, seconds):
            clock.value += seconds
            return list(streams), [], []
        system.poller = slow
        kernel.read = lambda fd, size: b'x' if fd == 41 else b''
        last = launcher._Child(system, plan, child.root, 11, 12, child.display)
        timed = last.query(last.endpoint(), 2.0, 262144)
        self.assertTrue(timed.timed_out)
        self.assertLessEqual(clock.value, 2.0)
        self.assertTrue(process.stdout.closed and process.stderr.closed)

    def test_native_child_binds_endpoint_and_ready_before_single_nested_payload(self):
        calls = []
        class Clock:
            def now(self): return 0
            def sleep(self, seconds): pass
        class ChildFS:
            def stat(self, name, **kwargs):
                return SimpleNamespace(st_uid=1000, st_mode=(stat.S_IFREG if name == 'ready' else stat.S_IFSOCK) | 0o600,
                                       st_size=16, st_dev=1, st_ino=23)
        def spawn(argv, **kwargs): calls.append((argv, kwargs)); return SimpleNamespace(pid=73)
        system = SimpleNamespace(uid=1000, checked=True, fs=ChildFS(), clock=Clock(), spawn=spawn,
            read=lambda *args, **kwargs: b'0123456789abcdef',
            payload_environment=lambda tree, display: {'WAYLAND_DISPLAY': display})
        plan = launcher.make_plan({'execute': True}, binaries()).value
        child = launcher._Child(system, plan, '/run/user/1000/hybrid-outer-0123456789abcdef',
                                11, 12, 'hybrid-outer-wl-0123456789abcdef')
        self.assertTrue(launcher.endpoint_valid(child.endpoint()))
        with self.assertRaises(launcher.Blocked): child.start(launcher.gamescope_argv(plan))
        self.assertTrue(child.wait_ready(5))
        with self.assertRaises(launcher.Blocked): child.start(('/bin/sh',))
        self.assertEqual(calls, [])
        try:
            self.assertEqual(child.start(launcher.gamescope_argv(plan)), 1)
        except launcher.Blocked:
            self.fail('Nested payload start adapter is missing')
        self.assertEqual(calls[0][0], launcher.gamescope_argv(plan))
        self.assertFalse(calls[0][1]['start_new_session'])
        self.assertTrue(calls[0][1]['close_fds'])
        with self.assertRaises(launcher.Blocked): child.start(launcher.gamescope_argv(plan))

    def test_payload_uses_own_installed_steam_profile_and_blocks_live_singleton(self):
        class ProfileFS:
            def __init__(self):
                self.path = SimpleNamespace(realpath=lambda p, **kwargs: p)
                self.fds, self.counter, self.alive = {}, 20, False
                self.link, self.executable, self.fifo = True, True, False
            def open(self, path, flags, *args, **kwargs):
                self.counter += 1
                self.fds[self.counter] = bool(flags & launcher.os.O_DIRECTORY)
                return self.counter
            def close(self, fd): self.fds.pop(fd, None)
            def fstat(self, fd):
                mode = stat.S_IFDIR if self.fds[fd] else stat.S_IFREG
                return SimpleNamespace(st_uid=1000, st_mode=mode | 0o700, st_size=7)
            def stat(self, path, **kwargs):
                if path.startswith('/etc/'): raise FileNotFoundError()
                if path == 'steam':
                    return SimpleNamespace(st_uid=1000, st_mode=(stat.S_IFLNK if self.link else stat.S_IFDIR) | 0o700)
                if path == 'steam.pipe':
                    if not self.fifo: raise FileNotFoundError()
                    return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFIFO | 0o600)
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFREG | (0o700 if self.executable else 0o645))
            def access(self, *args, **kwargs): return self.executable
            def read(self, fd, size): return b'999999\n'
            def pidfd_open(self, pid, flags):
                if not self.alive: raise ProcessLookupError()
                self.fds[51] = False
                return 51
        fs = ProfileFS()
        record = launcher.pwd.struct_passwd(('fixture', 'x', 1000, 1000, '', '/var/home/fixture', '/bin/bash'))
        system = launcher._System(1000, {}, fs, user_lookup=lambda uid: record,
                                  poller=lambda *args: ([], [], []))
        system.checked, system.session = True, 'c3'
        tree = SimpleNamespace(root='/run/user/1000/hybrid-outer-0123456789abcdef')
        try:
            env = system.payload_environment(tree, 'hybrid-outer-wl-0123456789abcdef')
        except launcher.Blocked:
            self.fail('Controlled existing Steam profile environment is missing')
        self.assertEqual(env['HOME'], '/var/home/fixture')
        self.assertEqual(env['XDG_CONFIG_HOME'], tree.root + '/config')
        self.assertNotIn('DISPLAY', env)
        self.assertNotIn('GAMESCOPE_SCRIPT_PATH', env)
        self.assertEqual(fs.fds, {})
        for field in ('link', 'executable', 'fifo'):
            with self.subTest(field=field):
                setattr(fs, field, field == 'fifo')
                with self.assertRaises(launcher.Blocked, msg=field):
                    system.payload_environment(tree, 'hybrid-outer-wl-0123456789abcdef')
                self.assertEqual(fs.fds, {})
                setattr(fs, field, field != 'fifo')
        fs.alive = True
        with self.assertRaises(launcher.Blocked): system.payload_environment(tree, 'hybrid-outer-wl-0123456789abcdef')
        self.assertEqual(fs.fds, {})

    def test_forged_native_plan_rejects_before_system_factory(self):
        from hybrid_display.outer_session import Plan
        calls = []
        def factory(): calls.append('factory'); raise launcher.Blocked()
        result = launcher.Native(factory=factory).execute(Plan(execute=True, inner_width=True))
        self.assertEqual(result.reason, 'config_invalid')
        self.assertEqual(calls, [])

    def test_native_run_restores_signal_handlers_after_owned_lifecycle(self):
        changes, events = [], []
        class Signals:
            def getsignal(self, number): return 0
            def signal(self, number, handler): changes.append((number, handler))
        class Clock:
            def now(self): return 0
            def sleep(self, seconds): pass
        class IO:
            def prepare(self): events.append('prepare')
            def start_kwin(self): return 1
            def poll_kwin(self, token): return 0
            def cleanup(self): events.append('cleanup'); return True
        system = launcher._System(1000, {}, FS(), clock=Clock(), signal_api=Signals())
        system.checked = True
        result = system.run(launcher.make_plan({'execute': True}, binaries()).value, IO())
        self.assertTrue(result.ok)
        self.assertEqual(events, ['prepare', 'cleanup'])
        self.assertEqual(len(changes), 6)
        self.assertEqual([handler for number, handler in changes[3:]], [0, 0, 0])

    def test_foreign_argument_container_is_rejected_without_iteration(self):
        calls, output, io = [], [], Native()
        class Trap(list):
            def __iter__(self): calls.append('iterate'); raise RuntimeError('private')
        self.assertEqual(launcher.main(Trap(), io, output.append), 1)
        self.assertEqual(calls, [])
        self.assertEqual(io.events, [])

    def test_native_log_bridge_handles_partial_activation_and_failure_without_raw_results(self):
        chunks = [b'js: HYBRID_OUTER_RE', b'ADY_V1:0123456789abcdef\n']
        class Clock:
            def now(self): return 0
        class LogFS(FS):
            def read(self, fd, size): return chunks.pop(0)
        def poller(*args): return ([1], [], []) if chunks else ([], [], [])
        system = launcher._System(1000, {}, LogFS(), clock=Clock(), poller=poller)
        system.started = 0
        system.tree = SimpleNamespace(nonce='0123456789abcdef')
        group = SimpleNamespace(process=SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 41)))
        self.assertEqual(system.messages(group), 'active')
        self.assertEqual(system.partial, b'')
        chunks.append(b'js: HYBRID_OUTER_FAIL_V1:0123456789abcdef\n')
        self.assertEqual(system.messages(group), 'failed')

    def test_native_log_bridge_bounds_output_and_startup_time(self):
        class Clock:
            value = 0
            def now(self): return self.value
        class LogFS(FS):
            def read(self, fd, size): return b'x' * 4097
        clock = Clock()
        system = launcher._System(1000, {}, LogFS(), clock=clock, poller=lambda *args: ([1], [], []))
        system.started, system.tree = 0, SimpleNamespace(nonce='0123456789abcdef')
        group = SimpleNamespace(process=SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 41)))
        with self.assertRaises(launcher.Blocked): system.messages(group)
        system.partial = b''
        clock.value = 31
        with self.assertRaises(launcher.Blocked): system.messages(group)

    def test_native_receipt_is_atomic_exclusive_and_contains_only_nonce(self):
        class ReceiptFS(TreeFS):
            def link(self, src, dst, **kwargs): self.events.append(('link', src, dst, kwargs))
            def unlink(self, name, **kwargs): self.events.append(('unlink', name))
        fs = ReceiptFS()
        system = launcher._System(1000, {}, fs)
        tree = SimpleNamespace(fd=13, nonce='0123456789abcdef')
        try:
            system.receipt(tree)
        except launcher.Blocked:
            self.fail('Atomic script-active receipt is missing')
        self.assertIn(('write', b'0123456789abcdef'), fs.events)
        link = next(x for x in fs.events if x[0] == 'link')
        self.assertEqual(link[1:3], ('ready.pending', 'ready'))
        self.assertEqual(link[3]['dst_dir_fd'], 13)
        self.assertFalse(link[3]['follow_symlinks'])
        self.assertIn(('unlink', 'ready.pending'), fs.events)

    def test_native_kwin_spawn_is_closed_private_and_creates_only_own_group(self):
        calls = []
        process = SimpleNamespace(pid=73)
        def spawn(argv, **kwargs): calls.append((argv, kwargs)); return process
        system = launcher._System(1000, {}, FS(), nonce='0123456789abcdef', spawn=spawn)
        tree = system.private(None)
        plan = launcher.make_plan({'execute': True}, binaries()).value
        with self.assertRaises(launcher.Blocked): system.kwin(plan, tree)
        self.assertEqual(calls, [])
        system.checked, system.session = True, 'c3'
        try:
            group = system.kwin(plan, tree)
        except launcher.Blocked:
            self.fail('Closed KWin spawn adapter is missing')
        self.assertIs(group.process, process)
        argv, kwargs = calls[0]
        self.assertEqual(argv, launcher.kwin_argv(tree.root, 'hybrid-outer-wl-' + tree.nonce))
        self.assertTrue(kwargs['start_new_session'])
        self.assertTrue(kwargs['close_fds'])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['env']['XDG_SESSION_ID'], 'c3')
        self.assertEqual(kwargs['env']['HOME'], tree.root)
        self.assertNotIn('WAYLAND_DISPLAY', kwargs['env'])
        self.assertNotIn('DISPLAY', kwargs['env'])

    def test_native_private_resources_are_allocated_before_bounded_population(self):
        class ResourceFS(FS):
            def listdir(self, path): return []
            def stat(self, path, **kwargs): raise FileNotFoundError()
        def read(path, limit, owner):
            return b'fixture-js' if path.endswith('main.js') else b'{}'
        fs = ResourceFS()
        system = launcher._System(1000, {}, fs, read, '0123456789abcdef')
        plan = launcher.make_plan({'execute': True}, binaries()).value
        tree = system.private(plan)
        self.assertIsNotNone(tree)
        self.assertEqual(tree.root, '/run/user/1000/hybrid-outer-0123456789abcdef')
        images = []
        tree.create = images.append
        try:
            system.populate(tree, plan)
        except launcher.Blocked:
            self.fail('Private script population is missing')
        self.assertEqual(len(images), 1)
        self.assertIn(b'GamingOutput=DP-2', images[0]['config/kwinrc'])
        self.assertFalse(system.checked)

    def test_bounded_native_read_rejects_links_wrong_owner_and_oversize(self):
        class ReadFS(FS):
            data, owner, mode = b'abc', 1000, stat.S_IFREG | 0o600
            def fstat(self, fd):
                return SimpleNamespace(st_uid=self.owner, st_mode=self.mode, st_size=len(self.data))
            def read(self, fd, size): return self.data[:size]
        fs = ReadFS()
        system = launcher._System(1000, {}, fs)
        try:
            self.assertEqual(system._read('plan.json', 3, 1000, dir_fd=11), b'abc')
        except (launcher.Blocked, TypeError):
            self.fail('Bounded anchored read is missing')
        self.assertEqual(fs.closed, [11])
        for owner, mode, data in ((1001, stat.S_IFREG | 0o600, b'abc'),
                                  (1000, stat.S_IFLNK | 0o777, b'abc'),
                                  (1000, stat.S_IFREG | 0o600, b'abcd')):
            fs.owner, fs.mode, fs.data = owner, mode, data
            with self.assertRaises(launcher.Blocked): system._read('plan.json', 3, 1000, dir_fd=11)

    def test_system_boundary_requires_valid_session_and_actual_own_service_receipt(self):
        own = b'0::/user.slice/user-1000.slice/user@1000.service/app.slice/bazzite-hybrid-display-outer-kwin.service\n'
        class BoundaryFS(FS):
            def stat(self, path, **kwargs):
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFSOCK | 0o600)
        calls = []
        def read(path, limit, owner):
            calls.append((path, limit, owner)); return own
        env = {'XDG_RUNTIME_DIR': '/run/user/1000', 'XDG_SESSION_ID': 'c3', 'XDG_SESSION_TYPE': 'wayland'}
        system = launcher._System(1000, env, BoundaryFS(), read)
        try:
            system.ensure()
        except launcher.Blocked:
            self.fail('Valid fixed service receipt was rejected')
        self.assertEqual(calls, [('/proc/self/cgroup', 4096, 1000)])
        self.assertTrue(system.checked)
        system.env = env | {'LD_PRELOAD': 'private'}
        with self.assertRaises(launcher.Blocked): system.ensure()
        self.assertFalse(system.checked)
        class PublicRuntimeFS(BoundaryFS):
            def fstat(self, fd):
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o755)
        with self.assertRaises(launcher.Blocked):
            launcher._System(1000, env, PublicRuntimeFS(), read).ensure()
        for mode in (0o500, 0o300, 0o600):
            with self.subTest(mode=mode):
                class RestrictedRuntimeFS(BoundaryFS):
                    def fstat(self, fd):
                        return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | mode)
                with self.assertRaises(launcher.Blocked):
                    launcher._System(1000, env, RestrictedRuntimeFS(), read).ensure()
        for values, receipt in ((env | {'LD_PRELOAD': 'private'}, own), (env, b'0::/foreign\n')):
            system = launcher._System(1000, values, BoundaryFS(), lambda *args: receipt)
            with self.assertRaises(launcher.Blocked): system.ensure()

    def test_native_binary_receipts_are_root_owned_regular_executables(self):
        class BinaryFS:
            owner, mode = 0, stat.S_IFREG | 0o755
            def stat(self, path):
                self.assert_path = path
                return SimpleNamespace(st_uid=self.owner, st_mode=self.mode)
        fs = BinaryFS()
        receipts = launcher.Native(fs=fs).binaries()
        self.assertTrue(launcher.make_plan({}, receipts).ok)
        fs.owner = 1000
        self.assertFalse(launcher.make_plan({}, launcher.Native(fs=fs).binaries()).ok)
        fs.owner, fs.mode = 0, stat.S_IFREG | 0o777
        self.assertFalse(launcher.make_plan({}, launcher.Native(fs=fs).binaries()).ok)

    def test_native_execution_checks_service_boundary_before_creating_resources(self):
        events = []
        class System:
            def ensure(self): events.append('service'); raise launcher.Blocked()
            def private(self, plan): events.append('private')
        plan = launcher.make_plan({'execute': True}, binaries()).value
        result = launcher.Native(factory=System).execute(plan)
        self.assertFalse(result.ok)
        self.assertEqual(events, ['service'])

    def test_first_stage_timeout_never_kills_or_claims_cgroup_cleanup(self):
        events = []
        class Clock:
            value = 0
            def now(self): return self.value
            def sleep(self, value): self.value += value
        class Kernel:
            def getpgid(self, pid): return pid
            def killpg(self, pid, sig): events.append(sig)
        class Process:
            pid = 73
            def wait(self, timeout): raise launcher.subprocess.TimeoutExpired('owned', timeout)
        group = launcher.OwnedGroup(Process(), Kernel(), Clock())
        self.assertFalse(group.close())
        self.assertIn(launcher.signal.SIGTERM, events)
        self.assertNotIn(launcher.signal.SIGKILL, events)

    def test_parent_requires_actual_script_ready_marker_and_cleans_group_first(self):
        events = []
        class System:
            def private(self, plan): events.append('private'); return 'tree'
            def populate(self, tree, plan): events.append('populate')
            def kwin(self, plan, tree): events.append('kwin'); return 'group'
            def messages(self, group): return 'active'
            def receipt(self, tree): events.append('receipt')
            def status(self, group): return None
            def terminate(self, group): events.append('terminate'); return True
            def cleanup(self, tree): events.append('cleanup'); return True
        plan = launcher.make_plan({'execute': True}, binaries()).value
        parent = launcher.Parent(plan, System())
        try:
            parent.prepare()
            self.assertEqual(parent.start_kwin(), 1)
            self.assertIsNone(parent.poll_kwin(1))
            self.assertIsNone(parent.poll_kwin(1))
        except launcher.Blocked:
            self.fail('Private parent lifecycle is missing')
        self.assertEqual(events.count('receipt'), 1)
        self.assertEqual(events[:3], ['private', 'populate', 'kwin'])
        self.assertTrue(parent.cleanup())
        self.assertEqual(events[-2:], ['terminate', 'cleanup'])
        parent.system.messages = lambda group: 'failed'
        with self.assertRaises(launcher.Blocked): parent.poll_kwin(1)

    def test_partial_preparation_keeps_cleanup_ownership(self):
        events = []
        class System:
            def private(self, plan): return 'owned-tree'
            def populate(self, tree, plan): raise launcher.Blocked()
            def cleanup(self, tree): events.append(tree); return True
        parent = launcher.Parent(launcher.make_plan({'execute': True}, binaries()).value, System())
        with self.assertRaises(launcher.Blocked): parent.prepare()
        self.assertTrue(parent.cleanup())
        self.assertEqual(events, ['owned-tree'])

    def test_cleanup_directory_iteration_is_lazy_bounded_and_closed(self):
        class Entries:
            consumed = 0
            closed = False
            def __enter__(self): return self
            def __exit__(self, *args): self.closed = True
            def __iter__(self): return self
            def __next__(self):
                self.consumed += 1
                if self.consumed > 257: raise AssertionError('Unbounded traversal')
                return SimpleNamespace(name='cache' + str(self.consumed))
        entries = Entries()
        class LazyFS(FS):
            def listdir(self, fd): raise AssertionError('Eager directory allocation')
            def scandir(self, fd): return entries
            def stat(self, name, **kwargs):
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFREG | 0o600, st_dev=1, st_ino=9)
            def unlink(self, *args, **kwargs): pass
        tree = launcher.PrivateTree(1000, '0123456789abcdef', LazyFS())
        try:
            tree._purge(11, 0, [0])
        except launcher.Blocked:
            pass
        self.assertTrue(entries.closed)
        self.assertEqual(entries.consumed, 257)

    def test_cleanup_never_deletes_replaced_root_or_follows_symlinks(self):
        class CleanupFS(TreeFS):
            changed = False
            def scandir(self, fd):
                class Scan:
                    def __enter__(scan): return iter(SimpleNamespace(name=n) for n in self.listdir(fd))
                    def __exit__(scan, *args): pass
                return Scan()
            def stat(self, name, **kwargs):
                return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFDIR | 0o700,
                                       st_dev=1, st_ino=999 if self.changed else 23)
            def listdir(self, fd): return []
            def rmdir(self, name, **kwargs): self.events.append(('remove', name))
        fs = CleanupFS()
        tree = launcher.PrivateTree(1000, '0123456789abcdef', fs)
        tree.fd, tree.parent, tree.identity = 23, 11, (1, 23)
        self.assertTrue(tree.cleanup())
        self.assertEqual(fs.events, [('remove', 'hybrid-outer-0123456789abcdef')])
        fs = CleanupFS(); fs.changed = True
        tree = launcher.PrivateTree(1000, '0123456789abcdef', fs)
        tree.fd, tree.parent, tree.identity = 23, 11, (1, 23)
        self.assertFalse(tree.cleanup())
        self.assertEqual(fs.events, [])
        class LinkFS(CleanupFS):
            def listdir(self, fd): return ['foreign']
            def stat(self, name, **kwargs):
                if name == 'foreign':
                    return SimpleNamespace(st_uid=1000, st_mode=stat.S_IFLNK | 0o777, st_dev=1, st_ino=30)
                return super().stat(name, **kwargs)
        fs = LinkFS()
        tree = launcher.PrivateTree(1000, '0123456789abcdef', fs)
        tree.fd, tree.parent, tree.identity = 23, 11, (1, 23)
        self.assertFalse(tree.cleanup())
        self.assertEqual(fs.events, [])

    def test_private_tree_creation_is_exclusive_anchored_and_bounded(self):
        fs = TreeFS()
        tree = launcher.PrivateTree(1000, '0123456789abcdef', fs)
        try:
            tree.create({'config/kwinrc': b'private'})
        except launcher.Blocked:
            self.fail('Private runtime tree was not created')
        self.assertIn(('mkdir', 'hybrid-outer-0123456789abcdef', 0o700), fs.events)
        self.assertIn(('write', b'private'), fs.events)
        for event in fs.events:
            if event[0] == 'open' and event[1] == 'kwinrc':
                self.assertTrue(event[2] & launcher.os.O_NOFOLLOW)
                self.assertTrue(event[2] & launcher.os.O_EXCL)
        for image in ({'../foreign': b'x'}, {'/etc/foreign': b'x'}, {'config/x': b'x' * 262145}):
            with self.assertRaises(launcher.Blocked):
                launcher.PrivateTree(1000, '0123456789abcdef', TreeFS()).create(image)

    def test_readiness_is_script_activation_not_placement_success(self):
        nonce = '0123456789abcdef'
        self.assertEqual(launcher.readiness(b'js: HYBRID_OUTER_READY_V1:' + nonce.encode(), nonce), 'active')
        self.assertEqual(launcher.readiness(b'js: HYBRID_OUTER_FAIL_V1:' + nonce.encode(), nonce), 'failed')
        self.assertIsNone(launcher.readiness(b'Gamescope still running', nonce))
        self.assertIsNone(launcher.readiness(b'HYBRID_OUTER_READY_V1:wrong', nonce))
        self.assertIsNone(launcher.readiness(b'HYBRID_OUTER_READY_V1:' + nonce.encode() + b'extra', nonce))

    def test_group_cleanup_never_reaps_before_signalling_owned_group(self):
        events = []
        class Kernel:
            P_PID, WEXITED, WNOHANG, WNOWAIT, CLD_EXITED = 1, 2, 4, 8, 1
            def getpgid(self, pid): return pid
            def waitid(self, kind, pid, flags):
                events.append(('observe', pid, flags))
                return SimpleNamespace(si_code=1, si_status=0)
            def killpg(self, pid, sig):
                events.append(('signal', pid, sig))
                if sig == 0: raise ProcessLookupError()
        class Process:
            pid = 73
            def wait(self, timeout): events.append('reap'); return 0
        group = launcher.OwnedGroup(Process(), Kernel())
        self.assertEqual(group.status(), 0)
        self.assertTrue(group.close())
        self.assertEqual(events[-1], 'reap')
        self.assertIn(('signal', 73, launcher.signal.SIGTERM), events)
        self.assertEqual(sum(x == 'reap' for x in events), 1)
        self.assertTrue(group.close())
        self.assertEqual(sum(x == 'reap' for x in events), 1)

    def test_changed_or_foreign_group_is_never_signalled(self):
        calls = []
        class Kernel:
            def getpgid(self, pid): return 99
            def killpg(self, *args): calls.append(args)
        group = launcher.OwnedGroup(SimpleNamespace(pid=73), Kernel())
        self.assertFalse(group.close())
        self.assertEqual(calls, [])

    def test_private_image_contains_only_isolated_script_and_config(self):
        plan = launcher.make_plan({'execute': True}, binaries()).value
        root = ROOT / 'prototype/hybrid-display/session/kwin/outer-placement'
        resources = ((root / 'contents/code/main.js').read_bytes(),
                     (root / 'metadata.json').read_bytes())
        image = launcher.private_image(plan, '0123456789abcdef', resources)
        self.assertIn('config/kwinrc', image)
        self.assertIn(b'GamingOutput=DP-2', image['config/kwinrc'])
        self.assertIn(b'SideOutput=DP-1', image['config/kwinrc'])
        self.assertIn(b'hybrid-display-outer-placementEnabled=true', image['config/kwinrc'])
        self.assertEqual(image['data/kwin/scripts/hybrid-display-outer-placement/contents/code/main.js'], resources[0])
        self.assertNotIn('plasmashell', str(image.keys()))
        for name in image:
            self.assertFalse(name.startswith('/'))
            self.assertNotIn('..', name.split('/'))
        with self.assertRaises(launcher.Blocked):
            launcher.private_image(plan, '../invalid', resources)

    def test_private_image_disables_other_system_scripts(self):
        plan = launcher.make_plan({'execute': True}, binaries()).value
        try:
            image = launcher.private_image(plan, '0123456789abcdef', (b'js', b'{}'),
                                           ('desktopchangeosd', 'videowall'))
        except TypeError:
            self.fail('Private script allowlist is not implemented')
        self.assertIn(b'desktopchangeosdEnabled=false', image['config/kwinrc'])
        self.assertIn(b'videowallEnabled=false', image['config/kwinrc'])
        with self.assertRaises(launcher.Blocked):
            launcher.private_image(plan, '0123456789abcdef', (b'js', b'{}'), ('x\nInjected',))

    def test_native_bridge_uses_only_owned_parent_lifecycle(self):
        events = []
        class Host:
            def prepare(self): events.append('prepare')
            def start_kwin(self): events.append('kwin'); return 1
            def poll_kwin(self, token): events.append(('poll', token)); return 0
            def cleanup(self): events.append('cleanup'); return True
        plan = launcher.make_plan({'execute': True}, binaries()).value
        result = launcher.Native(Host()).execute(plan)
        self.assertTrue(result.ok)
        self.assertEqual(events, ['prepare', 'kwin', ('poll', 1), 'cleanup'])

    def test_default_dry_run_never_calls_execution_adapter(self):
        io, output = Native(), []
        self.assertEqual(launcher.main([], io, output.append), 0)
        self.assertEqual(io.events, ['binaries'])
        self.assertNotIn('execute', io.events)

    def test_execute_only_calls_explicit_adapter_once(self):
        io, output = Native(), []
        self.assertEqual(launcher.main(['--execute'], io, output.append), 0)
        self.assertEqual(io.events, ['binaries', 'execute'])

    def test_unknown_option_and_shell_payload_block_without_process(self):
        for argv in (['--command', '/bin/sh'], ['--gaming-output-name', 'DP-2;evil'],
                     ['--display-index', '1'], ['--inner-width', '-1']):
            io, output = Native(), []
            self.assertNotEqual(launcher.main(argv, io, output.append), 0)
            self.assertNotIn('execute', io.events)

    def test_errors_never_print_private_exception_or_path(self):
        io, output = Native(), []
        def fail(plan):
            raise RuntimeError('synthetic-private')
        io.execute = fail
        self.assertEqual(launcher.main(['--execute'], io, output.append), 1)
        self.assertNotIn('synthetic-private', str(output))
        io.execute = lambda plan: launcher.Result(reason='synthetic-private')
        output.clear()
        self.assertEqual(launcher.main(['--execute'], io, output.append), 1)
        self.assertNotIn('synthetic-private', str(output))

    def test_secure_directory_requires_absolute_owned_non_symlink(self):
        try:
            value = launcher.directory('/run/user/1000', 1000, FS())
        except launcher.Blocked:
            self.fail('Valid owned runtime directory rejected')
        self.assertEqual(value, 11)
        for path, fs in (('relative', FS()), ('/run/user/1000/..', FS()),
                         ('/run/user/1000', FS(1001)), ('/run/user/1000', FS(symlink=True))):
            with self.assertRaises(launcher.Blocked):
                launcher.directory(path, 1000, fs)

    def test_kwin_argument_vector_and_child_command_are_closed(self):
        try:
            argv = launcher.kwin_argv('/run/user/1000/hybrid-outer-0123456789abcdef',
                                      'hybrid-outer-wl-0123456789abcdef')
        except launcher.Blocked:
            self.fail('Valid private KWin invocation rejected')
        self.assertEqual(argv[:4], ('/usr/bin/kwin_wayland', '--drm', '--xwayland', '--no-kactivities'))
        self.assertIn('--exit-with-session', argv)
        self.assertIn('--socket', argv)
        self.assertIn('--execute --session-child', argv[-1])
        self.assertNotIn('--replace', argv)
        self.assertNotIn('plasmashell', ' '.join(argv))
        with self.assertRaises(launcher.Blocked):
            launcher.kwin_argv('/tmp/a;evil', 'bad')

    def test_private_environment_cannot_inherit_parent_loader_or_plugins(self):
        env = launcher.kwin_environment('/run/user/1000/hybrid-outer-0123456789abcdef', 1000)
        self.assertEqual(env.get('XDG_CONFIG_HOME'), '/run/user/1000/hybrid-outer-0123456789abcdef/config')
        self.assertEqual(env.get('XDG_DATA_HOME'), '/run/user/1000/hybrid-outer-0123456789abcdef/data')
        self.assertNotIn('LD_PRELOAD', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertEqual(env['XDG_DATA_DIRS'], '/usr/share')

    def test_only_experimental_desktop_template_no_installation(self):
        path = ROOT / 'prototype/hybrid-display/session/hybrid-display-outer-kwin.desktop.in'
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn('Experimental', text)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(text)
        from hybrid_display.outer_session import transient_argv
        self.assertEqual(tuple(shlex.split(parser['Desktop Entry']['Exec'])), transient_argv())
        self.assertEqual(parser['Desktop Entry']['TryExec'], '/usr/libexec/bazzite-hybrid-display-outer-kwin')
        self.assertNotIn('gamescope-session-plus', text)
        self.assertNotIn('Autostart', text)
