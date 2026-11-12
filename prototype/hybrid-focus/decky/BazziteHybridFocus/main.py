"""Unprivileged Decky backend for the Hybrid Focus user service."""

import asyncio
import json
import os
from pathlib import Path
import socket

import decky


MAX_RESPONSE_BYTES = 4096


def _socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "bazzite-hybrid-focus/control.sock"

    configured_home = os.environ.get("DECKY_USER_HOME", decky.DECKY_USER_HOME)
    user_home = Path(configured_home)
    try:
        user_id = user_home.stat().st_uid
    except OSError as error:
        raise RuntimeError("cannot determine Decky user runtime directory") from error
    return Path("/run/user") / str(user_id) / "bazzite-hybrid-focus/control.sock"


def _request(command: str) -> dict:
    payload = json.dumps(
        {"version": 1, "command": command}, separators=(",", ":")
    ).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2.0)
        connection.connect(str(_socket_path()))
        connection.sendall(payload)
        connection.shutdown(socket.SHUT_WR)
        chunks = []
        total = 0
        while True:
            chunk = connection.recv(1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise RuntimeError("Hybrid Focus response is too large")
            chunks.append(chunk)
    response = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeError("invalid Hybrid Focus response")
    return response


class Plugin:
    async def get_status(self) -> dict:
        return await asyncio.to_thread(_request, "status")

    async def set_target(self, target: str) -> dict:
        if target not in {"desktop", "game"}:
            raise ValueError("target must be desktop or game")
        return await asyncio.to_thread(_request, target)

    async def _main(self):
        decky.logger.info("Bazzite Hybrid Focus QAM backend loaded")

    async def _unload(self):
        decky.logger.info("Bazzite Hybrid Focus QAM backend unloaded")
