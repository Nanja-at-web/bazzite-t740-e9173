"""Client for the private Hybrid Focus Unix socket."""

import json
from pathlib import Path
import socket

from .protocol import COMMANDS, MAX_REQUEST_BYTES


def request(socket_path: Path, command: str, timeout: float = 2.0) -> dict:
    if command not in COMMANDS:
        raise ValueError(f"unsupported command: {command}")
    payload = json.dumps(
        {"version": 1, "command": command}, separators=(",", ":")
    ).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(socket_path))
        connection.sendall(payload)
        connection.shutdown(socket.SHUT_WR)
        chunks = []
        total = 0
        while True:
            chunk = connection.recv(1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_REQUEST_BYTES:
                raise OSError("response too large")
            chunks.append(chunk)
    response = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(response, dict):
        raise OSError("invalid response")
    return response
