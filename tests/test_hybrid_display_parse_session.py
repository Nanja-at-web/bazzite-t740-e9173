from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from tests.test_hybrid_display_reader_fixtures import OWN, session_raw
from hybrid_display.host_reader import EnvKey, OwnIdentity, SessionRaw
from hybrid_display.parse_session import parse_session, parse_process, parse_session_context

class SessionTests(unittest.TestCase):

    def test_verified_own_session_only(self):
        result = parse_session(session_raw(), OWN)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(result.value.session_id, 's1')
        self.assertNotIn('s1', repr(result))

    def test_foreign_remote_inactive_uid_and_privileged_block(self):
        for changes in ({'Remote': True}, {'Active': False}, {'User': (1001, '/user/1001')}, {'Type': 'tty'}, {'Desktop': 'KDE-private'}, {'State': 'closing'}, {'Active': 1}):
            result = parse_session(session_raw(**changes), OWN)
            self.assertEqual(result.reasons, ('session_unverified',))
            self.assertIsNone(result.value)
        for own in (OwnIdentity(0, 0, 10), OwnIdentity(1000, 0, 10), OwnIdentity(1000, 1000, 10, True)):
            self.assertEqual(parse_session(session_raw(), own).reasons, ('session_unverified',))

    def test_env_mismatch_missing_unknown_and_foreign_owners_block(self):
        raw = session_raw()
        for invalid in (SessionRaw(raw.env[:-1], raw.session, raw.owners), SessionRaw(raw.env, raw.session, (('kwin', ':1.2', 1000, 11, 's2'), raw.owners[1])), SessionRaw(raw.env, raw.session + (('private', 'value'),), raw.owners)):
            self.assertFalse(parse_session(invalid, OWN).ok)
        bad = SessionRaw(raw.env[:-1] + ((EnvKey.BUS, b'tcp:private'),), raw.session, raw.owners)
        self.assertEqual(parse_session(bad, OWN).reasons, ('session_bus_invalid',))

    def test_process_stat_closing_parentheses_and_uid_projection(self):
        tail = ['R'] + ['0'] * 49
        tail[19] = '1234'
        stat = ('15 (steam name) nested)) ' + ' '.join(tail) + '\n').encode()
        status = b'Name:\tignored\nUid:\t1000\t1000\t1000\t1000\n'
        result = parse_process(stat, status, 15, 1000)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(result.value, ('steam name) nested)', 1234))
        for bad_stat, bad_status in ((stat[:-2], status), (stat, status + b'Uid: 1000 1000 1000 1000\n'), (stat, b'Uid: 1001 1001 1001 1001\n')):
            rejected = parse_process(bad_stat, bad_status, 15, 1000)
            self.assertEqual(rejected.reasons, ('process_identity_unverified',))
            self.assertIsNone(rejected.value)

    def test_own_context_can_be_checked_before_gui_owners_exist(self):
        raw = session_raw()
        context = SessionRaw(raw.env, raw.session, ())
        result = parse_session_context(context, OWN)
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(result.value.owners, ())
        self.assertEqual(parse_session_context(SessionRaw(raw.env, session_raw(Remote=True).session, ()), OWN).reasons, ('session_unverified',))
