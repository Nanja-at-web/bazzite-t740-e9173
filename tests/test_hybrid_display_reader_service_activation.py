"""Only synthetic metadata/FDs; no native activation, environment or sockets."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display import reader_service_activation as activation
from hybrid_display import reader_service_runtime as runtime
from hybrid_display import reader_service_protocol as wire
from hybrid_display.reader_service_client import Packet
from hybrid_display.reader_service_policy import PeerFacts


def metadata():
    return {'LISTEN_PID': '41', 'LISTEN_FDS': '1'}


def unit_model():
    # Synthetic selected startup/sandbox requirements, not installable units
    # and not evidence that the future native binary or full sandbox exists.
    return ({'ExecStart': '/usr/libexec/hybrid-display-reader-v1', 'Type': 'exec',
             'Restart': 'no', 'NoNewPrivileges': 'yes', 'PrivateNetwork': 'yes',
             'ProtectSystem': 'strict', 'ProtectHome': 'yes', 'PrivateDevices': 'yes',
             'RestrictAddressFamilies': 'AF_UNIX', 'MemoryMax': '64M', 'TasksMax': '1',
             'RuntimeMaxSec': '4s', 'TimeoutStopSec': '100ms',
             'RootDirectory': '/usr/lib/hybrid-display-reader-v1/root',
             'StandardOutput': 'null', 'StandardError': 'null'},
            {'ListenStream': '%t/hybrid-display-reader-v1.sock', 'SocketMode': '0600',
             'Accept': 'no', 'Backlog': '1', 'Service': 'hybrid-display-reader-v1.service'})


class Clock:
    value = 0.0
    def now(self):
        return self.value


class Backend:
    def __init__(self):
        self.calls = 0
    def capture(self, request):
        self.calls += 1
        return wire.Response('owner_missing')


class Adapter:
    def __init__(self):
        self.events = []
        self.receipt = activation.Receipt(3, 1)
        self.descriptor = activation.Descriptor(3,
            runtime.Listener('unix', 'stream', True, False, True, True, (1, 2)), False)
        self.request = wire.encode_request(wire.Request(())).value
        self.response = b''
        self.facts = PeerFacts(1000, 1000, 23, 99, 'fixture', 1000,
                              'wayland', 'KDE', False, True, 'user', 'active', True)
        self.pending = []
        self.closed_fds = []
    def take(self, descriptor):
        self.events.append(('take', descriptor))
        return self.receipt
    def inspect(self, receipt):
        self.events.append('inspect')
        return self.descriptor
    def release(self, receipt):
        self.events.append('release')
    def accept(self, receipt, remaining):
        self.events.append('accept')
        return 8
    def peer(self, handle):
        self.events.append('peer')
        return (23, 1000, 1000)
    def session(self, credentials):
        return self.facts
    def recvmsg(self, handle, size, remaining):
        self.events.append('recv')
        data, self.request = self.request[:size], self.request[size:]
        return Packet(data)
    def close_received(self, handle):
        self.closed_fds.extend(self.pending)
        self.pending.clear()
    def send(self, handle, data, remaining):
        self.events.append('send')
        self.response += data
        return len(data)
    def close_client(self):
        self.events.append('close_client')
        self.close_received(None)


class ActivationTests(unittest.TestCase):
    def test_late_unconfirmed_take_still_reports_original_timeout_without_close(self):
        adapter, clock = Adapter(), Clock()
        def late(fd):
            adapter.events.append(('take', fd))
            clock.value = 4
            return None
        adapter.take = late
        result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, clock, Backend())
        self.assertEqual(result.reason, 'source_timeout')
        self.assertEqual(adapter.events, [('take', 3)])

    def test_pid_mismatch_does_not_even_visit_adapter(self):
        class Untouched:
            def __getattribute__(self, name):
                raise AssertionError('FD callback before metadata validation')
        for raw in (dict(metadata(), LISTEN_PID='42'), dict(metadata(), LISTEN_FDS='2')):
            self.assertEqual(activation.activate_once(raw, 41, 1000, 'fixture', Untouched(), Clock(), Backend()).reason,
                             'input_invalid')

    def test_current_pid_and_metadata_types_are_exact_without_callbacks(self):
        calls = []
        class Meta(type):
            def __eq__(self, other):
                calls.append('meta')
                raise AssertionError
        class Integer(int, metaclass=Meta):
            def __eq__(self, other):
                calls.append('eq')
                raise AssertionError
            def __str__(self):
                calls.append('str')
                raise AssertionError
        class Mapping(dict, metaclass=Meta):
            def __len__(self):
                calls.append('len')
                raise AssertionError
            def __iter__(self):
                calls.append('iter')
                raise AssertionError
        class Text(str, metaclass=Meta):
            def isdecimal(self):
                calls.append('decimal')
                raise AssertionError
        for raw, pid in ((metadata(), Integer(41)), (Mapping(metadata()), 41),
                         (dict(metadata(), LISTEN_PID=Text('41')), 41),
                         (dict(metadata(), LISTEN_FDS=Text('1')), 41),
                         (metadata(), True), (metadata(), 0)):
            adapter = Adapter()
            self.assertEqual(activation.activate_once(raw, pid, 1000, 'fixture', adapter, Clock(), Backend()).reason,
                             'input_invalid')
            self.assertFalse(adapter.events)
        class Key:
            def __hash__(self):
                calls.append('hash')
                return 42
            def __eq__(self, other):
                calls.append('keyeq')
                raise AssertionError
        raw = {Key(): '41', 'LISTEN_FDS': '1'}
        calls.clear()
        self.assertFalse(activation.validate_metadata(raw, 41).ok)
        self.assertEqual(calls, [])

    def test_receipt_descriptor_and_unit_values_reject_callback_subclasses(self):
        calls = []
        class Meta(type):
            def __eq__(self, other):
                calls.append('meta')
                raise AssertionError
        class Receipt(activation.Receipt, metaclass=Meta):
            def __getattribute__(self, name):
                calls.append('receipt')
                raise AssertionError
        class Descriptor(activation.Descriptor, metaclass=Meta):
            def __getattribute__(self, name):
                calls.append('descriptor')
                raise AssertionError
        class Sequence(tuple, metaclass=Meta):
            def __iter__(self):
                calls.append('iter')
                raise AssertionError
        class Text(str, metaclass=Meta):
            def __eq__(self, other):
                calls.append('eq')
                raise AssertionError
        self.assertFalse(activation.receipt_valid(Receipt(3, 1)))
        self.assertFalse(activation.descriptor_valid(Descriptor(3, None, False)))
        adapter = Adapter()
        adapter.descriptor = replace(adapter.descriptor,
            listener=replace(adapter.descriptor.listener, identity=Sequence((1, 2))))
        self.assertFalse(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), Backend()).ok)
        service, socket = unit_model()
        self.assertFalse(activation.validate_unit_model(dict(service, ExecStart=Text('unsafe')), socket).ok)
        self.assertEqual(calls, [])

    def test_invalid_owned_descriptor_never_calls_backend_or_accept(self):
        for value in (None, False, object(), activation.Descriptor(0, None, False),
                      activation.Descriptor(3, None, False)):
            adapter, backend = Adapter(), Backend()
            adapter.descriptor = value
            result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend)
            self.assertEqual(result.reason, 'source_not_allowed')
            self.assertNotIn('accept', adapter.events)
            self.assertEqual(adapter.events.count('release'), 1)
            self.assertEqual(backend.calls, 0)

    def test_runtime_is_called_once_only_after_explicit_transfer(self):
        adapter = Adapter()
        original = runtime.serve_once
        observed = []
        def serve(uid, session, io, clock, backend):
            observed.append(io.ownership.phase)
            io.ownership.close(activation.Phase.OWNED)
            self.assertNotIn('release', adapter.events)
            return original(uid, session, io, clock, backend)
        with patch.object(activation.runtime, 'serve_once', side_effect=serve) as call:
            self.assertTrue(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), Backend()).ok)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(observed, [activation.Phase.TRANSFERRED])
        self.assertEqual(adapter.events.count('release'), 1)

    def test_runtime_failure_before_its_cleanup_uses_runtime_ownership_guard(self):
        for error in (RuntimeError('private'), SystemExit('private')):
            adapter = Adapter()
            with patch.object(activation.runtime, 'serve_once', side_effect=error):
                result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), Backend())
            self.assertEqual(result.reason, 'reader_failed')
            self.assertEqual(adapter.events.count('close_client'), 1)
            self.assertEqual(adapter.events.count('release'), 1)

    def test_callback_exceptions_close_only_confirmed_resources_once(self):
        for operation in ('inspect', 'accept', 'peer', 'session', 'recvmsg', 'send',
                          'close_received', 'close_client', 'release'):
            for error in (RuntimeError('private-path'), SystemExit('private-path'), TimeoutError()):
                with self.subTest(operation=operation, error=type(error).__name__):
                    adapter = Adapter()
                    original = getattr(adapter, operation)
                    def fail(*args):
                        if operation in ('release', 'close_client'):
                            original(*args)
                        raise error
                    setattr(adapter, operation, fail)
                    result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), Backend())
                    self.assertFalse(result.ok)
                    self.assertIn(result.reason, wire.REASONS)
                    self.assertEqual(adapter.events.count('release'), 1)
                    self.assertLessEqual(adapter.events.count('close_client'), 1)
                    self.assertIsNone(result.value)
                    self.assertNotIn('private-path', repr(result))

    def test_backend_exception_and_systemexit_preserve_fixed_wire_response(self):
        for error in (RuntimeError('private'), SystemExit('private')):
            adapter, backend = Adapter(), Backend()
            def fail(request):
                backend.calls += 1
                raise error
            backend.capture = fail
            self.assertTrue(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend).ok)
            self.assertEqual(wire.decode_frame(adapter.response, True).value.reason, 'reader_failed')
            self.assertEqual(backend.calls, 1)
            self.assertEqual(adapter.events.count('release'), 1)

    def test_clock_failure_before_claim_and_no_default_leave_descriptor_untouched(self):
        adapter = Adapter()
        self.assertEqual(activation.activate_once(metadata(), 41, 1000, 'fixture').reason, 'source_unavailable')
        clock = Clock()
        clock.value = float('nan')
        self.assertEqual(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, clock, Backend()).reason,
                         'reader_failed')
        self.assertFalse(adapter.events)

    def test_cleanup_and_activation_time_share_original_budget(self):
        for operation in ('inspect', 'release'):
            adapter, clock = Adapter(), Clock()
            original = getattr(adapter, operation)
            def late(*args):
                result = original(*args)
                clock.value = 4
                return result
            setattr(adapter, operation, late)
            result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, clock, Backend())
            self.assertEqual(result.reason, 'source_timeout')
            self.assertEqual(adapter.events.count('release'), 1)

    def test_ancillary_registry_is_drained_through_runtime_adapter(self):
        adapter, backend = Adapter(), Backend()
        def ancillary(*args):
            adapter.pending = [19, 20]
            return Packet(b'', (19, 20), True)
        adapter.recvmsg = ancillary
        self.assertEqual(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend).reason,
                         'ipc_invalid')
        self.assertEqual(adapter.closed_fds, [19, 20])
        self.assertEqual(adapter.events.count('release'), 1)
        self.assertEqual(backend.calls, 0)

    def test_repeated_calls_have_separate_ownership_and_runtime_state(self):
        for _ in range(2):
            adapter, backend = Adapter(), Backend()
            self.assertTrue(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend).ok)
            self.assertEqual(adapter.events.count(('take', 3)), 1)
            self.assertEqual(adapter.events.count('release'), 1)
            self.assertEqual(backend.calls, 1)

    def test_product_has_no_native_activation_path_or_installable_units(self):
        import ast
        from tests.test_hybrid_display_safety import product_violations
        root = Path(__file__).resolve().parents[1]
        path = 'prototype/hybrid-display/src/hybrid_display/reader_service_activation.py'
        source = (root / path).read_text()
        self.assertEqual(product_violations(path, source), [])
        forbidden = {'socket', 'bind', 'listen', 'unlink', 'lstat', 'open', 'getenv', 'dup',
                     'fromfd', 'fileno', 'system', 'Popen', 'Thread'}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
                self.assertNotIn(name, forbidden)
        self.assertNotIn('__main__', source)
        self.assertNotIn('/run/user', source)
        self.assertFalse((root / 'prototype/hybrid-display/packaging').exists())

    def test_synthetic_native_unit_identity_and_single_socket_contract(self):
        service, socket = unit_model()
        self.assertTrue(activation.validate_unit_model(service, socket).ok)
        for command in ('python3 -m reader', '/usr/bin/python3',
                        '/usr/libexec/hybrid-display-reader-v1 --helper', '${READER}',
                        '/bin/sh -c reader', '/usr/libexec/other'):
            self.assertFalse(activation.validate_unit_model(dict(service, ExecStart=command), socket).ok)
        for field, value in (('Accept', 'yes'), ('ListenStream', '@abstract'), ('Backlog', '8'),
                             ('Service', 'neighbor.service'), ('ListenDatagram', '%t/other')):
            self.assertFalse(activation.validate_unit_model(service, dict(socket, **{field: value})).ok)
        for field in ('NoNewPrivileges', 'PrivateNetwork', 'ProtectSystem', 'PrivateDevices',
                      'RestrictAddressFamilies', 'MemoryMax', 'TasksMax', 'RuntimeMaxSec', 'Restart'):
            missing = dict(service)
            missing.pop(field)
            self.assertFalse(activation.validate_unit_model(missing, socket).ok)
        self.assertFalse(activation.validate_unit_model(dict(service, ExecStartPre='helper'), socket).ok)
        root = Path(__file__).resolve().parents[1] / 'prototype/hybrid-display'
        self.assertFalse((root / 'packaging').exists())
        self.assertFalse(list(root.rglob('*.service')))
        self.assertFalse(list(root.rglob('*.socket')))

    def test_confirmed_late_take_is_owned_then_closed_without_runtime(self):
        adapter, clock = Adapter(), Clock()
        take = adapter.take
        def late(fd):
            result = take(fd)
            clock.value = 4
            return result
        adapter.take = late
        with patch.object(activation.runtime, 'serve_once', wraps=activation.runtime.serve_once) as serve:
            result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, clock, Backend())
        self.assertEqual(result.reason, 'source_timeout')
        serve.assert_not_called()
        self.assertEqual(adapter.events, [('take', 3), 'release'])

    def test_ownership_state_has_one_adopt_transfer_and_terminal_close(self):
        adapter = Adapter()
        owner = activation.Ownership(adapter)
        self.assertIs(owner.phase, activation.Phase.UNOWNED)
        owner.close(activation.Phase.OWNED)
        self.assertFalse(adapter.events)
        self.assertFalse(owner.transfer())
        self.assertTrue(owner.adopt(adapter.receipt))
        self.assertIs(owner.phase, activation.Phase.OWNED)
        self.assertFalse(owner.adopt(adapter.receipt))
        self.assertTrue(owner.transfer())
        self.assertIs(owner.phase, activation.Phase.TRANSFERRED)
        self.assertFalse(owner.transfer())
        owner.close(activation.Phase.OWNED)
        self.assertFalse(adapter.events)
        owner.close(activation.Phase.TRANSFERRED)
        owner.close(activation.Phase.TRANSFERRED)
        self.assertIs(owner.phase, activation.Phase.CLOSED)
        self.assertEqual(adapter.events, ['release'])

    def test_owned_validation_failure_closes_once_before_runtime(self):
        listener = Adapter().descriptor.listener
        cases = [None, {'listener': listener}, activation.Descriptor(4, listener, False),
                 activation.Descriptor(3, listener, True)]
        for changes in ({'family': 'inet'}, {'kind': 'datagram'}, {'listening': False},
                        {'closed': True}, {'nonblocking': False}, {'cloexec': False},
                        {'identity': (True, 2)}):
            cases.append(activation.Descriptor(3, replace(listener, **changes), False))
        for descriptor in cases:
            with self.subTest(descriptor=type(descriptor).__name__):
                adapter = Adapter()
                adapter.descriptor = descriptor
                with patch.object(activation.runtime, 'serve_once', wraps=activation.runtime.serve_once) as serve:
                    result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), Backend())
                self.assertEqual(result.reason, 'source_not_allowed')
                serve.assert_not_called()
                self.assertEqual(adapter.events, [('take', 3), 'inspect', 'release'])

    def test_descriptor_replacement_after_validation_blocks_before_accept(self):
        adapter, backend = Adapter(), Backend()
        inspect = adapter.inspect
        def replaced(receipt):
            value = inspect(receipt)
            if adapter.events.count('inspect') > 1:
                value = replace(value, listener=replace(value.listener, identity=(1, 99)))
            return value
        adapter.inspect = replaced
        result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend)
        self.assertEqual(result.reason, 'source_not_allowed')
        self.assertNotIn('accept', adapter.events)
        self.assertEqual(adapter.events.count('release'), 1)
        self.assertEqual(backend.calls, 0)

    def test_confirmed_claim_reaches_existing_runtime_once(self):
        adapter, backend = Adapter(), Backend()
        result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.value, 0)
        self.assertEqual(adapter.events[0], ('take', 3))
        self.assertEqual(adapter.events.count(('take', 3)), 1)
        self.assertEqual(adapter.events.count('accept'), 1)
        self.assertEqual(adapter.events.count('peer'), 1)
        self.assertEqual(adapter.events.count('close_client'), 1)
        self.assertEqual(adapter.events.count('release'), 1)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(wire.decode_frame(adapter.response, True).value.reason, 'owner_missing')

    def test_unconfirmed_atomic_claim_never_inspects_or_releases_descriptor(self):
        for receipt in (None, False, activation.Receipt(4, 1), activation.Receipt(3, True)):
            adapter, backend = Adapter(), Backend()
            adapter.receipt = receipt
            result = activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), backend)
            self.assertEqual(result.reason, 'source_not_allowed')
            self.assertEqual(adapter.events, [('take', 3)])
            self.assertEqual(backend.calls, 0)
        for error in (RuntimeError('private'), SystemExit('private')):
            adapter = Adapter()
            def fail(fd):
                adapter.events.append(('take', fd))
                raise error
            adapter.take = fail
            self.assertEqual(activation.activate_once(metadata(), 41, 1000, 'fixture', adapter, Clock(), Backend()).reason,
                             'reader_failed')
            self.assertEqual(adapter.events, [('take', 3)])

    def test_exact_activation_metadata_is_accepted(self):
        result = activation.validate_metadata(metadata(), 41)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.value, 0)

    def test_invalid_metadata_never_touches_or_closes_descriptor(self):
        cases = [None, {}, {'LISTEN_PID': '42', 'LISTEN_FDS': '1'},
                 {'LISTEN_PID': '41'}, {'LISTEN_FDS': '1'}]
        cases += [dict(metadata(), LISTEN_FDS=value) for value in ('0', '2', '-1', '+1', '01', '', '1'*100, 1, True)]
        cases += [dict(metadata(), LISTEN_PID=value) for value in ('0', '-1', ' 41', '041', '41x', 41, True)]
        cases += [dict(metadata(), LISTEN_FDNAMES='unexpected')]
        for raw in cases:
            with self.subTest(raw=raw):
                adapter, backend = Adapter(), Backend()
                result = activation.activate_once(raw, 41, 1000, 'fixture', adapter, Clock(), backend)
                self.assertEqual(result.reason, 'input_invalid')
                self.assertFalse(adapter.events)
                self.assertEqual(backend.calls, 0)
