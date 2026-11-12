import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-focus/src"))

from bazzite_hybrid_focus.model import (  # noqa: E402
    ControllerDevice,
    FocusTarget,
    classify_glyph_family,
)


class FocusModelTests(unittest.TestCase):
    def device(self, vendor_id=None, name="Controller"):
        return ControllerDevice(
            path="/org/shadowblip/InputPlumber/CompositeDevice0",
            name=name,
            vendor_id=vendor_id,
            product_id=None,
            profile_name="Default",
        )

    def test_focus_target_wire_values_are_stable(self):
        self.assertEqual(FocusTarget.GAME.value, "game")
        self.assertEqual(FocusTarget.DESKTOP.value, "desktop")

    def test_microsoft_vendor_is_xbox(self):
        self.assertEqual(classify_glyph_family([self.device("0x045E")]), "xbox")

    def test_sony_vendor_is_playstation(self):
        self.assertEqual(classify_glyph_family([self.device("054c")]), "playstation")

    def test_nintendo_vendor_is_nintendo(self):
        self.assertEqual(classify_glyph_family([self.device("057E")]), "nintendo")

    def test_unknown_vendor_uses_neutral_labels(self):
        self.assertEqual(classify_glyph_family([self.device("1234")]), "neutral")

    def test_missing_vendor_does_not_guess_from_name(self):
        self.assertEqual(
            classify_glyph_family([self.device(None, "Xbox Wireless Controller")]),
            "neutral",
        )

    def test_mixed_known_families_use_neutral_labels(self):
        devices = [self.device("045e"), self.device("054c")]
        self.assertEqual(classify_glyph_family(devices), "neutral")

    def test_empty_device_set_uses_neutral_labels(self):
        self.assertEqual(classify_glyph_family([]), "neutral")


if __name__ == "__main__":
    unittest.main()
