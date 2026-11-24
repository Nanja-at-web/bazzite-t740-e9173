"""Compile the test-only C17 Fake-ABI harness outside the repository."""
from pathlib import Path
from dataclasses import replace
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tests.test_hybrid_display_reader_service_activation import Adapter, Clock, Backend, metadata
from hybrid_display import reader_service_activation as reference
from hybrid_display.reader_service_protocol import Result, REASONS

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'prototype/hybrid-display/native'
FLAGS = ['-std=c17', '-Wall', '-Wextra', '-Werror', '-pedantic']


def build(directory, extra=()):
    executable = Path(directory) / 'reader-harness'
    result = subprocess.run(['cc', *FLAGS, *extra, '-I', str(NATIVE),
        str(NATIVE / 'reader_service_native.c'),
        str(NATIVE / 'tests/reader_service_native_harness.c'), '-o', str(executable)],
        capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError('C17 compilation failed:\n' + result.stderr)
    return executable


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='reader-native-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        executable = build(cls.temporary.name)
        cls.execution = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
        cls.rows = [line.split()[1:] for line in cls.execution.stdout.splitlines() if line.startswith('CASE ')]

    def test_strict_c17_fake_abi_harness(self):
        result = self.execution
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], 'CASES 59 OK')
        self.assertEqual(result.stderr, '')
        names = [row[0] for row in self.rows]
        self.assertEqual(len(names), 59)
        self.assertEqual(len(names), len(set(names)))

    def test_shared_synthetic_case_table_matches_python_reference(self):
        # The C table is the single scenario source; no second expected-results
        # table. Feed its variants to the merged, unmodified Python reference.
        compared = 0
        for row in self.rows:
            name = row[0]
            mode, fault, reason, takes, inspections, handoffs, releases = map(int, row[1:])
            if fault in (27, 39):
                # C-only narrower uint64 timestamp bound / ABI table snapshot.
                continue
            with self.subTest(case=name):
                raw, pid = metadata(), 41
                if mode == 1: raw.pop('LISTEN_PID')
                if mode == 2: pid = 42
                if mode == 3: raw['LISTEN_PID'] = 'x1'
                if mode == 4: raw.pop('LISTEN_FDS')
                if mode == 5: raw['LISTEN_FDS'] = '0'
                if mode == 6: raw['LISTEN_FDS'] = '2'
                if mode in (7, 14): raw['UNKNOWN'] = 'x'
                if mode == 8: raw['LISTEN_PID'] = '1' * 11
                if mode == 9: raw['LISTEN_PID'] = '2147483648'
                if mode == 10: raw['LISTEN_PID'] = '01'
                if mode == 11: raw['LISTEN_FDS'] = '01'
                if mode == 12: raw['LISTEN_PID'] = '4\x00'
                if mode == 13: raw['LISTEN_FDS'] = 'x'
                if mode == 15: raw['LISTEN_PID'] = True
                if mode == 16: pid = 0
                if mode == 99: raw = None
                adapter, clock = Adapter(), Clock()
                clock.value = 1.0
                metrics = {'runtime': 0, 'consumed': fault == 37}
                initial_inspect, initial_release = adapter.inspect, adapter.release
                def take(fd):
                    adapter.events.append(('take', fd))
                    if metrics['consumed'] or fault == 1: return None
                    if fault in (2, 4): raise RuntimeError()
                    if fault == 3: raise TimeoutError()
                    if fault == 21:
                        clock.value = 5.0
                        return None
                    if fault in (5, 6, 7, 35):
                        return {5: reference.Receipt(4, 1), 6: None,
                                7: reference.Receipt(3, 0), 35: reference.Receipt(3, 2**64-1)}[fault]
                    if fault == 20: clock.value = 5.0
                    if fault == 25: clock.value = 0.0
                    return adapter.receipt
                def inspect(receipt):
                    value = initial_inspect(receipt)
                    if fault in (16, 17): raise RuntimeError()
                    if fault == 22: clock.value = 5.0
                    updates = {8: {'family': 'inet'}, 9: {'kind': 'datagram'},
                               10: {'listening': False}, 12: {'closed': True},
                               14: {'nonblocking': False}, 15: {'cloexec': False}}
                    if fault in updates: value = replace(value, listener=replace(value.listener, **updates[fault]))
                    if fault == 11: value = replace(value, connected=True)
                    if fault == 13: value = replace(value, descriptor=4)
                    return value
                def release(receipt):
                    initial_release(receipt)
                    metrics['consumed'] = True
                    if fault == 24: clock.value = 5.0
                    if fault in (28, 29, 31): raise RuntimeError()
                def handoff(uid, session, io, injected_clock, backend):
                    metrics['runtime'] += 1
                    self.assertIs(io.ownership.phase, reference.Phase.TRANSFERRED)
                    if fault in (18, 19, 41): raise RuntimeError()
                    if fault == 23: clock.value = 5.0
                    io.close_client()
                    io.close_activation()
                    if fault == 30: io.close_activation()
                    self.assertIs(io.ownership.phase, reference.Phase.CLOSED)
                    return Result(0)
                adapter.take, adapter.inspect, adapter.release = take, inspect, release
                if fault in (26, 36): clock.value = float('nan')
                provider = None if fault in (32, 33, 34) else adapter
                with patch.object(reference.runtime, 'serve_once', side_effect=handoff):
                    result = reference.activate_once(raw, pid, 1000, 'fixture', provider, clock, Backend())
                    if fault == 38:
                        self.assertTrue(result.ok)
                        result = reference.activate_once(raw, pid, 1000, 'fixture', provider, clock, Backend())
                actual_reason = 0 if result.ok else REASONS.index(result.reason) + 1
                self.assertEqual(actual_reason, reason)
                self.assertEqual(adapter.events.count(('take', 3)), takes)
                self.assertEqual(adapter.events.count('inspect'), inspections)
                self.assertEqual(metrics['runtime'], handoffs)
                self.assertEqual(adapter.events.count('release'), releases)
                compared += 1
        self.assertEqual(compared, 57)

    def test_closed_native_reason_table_and_private_result(self):
        header = (NATIVE / 'reader_service_native.h').read_text()
        fields = re.search(r'struct hd_result\s*\{([^}]+)\}', header).group(1)
        self.assertEqual(fields.strip(), 'enum hd_reason reason;')
        pairs = dict(re.findall(r'\b(HD_[A-Z_]+)\s*=\s*(\d+)', header))
        for index, reason in enumerate(REASONS, 1):
            self.assertEqual(int(pairs['HD_' + reason.upper()]), index)

    def test_no_productive_os_heap_or_dynamic_runtime_symbols(self):
        core = (NATIVE / 'reader_service_native.c').read_text()
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', core, flags=re.S)
        forbidden = ('getenv', 'socket', 'accept', 'bind', 'listen', 'close', 'poll', 'read',
                     'write', 'malloc', 'calloc', 'realloc', 'free', 'dlopen', 'system', 'popen', 'fork')
        for symbol in forbidden:
            self.assertNotRegex(text, r'\b' + symbol + r'\s*\(')
        self.assertNotRegex(text, r'\bmain\s*\(')
        with tempfile.TemporaryDirectory(prefix='reader-native-symbols-') as directory:
            obj = Path(directory) / 'core.o'
            subprocess.run(['cc', *FLAGS, '-I', str(NATIVE), '-c', str(NATIVE / 'reader_service_native.c'),
                            '-o', str(obj)], check=True, capture_output=True, timeout=30)
            # nm reads only the already-built temporary object. The bounded
            # deadline still guards hangs while allowing loaded CI runners;
            # it changes neither the symbol allowlist nor compiler hardening.
            symbols = subprocess.check_output(['nm', '-u', str(obj)], text=True, timeout=30)
            # Exact compiler stack-protection runtime reference; no OS/heap API.
            self.assertTrue(all(line.split()[-1] in {'memcpy', 'memset', '__stack_chk_fail'} for line in symbols.splitlines()), symbols)
