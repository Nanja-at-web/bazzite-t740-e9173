#!/usr/bin/python3 -IB
"""Experimental non-installed outer session; no action without --execute.

No live start has been validated. Initial placement can briefly be on another
output. Same-UID authority, controller isolation and hardware gates remain open.
"""
import sys
from pathlib import Path
import argparse
import json
import os
import pwd
import re
import secrets
import select
import signal
import stat
import subprocess
import time

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from hybrid_display.outer_session import Result, Binary, PROGRAMS, make_plan, session_environment, service_membership, valid_plan
from hybrid_display.outer_supervisor import Endpoint, Reply, supervise, launch_outer, endpoint_valid, gamescope_argv


class Blocked(Exception):
    pass


def directory(path, uid, fs=None):
    """Walk every component with O_NOFOLLOW; return an owned directory FD."""
    fs = os if fs is None else fs
    if (type(path) is not str or type(uid) is not int or uid <= 0
            or len(path) > 256 or not path.startswith('/')
            or any(p in ('', '.', '..') for p in path.split('/')[1:])):
        raise Blocked()
    fd = None
    try:
        fd = fs.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in path.split('/')[1:]:
            nxt = fs.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            fs.close(fd)
            fd = nxt
            metadata = fs.fstat(fd)
            if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in (0, uid)
                    or metadata.st_mode & 0o022):
                raise Blocked()
        if fs.fstat(fd).st_uid != uid:
            raise Blocked()
        return fd
    except (OSError, Blocked):
        if fd is not None:
            fs.close(fd)
        raise Blocked() from None


def _root_valid(root, uid=None):
    match = re.fullmatch(r'/run/user/([1-9][0-9]{0,9})/hybrid-outer-([a-f0-9]{16})', root) if type(root) is str else None
    if match is None or uid is not None and int(match[1]) != uid:
        raise Blocked()
    return match


def kwin_argv(root, display):
    match = _root_valid(root)
    script = str(Path(__file__).absolute())
    if (display != 'hybrid-outer-wl-' + match[2]
            or re.fullmatch(r'/[A-Za-z0-9_./-]+', script) is None
            or any(p in ('.', '..') for p in script.split('/'))):
        raise Blocked()
    # This one fixed command is KWin's documented QProcess API argument.
    # KWin KShell::splitArgs tokenizes it; no shell is invoked.
    client = ' '.join(('/usr/bin/python3', '-I', '-B', script, '--execute', '--session-child', root))
    return ('/usr/bin/kwin_wayland', '--drm', '--xwayland', '--no-kactivities',
            '--no-global-shortcuts', '--socket', display, '--exit-with-session', client)


def kwin_environment(root, uid):
    _root_valid(root, uid)
    return {'PATH': '/usr/bin', 'HOME': root, 'XDG_RUNTIME_DIR': '/run/user/' + str(uid),
            'XDG_CONFIG_HOME': root + '/config', 'XDG_CONFIG_DIRS': root + '/config',
            'XDG_DATA_HOME': root + '/data', 'XDG_DATA_DIRS': '/usr/share',
            'XDG_CACHE_HOME': root + '/cache', 'XDG_STATE_HOME': root + '/state',
            'XDG_CURRENT_DESKTOP': 'HYBRID_OUTER_KWIN', 'XDG_SESSION_TYPE': 'wayland',
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/' + str(uid) + '/bus',
            'LC_ALL': 'C', 'QT_MESSAGE_PATTERN': '%{message}'}


def _config(plan):
    return {k: getattr(plan, k) for k in ('gaming_output_name', 'side_output_name',
            'inner_width', 'inner_height', 'outer_width', 'outer_height', 'execute')}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Blocked()


class Native:
    def __init__(self, host=None, fs=None, factory=None):
        self.host = host
        self.fs = os if fs is None else fs
        self.factory = factory

    def binaries(self):
        receipts = []
        try:
            for path in PROGRAMS:
                info = self.fs.stat(path)
                receipts.append(Binary(path, stat.S_ISREG(info.st_mode) and bool(info.st_mode & 0o111),
                                       info.st_uid == 0, bool(info.st_mode & 0o022)))
        except OSError:
            return ()
        return tuple(receipts)

    def execute(self, plan):
        if not valid_plan(plan) or plan.execute is not True:
            return Result(reason='config_invalid')
        if self.host is None:
            try:
                system = (self.factory or _System)()
                system.ensure()
                return system.run(plan)
            except (Exception, SystemExit):
                return Result(reason='session_failed')
        return launch_outer(plan, self.host, Clock())


class Clock:
    @staticmethod
    def now():
        return time.monotonic()

    @staticmethod
    def sleep(seconds):
        time.sleep(seconds)


def private_image(plan, nonce, resources, script_ids=()):
    if (type(nonce) is not str or re.fullmatch(r'[a-f0-9]{16}', nonce) is None
            or type(resources) is not tuple or len(resources) != 2
            or any(type(value) is not bytes or not 1 <= len(value) <= 32768 for value in resources)):
        raise Blocked()
    if (type(script_ids) is not tuple or len(script_ids) > 128
            or any(type(s) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,96}', s) is None
                   or s == 'hybrid-display-outer-placement' for s in script_ids)
            or len(set(script_ids)) != len(script_ids)):
        raise Blocked()
    checked = make_plan(_config(plan), tuple(Binary(p, True, True, False) for p in PROGRAMS))
    if not checked.ok or not checked.value.execute:
        raise Blocked()
    prefix = 'data/kwin/scripts/hybrid-display-outer-placement/'
    config = ('[Plugins]\n' + ''.join(s + 'Enabled=false\n' for s in script_ids)
              + 'hybrid-display-outer-placementEnabled=true\n'
              '[Script-hybrid-display-outer-placement]\nGamingOutput=' + plan.gaming_output_name
              + '\nSideOutput=' + plan.side_output_name + '\nReceipt=' + nonce + '\n')
    return {'config/kwinrc': config.encode('ascii'),
            'plan.json': json.dumps(_config(plan), sort_keys=True).encode('ascii'),
            prefix + 'contents/code/main.js': resources[0], prefix + 'metadata.json': resources[1]}


class OwnedGroup:
    """First-stage TERM only. Never an attestation of complete cgroup cleanup.

    Only accepts a freshly created, unreaped Popen session leader. The fixed
    transient service performs authoritative escalation after launcher exit.
    """
    def __init__(self, process, kernel=None, clock=None):
        self.process = process
        self.kernel = os if kernel is None else kernel
        self.clock = Clock() if clock is None else clock
        self.closed = False

    def status(self):
        if self.closed:
            raise Blocked()
        info = self.kernel.waitid(self.kernel.P_PID, self.process.pid,
                                  self.kernel.WEXITED | self.kernel.WNOHANG | self.kernel.WNOWAIT)
        if info is None:
            return None
        return info.si_status if info.si_code == self.kernel.CLD_EXITED else -1

    def close(self, grace=5.0):
        if self.closed:
            return True
        try:
            if (type(self.process.pid) is not int or self.process.pid <= 1
                    or self.kernel.getpgid(self.process.pid) != self.process.pid):
                return False
            # WNOWAIT reserves the leader PID until the final reap. Never use
            # Popen.poll()/wait() before these group operations (PID reuse).
            self.kernel.killpg(self.process.pid, signal.SIGTERM)
            deadline = self.clock.now() + min(5.0, max(0.0, grace))
            alive = True
            while self.clock.now() < deadline:
                try:
                    self.kernel.killpg(self.process.pid, 0)
                except ProcessLookupError:
                    alive = False
                    break
                self.clock.sleep(min(.05, max(0.0, deadline - self.clock.now())))
            self.process.wait(timeout=.25)
            self.closed = True
            return True
        except (OSError, subprocess.TimeoutExpired, ChildProcessError):
            return False


def readiness(chunk, nonce):
    if (type(chunk) is not bytes or len(chunk) > 4096 or type(nonce) is not str
            or re.fullmatch(r'[a-f0-9]{16}', nonce) is None):
        return None
    for tag, result in ((b'FAIL', 'failed'), (b'READY', 'active')):
        if re.search(rb'(?:^|\s)HYBRID_OUTER_' + tag + rb'_V1:' + nonce.encode()
                     + rb'(?:$|\s)', chunk):
            return result
    return None


class PrivateTree:
    def __init__(self, uid, nonce, fs=None):
        self.fs = os if fs is None else fs
        self.uid, self.nonce = uid, nonce
        self.root = '/run/user/' + str(uid) + '/hybrid-outer-' + nonce
        _root_valid(self.root, uid)
        self.parent = self.fd = None
        self.identity = None
        self.created = False

    def create(self, image):
        if (type(image) is not dict or not 1 <= len(image) <= 16
                or any(type(k) is not str or len(k) > 192
                       or re.fullmatch(r'[A-Za-z0-9_./-]+', k) is None
                       or any(p in ('', '.', '..') for p in k.split('/'))
                       or type(v) is not bytes or len(v) > 262144 for k, v in image.items())):
            raise Blocked()
        fs = self.fs
        self.parent = directory('/run/user/' + str(self.uid), self.uid, fs)
        name = 'hybrid-outer-' + self.nonce
        fs.mkdir(name, 0o700, dir_fd=self.parent)
        self.created = True
        metadata = fs.stat(name, dir_fd=self.parent, follow_symlinks=False)
        if metadata.st_uid != self.uid or not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o077:
            raise Blocked()
        self.identity = metadata.st_dev, metadata.st_ino
        self.fd = fs.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent)
        metadata = fs.fstat(self.fd)
        if metadata.st_uid != self.uid or not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o077:
            raise Blocked()
        if self.identity != (metadata.st_dev, metadata.st_ino):
            raise Blocked()
        dirs = {'': self.fd}
        try:
            for relative in ('config/x', 'data/x', 'cache/x', 'state/x', *image):
                parts = relative.split('/')[:-1]
                for i in range(len(parts)):
                    path = '/'.join(parts[:i + 1])
                    if path in dirs:
                        continue
                    parent = dirs['/'.join(parts[:i])]
                    fs.mkdir(parts[i], 0o700, dir_fd=parent)
                    dirs[path] = fs.open(parts[i], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                         dir_fd=parent)
            for relative, data in image.items():
                parts = relative.split('/')
                fd = fs.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=dirs['/'.join(parts[:-1])])
                try:
                    offset = 0
                    while offset < len(data):
                        amount = fs.write(fd, data[offset:])
                        if type(amount) is not int or not 0 < amount <= len(data) - offset:
                            raise Blocked()
                        offset += amount
                finally:
                    fs.close(fd)
        finally:
            for path, fd in dirs.items():
                if path:
                    fs.close(fd)

    def cleanup(self):
        fs = self.fs
        try:
            if self.fd is None:
                if self.identity is None:
                    return not self.created
                metadata = fs.stat('hybrid-outer-' + self.nonce, dir_fd=self.parent, follow_symlinks=False)
                if ((metadata.st_dev, metadata.st_ino) != self.identity
                        or metadata.st_uid != self.uid or not stat.S_ISDIR(metadata.st_mode)):
                    return False
                fs.rmdir('hybrid-outer-' + self.nonce, dir_fd=self.parent)
                self.identity, self.created = None, False
                return True
            name = 'hybrid-outer-' + self.nonce
            metadata = fs.stat(name, dir_fd=self.parent, follow_symlinks=False)
            if ((metadata.st_dev, metadata.st_ino) != self.identity
                    or metadata.st_uid != self.uid or not stat.S_ISDIR(metadata.st_mode)):
                return False
            self._purge(self.fd, 0, [0])
            metadata = fs.stat(name, dir_fd=self.parent, follow_symlinks=False)
            if (metadata.st_dev, metadata.st_ino) != self.identity:
                return False
            fs.rmdir(name, dir_fd=self.parent)
            self.identity = None
            self.created = False
            return True
        except (OSError, Blocked):
            return False
        finally:
            for fd in (self.fd, self.parent):
                if fd is not None:
                    fs.close(fd)
            self.fd = self.parent = None

    def _purge(self, fd, depth, count):
        # Only descend from our still-anchored, freshly generated session root.
        # Reject links/foreign owners; never shutil.rmtree an arbitrary path.
        fs = self.fs
        if depth > 10:
            raise Blocked()
        with fs.scandir(fd) as entries:
            for entry in entries:
                name = entry.name
                count[0] += 1
                if count[0] > 256 or type(name) is not str or '/' in name or name in ('.', '..'):
                    raise Blocked()
                metadata = fs.stat(name, dir_fd=fd, follow_symlinks=False)
                if metadata.st_uid != self.uid:
                    raise Blocked()
                if stat.S_ISDIR(metadata.st_mode):
                    child = fs.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        opened = fs.fstat(child)
                        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                            raise Blocked()
                        self._purge(child, depth + 1, count)
                        latest = fs.stat(name, dir_fd=fd, follow_symlinks=False)
                        if (latest.st_dev, latest.st_ino) != (opened.st_dev, opened.st_ino):
                            raise Blocked()
                        fs.rmdir(name, dir_fd=fd)
                    finally:
                        fs.close(child)
                elif stat.S_ISREG(metadata.st_mode) or stat.S_ISSOCK(metadata.st_mode):
                    latest = fs.stat(name, dir_fd=fd, follow_symlinks=False)
                    if (latest.st_dev, latest.st_ino) != (metadata.st_dev, metadata.st_ino):
                        raise Blocked()
                    fs.unlink(name, dir_fd=fd)
                else:
                    raise Blocked()


class Parent:
    def __init__(self, plan, system):
        self.plan, self.system = plan, system
        self.tree = self.group = None
        self.active = False

    def prepare(self):
        self.tree = self.system.private(self.plan)
        self.system.populate(self.tree, self.plan)

    def start_kwin(self):
        self.group = self.system.kwin(self.plan, self.tree)
        return 1

    def poll_kwin(self, token):
        if type(token) is not int or token != 1 or self.group is None:
            raise Blocked()
        message = self.system.messages(self.group)
        if message == 'failed':
            raise Blocked()
        if message == 'active' and not self.active:
            self.system.receipt(self.tree)
            self.active = True
        return self.system.status(self.group)

    def cleanup(self):
        ended = self.group is None or self.system.terminate(self.group) is True
        # Preserve the private root if its processes might still be writing.
        return ended and (self.tree is None or self.system.cleanup(self.tree) is True)


class _System:
    def __init__(self, uid=None, env=None, fs=None, read=None, nonce=None, spawn=None, clock=None, poller=None, signal_api=None, user_lookup=None, display=None):
        self.uid = os.getuid() if uid is None else uid
        self.env = {k: os.environ.get(k) for k in ('XDG_RUNTIME_DIR', 'XDG_SESSION_ID', 'XDG_SESSION_TYPE')} if env is None else env
        self.fs = os if fs is None else fs
        self.read = self._read if read is None else read
        self.nonce = nonce
        self.spawn = subprocess.Popen if spawn is None else spawn
        self.clock = Clock() if clock is None else clock
        self.checked = False
        self.partial = b''
        self.log_bytes = 0
        self.poller = select.select if poller is None else poller
        self.started = None
        self.script_active = False
        self.signals = signal if signal_api is None else signal_api
        self.user_lookup = pwd.getpwuid if user_lookup is None else user_lookup
        self.display_value = display

    def child_display(self):
        if self.checked is not True:
            raise Blocked()
        value = os.environ.get('WAYLAND_DISPLAY') if self.display_value is None else self.display_value
        if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) is None:
            raise Blocked()
        return value

    def payload_environment(self, tree, display):
        if not self.checked:
            raise Blocked()
        entry = self.user_lookup(self.uid)
        if (type(entry) is not pwd.struct_passwd or type(entry.pw_uid) is not int or entry.pw_uid != self.uid
                or type(entry.pw_dir) is not str or type(entry.pw_name) is not str
                or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}', entry.pw_name) is None):
            raise Blocked()
        home = self.fs.path.realpath(entry.pw_dir, strict=True)
        fd = directory(home, self.uid, self.fs)
        self.fs.close(fd)
        steamdir = directory(home + '/.steam', self.uid, self.fs)
        try:
            link = self.fs.stat('steam', dir_fd=steamdir, follow_symlinks=False)
            if not stat.S_ISLNK(link.st_mode) or link.st_uid != self.uid:
                raise Blocked()
            # Steam can forward through this FIFO before consulting its PID
            # file. Any existing inode is ambiguous; never connect or delete it.
            try:
                self.fs.stat('steam.pipe', dir_fd=steamdir, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise Blocked()
        finally:
            self.fs.close(steamdir)
        steam = self.fs.path.realpath(home + '/.steam/steam', strict=True)
        if type(steam) is not str or not steam.startswith(home + '/'):
            raise Blocked()
        fd = directory(steam, self.uid, self.fs)
        try:
            client = self.fs.stat('steam.sh', dir_fd=fd, follow_symlinks=False)
            if (not stat.S_ISREG(client.st_mode) or client.st_uid != self.uid
                    or not client.st_mode & 0o100
                    or not self.fs.access('steam.sh', os.X_OK, dir_fd=fd,
                                          effective_ids=True, follow_symlinks=False)):
                raise Blocked()
        finally:
            self.fs.close(fd)
        # Same startup PID path as the installed Steam shell contract. A stale
        # file alone is not a running instance. Never signal that PID.
        try:
            pidpath = self.fs.path.realpath(home + '/.steam/steam.pid', strict=True)
        except FileNotFoundError:
            pidpath = None
        if pidpath is not None:
            if type(pidpath) is not str or not pidpath.startswith(home + '/') or not pidpath.endswith('/steam.pid'):
                raise Blocked()
            fd = directory(pidpath.rsplit('/', 1)[0], self.uid, self.fs)
            try:
                raw = self._read('steam.pid', 16, self.uid, dir_fd=fd).strip()
            finally:
                self.fs.close(fd)
            if re.fullmatch(rb'[1-9][0-9]{0,9}', raw) is None or not 1 < int(raw) <= 2147483647:
                raise Blocked()
            try:
                pidfd = self.fs.pidfd_open(int(raw), 0)
            except ProcessLookupError:
                pidfd = None
            if pidfd is not None:
                try:
                    if not self.poller([pidfd], [], [], 0)[0]:
                        raise Blocked()
                finally:
                    self.fs.close(pidfd)
        try:
            scripts = self.fs.stat('/etc/gamescope/scripts', follow_symlinks=False)
        except FileNotFoundError:
            scripts = None
        if scripts is not None:
            if (not stat.S_ISDIR(scripts.st_mode) or scripts.st_uid != 0 or scripts.st_mode & 0o022
                    or self.fs.listdir('/etc/gamescope/scripts')):
                raise Blocked()
        env = kwin_environment(tree.root, self.uid)
        expected = 'hybrid-outer-wl-' + _root_valid(tree.root, self.uid)[2]
        if type(display) is not str or display != expected:
            raise Blocked()
        env.update(HOME=home, USER=entry.pw_name, LOGNAME=entry.pw_name,
                   WAYLAND_DISPLAY=display, XDG_SESSION_ID=self.session)
        return env

    def run(self, plan, parent=None):
        if not self.checked:
            return Result(reason='session_failed')
        previous = {}
        def interrupted(number, frame):
            raise SystemExit(1)
        try:
            for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                previous[number] = self.signals.getsignal(number)
                self.signals.signal(number, interrupted)
            return launch_outer(plan, Parent(plan, self) if parent is None else parent, self.clock)
        finally:
            for number, handler in previous.items():
                self.signals.signal(number, handler)

    def messages(self, group):
        if self.started is None or not self.script_active and self.clock.now() - self.started >= 30:
            raise Blocked()
        result = None
        for _ in range(8):
            stream = group.process.stdout
            if not self.poller([stream], [], [], 0)[0]:
                break
            chunk = self.fs.read(stream.fileno(), 8192)
            if type(chunk) is not bytes or len(chunk) > 8192:
                raise Blocked()
            if not chunk:
                break
            self.log_bytes += len(chunk)
            if self.log_bytes > 262144:
                raise Blocked()
            lines = (self.partial + chunk).split(b'\n')
            self.partial = lines.pop()
            if len(self.partial) > 4096 or any(len(line) > 4096 for line in lines):
                raise Blocked()
            for line in lines:
                marker = readiness(line, self.tree.nonce)
                if marker == 'failed':
                    return marker
                if marker == 'active':
                    self.script_active = True
                    result = marker
        return result

    def receipt(self, tree):
        fd = self.fs.open('ready.pending', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=tree.fd)
        try:
            data = tree.nonce.encode('ascii')
            offset = 0
            while offset < len(data):
                size = self.fs.write(fd, data[offset:])
                if type(size) is not int or not 0 < size <= len(data) - offset:
                    raise Blocked()
                offset += size
        finally:
            self.fs.close(fd)
        self.fs.link('ready.pending', 'ready', src_dir_fd=tree.fd, dst_dir_fd=tree.fd,
                     follow_symlinks=False)
        self.fs.unlink('ready.pending', dir_fd=tree.fd)

    def status(self, group):
        return group.status()

    def terminate(self, group):
        try:
            result = group.close(grace=1.0)
        except (Exception, SystemExit):
            result = False
        try:
            if group.process.stdout is not None:
                group.process.stdout.close()
        except (Exception, SystemExit):
            result = False
        return result

    def cleanup(self, tree):
        return tree.cleanup()

    def kwin(self, plan, tree):
        if not self.checked:
            raise Blocked()
        display = 'hybrid-outer-wl-' + tree.nonce
        env = kwin_environment(tree.root, self.uid)
        env['XDG_SESSION_ID'] = self.session
        self.started = self.clock.now()
        process = self.spawn(kwin_argv(tree.root, display), env=env, cwd=tree.root,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             close_fds=True, start_new_session=True, bufsize=0)
        return OwnedGroup(process, self.fs, self.clock)

    def private(self, plan):
        return PrivateTree(self.uid, self.nonce or secrets.token_hex(8), self.fs)

    def populate(self, tree, plan):
        source = Path(__file__).resolve().parent / 'session/kwin/outer-placement'
        resources = (self.read(str(source / 'contents/code/main.js'), 32768, self.uid),
                     self.read(str(source / 'metadata.json'), 32768, self.uid))
        names = self.fs.listdir('/usr/share/kwin/scripts')
        if len(names) > 128:
            raise Blocked()
        ids = []
        for name in names:
            if type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,96}', name) is None or name in ('.', '..'):
                raise Blocked()
            metadata = json.loads(self.read('/usr/share/kwin/scripts/' + name + '/metadata.json', 32768, 0))
            ids.append(metadata['KPlugin']['Id'])
        image = private_image(plan, tree.nonce, resources, tuple(ids))
        fd = directory('/run/user/' + str(self.uid), self.uid, self.fs)
        try:
            for name in ('hybrid-outer-wl-' + tree.nonce, 'hybrid-outer-wl-' + tree.nonce + '.lock'):
                try:
                    self.fs.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise Blocked()
        finally:
            self.fs.close(fd)
        tree.create(image)
        self.tree = tree

    def _read(self, path, limit, owner, dir_fd=None):
        fd = None
        try:
            fd = self.fs.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
            info = self.fs.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, owner) or info.st_size > limit:
                raise Blocked()
            value = self.fs.read(fd, limit + 1)
            if type(value) is not bytes or len(value) > limit:
                raise Blocked()
            return value
        except OSError:
            raise Blocked() from None
        finally:
            if fd is not None:
                self.fs.close(fd)

    def ensure(self):
        self.checked = False
        checked = session_environment(self.env, self.uid)
        if not checked.ok or not service_membership(self.read('/proc/self/cgroup', 4096, self.uid), self.uid):
            raise Blocked()
        runtime, self.session = checked.value
        fd = directory(runtime, self.uid, self.fs)
        try:
            if stat.S_IMODE(self.fs.fstat(fd).st_mode) != 0o700:
                raise Blocked()
            bus = self.fs.stat('bus', dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISSOCK(bus.st_mode) or bus.st_uid != self.uid:
                raise Blocked()
        finally:
            self.fs.close(fd)
        self.checked = True


class _Child:
    def __init__(self, system, plan, root, rootfd, runtimefd, display):
        if (system.checked is not True or not valid_plan(plan) or plan.execute is not True
                or type(rootfd) is not int or type(runtimefd) is not int
                or rootfd < 0 or runtimefd < 0 or rootfd == runtimefd):
            raise Blocked()
        nonce = _root_valid(root, system.uid)[2]
        if type(display) is not str or display != 'hybrid-outer-wl-' + nonce:
            raise Blocked()
        self.system, self.plan, self.root = system, plan, root
        self.rootfd, self.runtimefd, self.display = rootfd, runtimefd, display
        self.ready = self.closed = False
        self.game = None
        self.queries = 0
        self.last_status = None

    def poll(self, token):
        if type(token) is not int or token != 1 or self.closed or self.game is None:
            raise Blocked()
        kernel = self.system.fs
        info = kernel.waitid(kernel.P_PID, self.game.pid, kernel.WEXITED | kernel.WNOHANG | kernel.WNOWAIT)
        if info is None:
            return None
        self.last_status = info.si_status if info.si_code == kernel.CLD_EXITED else -1
        return self.last_status

    def finish(self):
        if self.closed:
            return True
        self.closed = True
        if self.game is not None and self.last_status is not None:
            self.game.wait(timeout=0)
        # Parent first-stage cleanup and then systemd own all remaining payload
        # processes. This is not a complete process/cgroup-cleanup receipt.
        return True

    def query(self, endpoint, seconds, limit):
        if (self.closed or self.game is not None or self.queries >= 3 or type(limit) is not int
                or limit != 262144 or (type(seconds) is not float and type(seconds) is not int)
                or not 0 < seconds <= 2 or not endpoint_valid(endpoint) or endpoint != self.endpoint()):
            raise Blocked()
        self.queries += 1
        if seconds <= .35:
            return Reply(status=-1, timed_out=True)
        start = self.system.clock.now()
        deadline = start + seconds - .35  # reserve bounded TERM/reap time
        process = group = None
        answer = Reply(status=-1)
        clean = True
        try:
            env = {'XDG_RUNTIME_DIR': endpoint.runtime, 'WAYLAND_DISPLAY': endpoint.name, 'LC_ALL': 'C'}
            process = self.system.spawn(('/usr/bin/wayland-info',), env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        close_fds=True, start_new_session=True, bufsize=0)
            group = OwnedGroup(process, self.system.fs, self.system.clock)
            streams = [process.stdout, process.stderr]
            buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
            total = 0
            limited = False
            while streams and self.system.clock.now() < deadline:
                remaining = deadline - self.system.clock.now()
                readable = self.system.poller(streams, [], [], max(0, min(.05, remaining)))[0]
                for stream in readable:
                    size = min(8192, limit - total + 1)
                    data = self.system.fs.read(stream.fileno(), size)
                    if type(data) is not bytes or len(data) > size:
                        raise Blocked()
                    if not data:
                        streams.remove(stream)
                        continue
                    buffers[stream].extend(data)
                    total += len(data)
                    if total > limit:
                        limited = True
                        break
                if limited:
                    break
            status = group.status()
            answer = Reply(bytes(buffers[process.stdout]), bytes(buffers[process.stderr]),
                           -1 if status is None else status,
                           timed_out=bool(streams) and not limited or status is None, limited=limited)
        except (Exception, SystemExit):
            answer = Reply(status=-1)
        finally:
            if group is not None:
                try:
                    clean = group.close(grace=.05)
                except (Exception, SystemExit):
                    clean = False
            elif process is not None:
                clean = False
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    try:
                        stream.close()
                    except (Exception, SystemExit):
                        clean = False
        if not clean:
            raise Blocked()  # end the service; never accumulate hung retry probes
        return answer

    def endpoint(self):
        info = self.system.fs.stat(self.display, dir_fd=self.runtimefd, follow_symlinks=False)
        return Endpoint(self.system.uid, '/run/user/' + str(self.system.uid), self.display,
                        'hybrid-outer-wl-' + _root_valid(self.root)[2], info.st_uid,
                        stat.S_ISSOCK(info.st_mode), True, (info.st_dev, info.st_ino))

    def wait_ready(self, seconds):
        deadline = self.system.clock.now() + min(5.0, seconds)
        for _ in range(101):
            if self.closed or self.system.clock.now() >= deadline:
                return False
            try:
                info = self.system.fs.stat('ready', dir_fd=self.rootfd, follow_symlinks=False)
            except FileNotFoundError:
                self.system.clock.sleep(.05)
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_uid != self.system.uid or info.st_size != 16:
                return False
            raw = self.system.read('ready', 16, self.system.uid, dir_fd=self.rootfd)
            self.ready = raw == _root_valid(self.root)[2].encode('ascii')
            return self.ready
        return False

    def start(self, argv):
        if (self.closed or not self.ready or self.game is not None or type(argv) is not tuple
                or any(type(value) is not str for value in argv) or argv != gamescope_argv(self.plan)):
            raise Blocked()
        env = self.system.payload_environment(self, self.display)
        self.game = self.system.spawn(argv, env=env, cwd=self.root, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      close_fds=True, start_new_session=False)
        return 1


def session_child(root, execute=False, system=None, runner=None):
    rootfd = runtimefd = None
    if execute is not True:
        return 1
    try:
        _root_valid(root)
        system = _System() if system is None else system
        system.ensure()
        _root_valid(root, system.uid)
        fs = system.fs
        parent = fs.getppid()
        if parent <= 1 or fs.getpgid(0) != parent or fs.getsid(0) != parent:
            raise Blocked()
        rootfd = directory(root, system.uid, fs)
        runtimefd = directory('/run/user/' + str(system.uid), system.uid, fs)
        if (stat.S_IMODE(fs.fstat(rootfd).st_mode) != 0o700
                or stat.S_IMODE(fs.fstat(runtimefd).st_mode) != 0o700):
            raise Blocked()
        config = json.loads(system.read('plan.json', 4096, system.uid, dir_fd=rootfd))
        plan = make_plan(config, Native(fs=fs).binaries())
        if not plan.ok or plan.value.execute is not True:
            raise Blocked()
        child = _Child(system, plan.value, root, rootfd, runtimefd, system.child_display())
        deadline = system.clock.now() + 5
        for _ in range(101):
            if system.clock.now() >= deadline:
                raise Blocked()
            try:
                endpoint = child.endpoint()
            except FileNotFoundError:
                system.clock.sleep(.05)
                continue
            if not endpoint_valid(endpoint):
                raise Blocked()
            break
        else:
            raise Blocked()
        result = (supervise if runner is None else runner)(plan.value, child, system.clock)
        return 0 if type(result) is Result and result.ok else 1
    except (Exception, SystemExit):
        return 1
    finally:
        for fd in (runtimefd, rootfd):
            if fd is not None:
                system.fs.close(fd)


def entry(argv=None, adapter=None, emit=None, child=None):
    argv = sys.argv[1:] if argv is None else argv
    if ((type(argv) is list or type(argv) is tuple) and len(argv) == 3
            and all(type(value) is str for value in argv)
            and tuple(argv[:2]) == ('--execute', '--session-child')):
        try:
            _root_valid(argv[2])
            status = (session_child if child is None else child)(argv[2], execute=True)
            return status if type(status) is int and status in (0, 1) else 1
        except (Exception, SystemExit):
            return 1
    return main(argv, adapter, emit)


def main(argv=None, adapter=None, emit=None):
    emit = print if emit is None else emit
    attempted = False
    try:
        argv = sys.argv[1:] if argv is None else argv
        if ((type(argv) is not list and type(argv) is not tuple) or len(argv) > 16
                or any(type(value) is not str or len(value) > 256 for value in argv)):
            raise Blocked()
        parser = _Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--execute', action='store_true')
        parser.add_argument('--gaming-output-name', default='DP-2')
        parser.add_argument('--side-output-name', default='DP-1')
        for name, value in (('inner-width', 1280), ('inner-height', 720),
                            ('outer-width', 1280), ('outer-height', 720)):
            parser.add_argument('--' + name, default=value, type=int)
        args = parser.parse_args(argv)
        adapter = Native() if adapter is None else adapter
        result = make_plan(vars(args), adapter.binaries())
        if result.ok and args.execute:
            result = adapter.execute(result.value)
        if (type(result) is not Result or type(result.reason) is not str or result.reason not in
                ('', 'config_invalid', 'binary_invalid', 'session_failed', 'session_timeout',
                 'cleanup_failed', 'endpoint_invalid', 'provider_failed', 'provider_limit',
                 'output_invalid', 'script_unavailable')):
            raise Blocked()
        attempted = True
        emit(json.dumps({'status': 'plan_only' if result.ok and not args.execute else
                         'launcher_ended' if result.ok else 'blocked', 'reason': result.reason,
                         'live_cgroup_cleanup_verified': False}))
        return 0 if result.ok else 1
    except (Exception, SystemExit):
        if not attempted:
            try:
                emit('{"status":"blocked","reason":"session_failed"}')
            except (Exception, SystemExit):
                pass
        return 1


if __name__ == '__main__':
    sys.exit(entry())
