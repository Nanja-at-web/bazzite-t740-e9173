"""Strict local wire protocol shared by all focus controls."""

import json

from .model import FocusStatus


MAX_REQUEST_BYTES = 4096
COMMANDS = frozenset({"game", "desktop", "toggle", "status"})


class ProtocolError(ValueError):
    pass


def parse_request(payload: bytes) -> str:
    if len(payload) > MAX_REQUEST_BYTES:
        raise ProtocolError("request too large")
    try:
        decoded = payload.decode("utf-8")
        request = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("invalid JSON request") from error
    if not isinstance(request, dict) or set(request) != {"version", "command"}:
        raise ProtocolError("request must contain only version and command")
    if request["version"] != 1:
        raise ProtocolError("unsupported protocol version")
    command = request["command"]
    if not isinstance(command, str) or command not in COMMANDS:
        raise ProtocolError("unsupported command")
    return command


def encode_response(status: FocusStatus) -> bytes:
    return (
        json.dumps(
            {
                "ok": not status.degraded,
                "target": status.target.value,
                "glyph_family": status.glyph_family,
                "degraded": status.degraded,
                "message": status.message,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def encode_error(message: str, target: str = "game") -> bytes:
    return (
        json.dumps(
            {
                "ok": False,
                "target": target,
                "glyph_family": "neutral",
                "degraded": True,
                "message": message,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
