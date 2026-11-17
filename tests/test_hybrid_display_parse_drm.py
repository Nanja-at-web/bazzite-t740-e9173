from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype/hybrid-display/src'))
from tests.test_hybrid_display_reader_fixtures import edid, frame
from hybrid_display.host_reader import DrmRaw, DrmData, KScreenData, KScreenProfile
from hybrid_display.parse_drm import parse_drm, associate
from hybrid_display.parse_kscreen import parse_kscreen

class DrmTests(unittest.TestCase):

    def raw(self, payload=None, **changes):
        args = dict(card=0, connector='DP-1', gpu='0000:01:00.0', status=b'connected\n', enabled=b'enabled\n', edid=edid() if payload is None else payload)
        args.update(changes)
        return DrmRaw(**args)

    def test_edid_header_checksum_extension_limit_empty_and_flags(self):
        self.assertTrue(parse_drm((self.raw(),)).ok)
        for payload in (b'', b'x' * 128, edid()[:-1], edid() + edid(), edid() * 33):
            result = parse_drm((self.raw(payload),))
            self.assertEqual(result.reasons, ('edid_invalid',))
        self.assertTrue(parse_drm((self.raw(b'', status=b'disconnected\n', enabled=b'disabled\n'),)).ok)
        self.assertEqual(parse_drm((self.raw(status=b'connected-private'),)).reasons, ('drm_status_invalid',))

    def test_unique_association_requires_edid_and_flags_agree(self):
        parsed_ks = parse_kscreen(frame(), KScreenProfile.SYNTHETIC_V1)
        parsed_drm = parse_drm((self.raw(),))
        self.assertTrue(parsed_ks.ok, parsed_ks.reasons)
        self.assertTrue(parsed_drm.ok, parsed_drm.reasons)
        ks = parsed_ks.value
        drm = parsed_drm.value
        success = associate(ks, drm, ((1, edid()),))
        self.assertTrue(success.ok, success.reasons)
        record = success.value.outputs[0]
        self.assertEqual(len(record[0]), 64)
        self.assertNotIn(record[0], repr(success))
        self.assertNotIn('0000:01:00.0', repr(success))
        self.assertEqual(associate(ks, drm, ((1, edid(2)),)).reasons, ('association_ambiguous',))
        parsed_disabled = parse_drm((self.raw(enabled=b'disabled\n'),))
        self.assertTrue(parsed_disabled.ok, parsed_disabled.reasons)
        disabled = parsed_disabled.value
        self.assertEqual(associate(ks, disabled, ((1, edid()),)).reasons, ('inventory_changed',))

    def test_duplicate_gpu_connector_or_digest_is_never_selected(self):
        for raw in ((self.raw(), self.raw()), (self.raw(), self.raw(card=1, gpu='0000:02:00.0'))):
            self.assertEqual(parse_drm(raw).reasons, ('association_ambiguous',))

    def test_malformed_exact_nested_records_are_rejected(self):
        for kscreen, drm in ((KScreenData((1,)), DrmData((1,))), (KScreenData(1), DrmData(())), (object.__new__(KScreenData), DrmData(()))):
            try:
                result = associate(kscreen, drm, ((1, b''),))
            except Exception:
                self.fail('Malformed nested DTO must return a fixed blocked result')
            self.assertEqual(result.reasons, ('association_ambiguous',))
            self.assertIsNone(result.value)
