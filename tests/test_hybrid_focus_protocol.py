import json
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-focus/src"))

from bazzite_hybrid_focus.model import FocusStatus, FocusTarget  # noqa: E402
from bazzite_hybrid_focus.protocol import (  # noqa: E402
    ProtocolError,
    encode_response,
    parse_request,
)


class ProtocolTests(unittest.TestCase):
    def test_all_allowlisted_commands_are_accepted(self):
        for command in ("game", "desktop", "toggle", "status"):
            with self.subTest(command=command):
                payload = json.dumps({"version": 1, "command": command}).encode()
                self.assertEqual(parse_request(payload), command)

    def test_extra_fields_are_rejected(self):
        payload = b'{"version":1,"command":"status","exec":"id"}'
        with self.assertRaises(ProtocolError):
            parse_request(payload)

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(ProtocolError):
            parse_request(b'{"version":1,"command":"reboot"}')

    def test_wrong_version_is_rejected(self):
        with self.assertRaises(ProtocolError):
            parse_request(b'{"version":2,"command":"status"}')

    def test_invalid_utf8_and_json_are_rejected(self):
        for payload in (b"\xff", b"{broken"):
            with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                parse_request(payload)

    def test_oversized_request_is_rejected(self):
        with self.assertRaises(ProtocolError):
            parse_request(b"x" * 4097)

    def test_response_contains_only_public_status_fields(self):
        status = FocusStatus(
            target=FocusTarget.DESKTOP,
            devices=(),
            glyph_family="neutral",
            degraded=False,
            message="Controller → Desktop 2",
        )
        response = json.loads(encode_response(status))
        self.assertEqual(
            response,
            {
                "ok": True,
                "target": "desktop",
                "glyph_family": "neutral",
                "degraded": False,
                "message": "Controller → Desktop 2",
            },
        )


if __name__ == "__main__":
    unittest.main()
