import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype/hybrid-focus/src"))

from bazzite_hybrid_focus.client import request  # noqa: E402
from bazzite_hybrid_focus.model import FocusStatus, FocusTarget  # noqa: E402
from bazzite_hybrid_focus.server import (  # noqa: E402
    _prepare_socket,
    handle_connection,
    serve,
)


class FakeController:
    def __init__(self, delay=0):
        self.target = FocusTarget.GAME
        self.restore_calls = 0
        self.calls = []
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def _reply(self, command, target=None):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            self.calls.append(command)
            if target is not None:
                self.target = target
            return FocusStatus(
                target=self.target,
                devices=(),
                glyph_family="neutral",
                message=command,
            )
        finally:
            with self.lock:
                self.active -= 1

    def set_target(self, target):
        return self._reply(target.value, target)

    def toggle(self):
        target = (
            FocusTarget.DESKTOP
            if self.target == FocusTarget.GAME
            else FocusTarget.GAME
        )
        return self._reply("toggle", target)

    def status(self):
        return self._reply("status")

    def restore(self):
        self.restore_calls += 1
        self.target = FocusTarget.GAME
        return FocusStatus(
            target=self.target,
            devices=(),
            glyph_family="neutral",
            message="restore",
        )


class FakeListener:
    def __init__(self, *_):
        self.path = None
        self.closed = False

    def bind(self, path):
        self.path = Path(path)
        self.path.touch()

    def listen(self, _backlog):
        pass

    def settimeout(self, _timeout):
        pass

    def accept(self):
        raise TimeoutError

    def close(self):
        self.closed = True


class TimeoutTrackingConnection:
    def __init__(self):
        self.timeout = None
        self.responses = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, _size):
        return b'{"version":1,"command":"status"}'

    def sendall(self, payload):
        self.responses.append(payload)


class ServiceContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.socket_path = Path(self.temporary.name) / "run/control.sock"

    def round_trip(self, controller, command, credential_checker=lambda _c: True, lock=None):
        client, server = socket.socketpair()
        thread = threading.Thread(
            target=handle_connection,
            args=(server, controller, credential_checker),
            kwargs={"transition_lock": lock},
            daemon=True,
        )
        client.sendall(
            json.dumps({"version": 1, "command": command}).encode("utf-8")
        )
        client.shutdown(socket.SHUT_WR)
        thread.start()
        payload = b""
        while True:
            chunk = client.recv(1024)
            if not chunk:
                break
            payload += chunk
        thread.join(2)
        client.close()
        return json.loads(payload)

    def test_socket_path_is_created_private(self):
        listener = _prepare_socket(
            self.socket_path, listener_factory=FakeListener
        )
        mode = stat.S_IMODE(os.stat(self.socket_path).st_mode)
        listener.close()
        self.assertEqual(mode, 0o600)

    def test_one_request_gets_one_response(self):
        controller = FakeController()
        response = self.round_trip(controller, "desktop")
        self.assertTrue(response["ok"])
        self.assertEqual(response["target"], "desktop")
        self.assertIn("desktop", controller.calls)

    def test_each_client_gets_a_bounded_read_timeout(self):
        connection = TimeoutTrackingConnection()
        handle_connection(
            connection,
            FakeController(),
            credential_checker=lambda _connection: True,
        )
        self.assertIsNotNone(connection.timeout)
        self.assertGreater(connection.timeout, 0)
        self.assertTrue(connection.responses)

    def test_peer_uid_rejection_causes_no_state_change(self):
        controller = FakeController()
        response = self.round_trip(
            controller, "desktop", credential_checker=lambda _connection: False
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["target"], "game")
        self.assertNotIn("desktop", controller.calls)

    def test_requests_are_serialized(self):
        controller = FakeController(delay=0.05)
        lock = threading.Lock()
        threads = [
            threading.Thread(
                target=self.round_trip,
                args=(controller, "status"),
                kwargs={"lock": lock},
                daemon=True,
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(controller.max_active, 1)

    def test_startup_and_shutdown_restore_game_mapping(self):
        controller = FakeController()
        stop = threading.Event()
        stop.set()
        serve(
            self.socket_path,
            controller,
            stop,
            listener_factory=FakeListener,
        )
        self.assertGreaterEqual(controller.restore_calls, 2)

    def test_client_rejects_non_allowlisted_command(self):
        with self.assertRaises(ValueError):
            request(self.socket_path, "reboot")


if __name__ == "__main__":
    unittest.main()
