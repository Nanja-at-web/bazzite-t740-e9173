"""Synthetic metadata policy tests; no host path resolution."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from hybrid_display.host_reader import SourceKey, QueryKey, FileSource, BusQuery, ConnectorManifest
from hybrid_display.reader_policy import Resolution, QueryContext, validate_manifest, validate_source, validate_query

def resolution(card=0, connector='DP-1', gpu='0000:01:00.0'):
    prefix = ('devices', 'pci0000:00', gpu)
    card_name = 'card' + str(card)
    connector_name = card_name + '-' + connector
    links = (('card', card, '', gpu, 1, prefix + ('drm', card_name)), ('device', card, '', gpu, 1, prefix), ('connector', card, connector, gpu, 1, prefix + ('drm', card_name, connector_name)))
    return Resolution('sysfs', 'regular', 1, 2, True, False, prefix + ('drm', card_name, connector_name, 'status'), links)

class PolicyTests(unittest.TestCase):

    def test_session_property_without_resolved_path_is_denied(self):
        context = QueryContext(1000, 10, (('org.freedesktop.login1', ':1.1', 9, 0),),
                               session_id='s1')
        query = BusQuery(QueryKey.SESSION_PROPERTY, 'system', ':1.1', 'Id')
        self.assertEqual(validate_query(query, context).reasons, ('source_not_allowed',))
        context = replace(context, session_path='/session/s1')
        bound = replace(query, object_path='/session/s1')
        self.assertTrue(validate_query(bound, context).ok)
        for path in ('/session/neighbor', '', True):
            self.assertFalse(validate_query(replace(bound, object_path=path), context).ok)

    def test_exact_manifest_is_bounded_and_closed(self):
        good = ConnectorManifest(((0, 'DP-1'),), True)
        result = validate_manifest(good)
        self.assertTrue(result.ok, result.reasons)
        for invalid in (ConnectorManifest(((True, 'DP-1'),), True), ConnectorManifest(((0, '../DP-1'),), True), ConnectorManifest(((0, 'DP-1'),) * 17, True), ConnectorManifest(((0, 'DP-1'),) * 2, True), ConnectorManifest(((0, 'DP-1'),), False)):
            self.assertEqual(validate_manifest(invalid).reasons, ('source_not_allowed',))

    def test_normal_links_allowed_swapped_gpu_traversal_mount_denied(self):
        source = FileSource(SourceKey.DRM_STATUS, 0, 'DP-1')
        metadata = resolution()
        self.assertTrue(validate_source(source, metadata).ok)
        bad_links = metadata.links[:-1] + (metadata.links[-1][:3] + ('0000:02:00.0',) + metadata.links[-1][4:],)
        for bad in (replace(metadata, same_mount=False), replace(metadata, final_symlink=True), replace(metadata, kind='fifo'), replace(metadata, components=('devices', '..', 'private')), replace(metadata, links=bad_links), replace(metadata, links=())):
            result = validate_source(source, bad)
            self.assertEqual(result.reasons, ('source_not_allowed',))
            self.assertIsNone(result.value)

    def test_closed_keys_and_pid_scope_before_callbacks(self):
        for source in ('private/path', FileSource('drm_status', 0, 'DP-1'), FileSource(SourceKey.DRM_STATUS, True, 'DP-1'), FileSource(SourceKey.DRM_STATUS, 0, 'DP-1/neighbor'), FileSource(SourceKey.PROCESS_STAT, pid=99)):
            self.assertFalse(validate_source(source).ok)
        calls = []

        class Meta(type):

            def __eq__(self, other):
                calls.append('eq')
                return True

        class Trap(tuple, metaclass=Meta):

            def __len__(self):
                calls.append('len')
                return 1

            def __iter__(self):
                calls.append('iter')
                return super().__iter__()
        self.assertFalse(validate_manifest(ConnectorManifest(Trap(((0, 'DP-1'),)), True)).ok)
        self.assertEqual(calls, [])

    def test_fixed_bus_methods_require_verified_unique_owner_and_scope(self):
        context = QueryContext(1000, 10, (('org.freedesktop.login1', ':1.1', 9, 0), ('org.kde.KWin', ':1.2', 11, 1000), ('org.kde.KScreen', ':1.3', 12, 1000)), (), (1,), True, 's1')
        query = BusQuery(QueryKey.CONFIG, 'session', ':1.3')
        self.assertTrue(validate_query(query, context).ok)
        for bad in (replace(query, autostart=True), replace(query, target=':1.4'), replace(query, bus='tcp'), replace(query, key='Set'), replace(query, key='Introspect')):
            self.assertEqual(validate_query(bad, context).reasons, ('source_not_allowed',))
        self.assertFalse(validate_query(query, replace(context, session_bound=False)).ok)

    def test_auth_hello_allowed_no_requestname_addmatch_or_service_start(self):
        context = QueryContext(1000, 10)
        for key in (QueryKey.AUTH, QueryKey.HELLO):
            self.assertTrue(validate_query(BusQuery(key), context).ok)
        for method in ('RequestName', 'AddMatch', 'StartServiceByName'):
            self.assertEqual(validate_query(BusQuery(method), context).reasons, ('source_not_allowed',))

    def test_final_metadata_cannot_substitute_neighbor_root(self):
        source = FileSource(SourceKey.DRM_STATUS, 0, 'DP-1')
        metadata = resolution()
        forged = replace(metadata, components=('private',) + metadata.components[-5:])
        self.assertEqual(validate_source(source, forged).reasons, ('source_not_allowed',))

    def test_logind_server_pid_is_not_a_session_lookup_target(self):
        context = QueryContext(1000, 10, (('org.freedesktop.login1', ':1.1', 9, 0),))
        query = BusQuery(QueryKey.SESSION_BY_PID, 'system', ':1.1', 9)
        self.assertEqual(validate_query(query, context).reasons, ('source_not_allowed',))
