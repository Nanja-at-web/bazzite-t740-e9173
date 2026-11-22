"""Peer/time policy, only synthetic immutable metadata and an injected clock."""
import sys
import unittest
from dataclasses import replace, FrozenInstanceError
sys.path.insert(0, 'prototype/hybrid-display/src')
from hybrid_display import reader_service_policy as q

class Clock:
    def __init__(self, value=0):
        self.value = value
    def now(self):
        return self.value


def peer(**changes):
    return replace(q.PeerFacts(1000, 1000, 23, 99, 'fixture', 1000, 'wayland', 'KDE', False, True, 'user', 'active', True), **changes)

class PolicyTests(unittest.TestCase):
    def test_verified_peer_and_exact_session(self):
        self.assertTrue(q.peer_valid(peer(), 1000, 'fixture'))
        self.assertFalse(q.peer_valid(peer(), 1001, 'fixture'))
        self.assertFalse(q.peer_valid(peer(), 1000, 'other'))
        with self.assertRaises(FrozenInstanceError):
            peer().uid = 2

    def test_peer_missing_invalid_or_non_graphical_blocks(self):
        for changes in ({'uid': True}, {'uid': 0}, {'euid': 1001}, {'pid': False},
                {'pid': 0}, {'starttime': 0}, {'starttime': True}, {'session_id': ''},
                {'session_id': '../private'}, {'session_uid': 1001}, {'verified': False},
                {'session_type': 'tty'}, {'desktop': 'other'}, {'active': False},
                {'remote': True}, {'session_class': 'manager'}, {'state': 'closing'}):
            self.assertFalse(q.peer_valid(peer(**changes), 1000, 'fixture'))
        self.assertFalse(q.peer_valid(object.__new__(q.PeerFacts), 1000, 'fixture'))
        self.assertFalse(q.peer_valid(None, 1000, 'fixture'))

    def test_clock_absolute_boundary_and_no_extension(self):
        clock = Clock()
        budget = q.Budget(clock, 4.0)
        self.assertTrue(budget.check().ok)
        clock.value = 3.999
        self.assertTrue(budget.check().ok)
        clock.value = 4.0
        result = budget.check()
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, 'source_timeout')
        clock.value = 0
        self.assertFalse(budget.check().ok)

    def test_subdeadline_boundary(self):
        clock = Clock()
        budget = q.Budget(clock, 5.0)
        self.assertTrue(budget.check().ok)
        clock.value = .099
        self.assertTrue(budget.check(.1).ok)
        clock.value = .1
        self.assertEqual(budget.check(.1).reason, 'source_timeout')

    def test_bad_or_backwards_clock_latches(self):
        for bad in (True, -1, float('nan'), float('inf'), 10 ** 1000, 'secret', None):
            budget = q.Budget(Clock(bad), 4.0)
            self.assertEqual(budget.check().reason, 'reader_failed')
        clock = Clock(3)
        budget = q.Budget(clock, 4.0)
        self.assertTrue(budget.check().ok)
        clock.value = 2
        self.assertEqual(budget.check().reason, 'reader_failed')
        clock.value = 3
        self.assertEqual(budget.check().reason, 'reader_failed')

    def test_limits_cannot_be_extended(self):
        self.assertEqual(q.Limits().request, .25)
        with self.assertRaises(ValueError):
            q.Limits(request=1)

    def test_peer_callback_objects_are_never_visited(self):
        calls = []
        class Meta(type):
            def __eq__(self, other):
                calls.append('meta')
                raise AssertionError
        class Trap(str, metaclass=Meta):
            def __eq__(self, other):
                calls.append('eq')
                raise AssertionError
            def __len__(self):
                calls.append('len')
                raise AssertionError
        for name in ('uid', 'euid', 'pid', 'starttime', 'session_id', 'session_uid',
                     'session_type', 'desktop', 'remote', 'active', 'session_class', 'state', 'verified'):
            self.assertFalse(q.peer_valid(peer(**{name: Trap('private')}), 1000, 'fixture'))
        self.assertEqual(calls, [])

    def test_peer_constructor_cannot_retain_mutable_values(self):
        original = ['private']
        value = peer(session_id=original)
        original.append('changed')
        self.assertIsNone(value.session_id)
        self.assertFalse(q.peer_valid(value, 1000, 'fixture'))
        self.assertNotIn('private', repr(value))

    def test_clock_exception_and_bad_subdeadline_are_private(self):
        class Broken:
            def now(self):
                raise SystemExit('private')
        result = q.Budget(Broken(), 4).check()
        self.assertEqual(result.reason, 'reader_failed')
        self.assertNotIn('private', repr(result))
        for value in (True, float('nan'), float('inf'), 'private', -1):
            self.assertEqual(q.Budget(Clock(), 4).check(value).reason, 'reader_failed')

    def test_omitted_graphical_receipts_are_not_positive_defaults(self):
        value = q.PeerFacts(1000, 1000, 23, 99, 'fixture', 1000, verified=True)
        self.assertFalse(q.peer_valid(value, 1000, 'fixture'))
