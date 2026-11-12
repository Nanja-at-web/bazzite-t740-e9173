"""Single-threaded private service for focus transitions."""

from __future__ import annotations

from pathlib import Path
from contextlib import nullcontext
import os
import socket
import stat
import struct
import threading
from typing import Callable

from .model import FocusTarget
from .protocol import (
    MAX_REQUEST_BYTES,
    ProtocolError,
    encode_error,
    encode_response,
    parse_request,
)


CredentialChecker = Callable[[socket.socket], bool]
REQUEST_TIMEOUT_SECONDS = 2.0


def same_user(connection: socket.socket) -> bool:
    credentials = connection.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
    )
    _pid, uid, _gid = struct.unpack("3i", credentials)
    return uid == os.getuid()


def _dispatch(command: str, controller):
    if command == "game":
        return controller.set_target(FocusTarget.GAME)
    if command == "desktop":
        return controller.set_target(FocusTarget.DESKTOP)
    if command == "toggle":
        return controller.toggle()
    return controller.status()


def _prepare_socket(
    socket_path: Path,
    listener_factory=socket.socket,
) -> socket.socket:
    socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(socket_path.parent, 0o700)
    if socket_path.exists() or socket_path.is_symlink():
        mode = socket_path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise RuntimeError(f"refusing to replace non-socket: {socket_path}")
        socket_path.unlink()
    listener = listener_factory(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    listener.listen(8)
    listener.settimeout(0.1)
    return listener


def handle_connection(
    connection: socket.socket,
    controller,
    credential_checker: CredentialChecker = same_user,
    transition_lock: threading.Lock | None = None,
) -> None:
    with connection:
        connection.settimeout(REQUEST_TIMEOUT_SECONDS)
        try:
            payload = connection.recv(MAX_REQUEST_BYTES + 1)
        except TimeoutError:
            connection.sendall(encode_error("request timed out"))
            return
        if not credential_checker(connection):
            connection.sendall(encode_error("peer UID rejected"))
            return
        try:
            command = parse_request(payload)
            lock_context = transition_lock if transition_lock is not None else nullcontext()
            with lock_context:
                response = encode_response(_dispatch(command, controller))
        except ProtocolError as error:
            response = encode_error(str(error))
        except Exception as error:
            response = encode_error(f"request failed: {error}")
        connection.sendall(response)


def serve(
    socket_path: Path,
    controller,
    stop_event: threading.Event,
    credential_checker: CredentialChecker | None = None,
    listener_factory=socket.socket,
) -> None:
    credential_checker = credential_checker or same_user
    recovery = controller.restore()
    if recovery.degraded:
        raise RuntimeError(f"controller recovery failed: {recovery.message}")
    listener = _prepare_socket(
        Path(socket_path), listener_factory=listener_factory
    )
    transition_lock = threading.Lock()
    try:
        while not stop_event.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            handle_connection(
                connection,
                controller,
                credential_checker,
                transition_lock=transition_lock,
            )
    finally:
        listener.close()
        controller.restore()
        try:
            Path(socket_path).unlink()
        except FileNotFoundError:
            pass
