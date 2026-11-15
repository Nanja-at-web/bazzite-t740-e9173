"""Pure argument and environment builders over supplied ordinary Python data.

No probing or launching. These results do not grant runtime permission and are
not a sandbox for executing caller-chosen client programs. Client arguments are
opaque data after --; no client-specific flags or wrappers are guessed.
"""

from dataclasses import dataclass, field
from collections.abc import Mapping
from enum import Enum
import re
from types import MappingProxyType


class WaylandSupport(Enum):
    """Previously established support for --expose-wayland, never auto-detected."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LaunchOptions:
    """Local task-3 input type; foundation model.py stays unchanged.

    Input payloads are hidden from repr even when malformed. A caller's list is
    detached; validation is performed by build_argv, not by throwing in init.
    """
    client_argv: tuple[str, ...] = field(repr=False)
    inner_width: int = field(default=1920, repr=False)
    inner_height: int = field(default=1080, repr=False)
    outer_width: int = field(default=1920, repr=False)
    outer_height: int = field(default=1080, repr=False)
    fps: int = field(default=60, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.client_argv, list):
            object.__setattr__(self, "client_argv", tuple(self.client_argv))


@dataclass(frozen=True)
class ArgvResult:
    """Immutable argv only on success; findings contain codes, never input values."""
    argv: tuple[str, ...] | None = field(default=None, repr=False)
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.argv is not None and not self.reasons

    @property
    def status(self) -> str:
        return "success" if self.ok else "blocked"


@dataclass(frozen=True)
class EnvironmentResult:
    """Detached read-only mapping only on success; no payload in repr."""

    child_env: Mapping[str, str] | None = field(default=None, repr=False)
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.child_env is not None and not self.reasons

    @property
    def status(self) -> str:
        return "success" if self.ok else "blocked"


# Conservative MVP validation policy, not discovered hardware/API limits:
# 16K per axis bounds accidental huge requests; 360 FPS covers the initial
# 60-FPS experiment with headroom. Higher values require a separate policy review.
MAX_DIMENSION = 16384
MAX_FPS = 360


def build_argv(
    options: object, expose_wayland: object = WaylandSupport.UNKNOWN,
) -> ArgvResult:
    """Return fixed nested Wayland flags plus an element-preserving client argv.

    -r is a frame-rate limit, not a physical monitor-mode change. Capability must
    be the explicit SUPPORTED enum member; unknown/unsupported cannot fall back.
    All expected invalid input blocks atomically. No option controls DRM/output
    placement. Strings resembling shell syntax remain literal client arguments.
    """
    reasons = []
    if expose_wayland is WaylandSupport.UNSUPPORTED:
        reasons.append("wayland_exposure_unsupported")
    if expose_wayland is WaylandSupport.UNKNOWN:
        reasons.append("wayland_exposure_unknown")
    if not isinstance(expose_wayland, WaylandSupport):
        reasons.append("wayland_capability_invalid")
    if not isinstance(options, LaunchOptions):
        reasons.append("options_invalid")
        return ArgvResult(reasons=tuple(sorted(set(reasons))))
    for name in ("inner_width", "inner_height", "outer_width", "outer_height"):
        value = getattr(options, name)
        if type(value) is not int or not 1 <= value <= MAX_DIMENSION:
            reasons.append(name + "_invalid")
    if type(options.fps) is not int or not 1 <= options.fps <= MAX_FPS:
        reasons.append("fps_invalid")
    client = options.client_argv
    if not isinstance(client, (tuple, list)) or not client:
        reasons.append("client_argv_invalid")
    if (isinstance(client, (tuple, list)) and client
            and isinstance(client[0], str) and not client[0].strip()):
        reasons.append("client_program_empty")
    if isinstance(client, (tuple, list)) and any(
        not isinstance(value, str) or "\0" in value for value in client
    ):
        reasons.append("client_argument_invalid")
    if reasons:
        return ArgvResult(reasons=tuple(sorted(set(reasons))))
    return ArgvResult((
        "gamescope", "--backend", "wayland", "--expose-wayland",
        "-w", str(options.inner_width), "-h", str(options.inner_height),
        "-W", str(options.outer_width), "-H", str(options.outer_height),
        "-r", str(options.fps), "--", *options.client_argv,
    ))


# Exact names only, never prefix matching:
# XDG_RUNTIME_DIR: supplied base for runtime sockets, not discovered here.
# DBUS_SESSION_BUS_ADDRESS: supplied session bus for later desktop integration.
# LANG/LC_ALL/LC_CTYPE: inherited text/locale behavior, no fabricated defaults.
# This is deliberately NOT a complete launch environment: no PATH/HOME, display
# endpoints, session identity, GPU/backend/loader overrides, credentials or secrets.
# In particular DISPLAY/WAYLAND_DISPLAY/XDG_SESSION_TYPE/XDG_CURRENT_DESKTOP are
# neither inherited nor set. Their eventual introduction needs a separate runtime
# design. Addresses/locale values are not evidence of a valid live session.
ENV_ALLOWLIST = (
    "DBUS_SESSION_BUS_ADDRESS", "LANG", "LC_ALL", "LC_CTYPE", "XDG_RUNTIME_DIR",
)


def build_child_env(parent: object) -> EnvironmentResult:
    """Filter an explicit mapping without reading/changing the real environment.

    Invalid entry types, keys and NULs block the entire result, even in unknown
    entries; well-formed unknown/sensitive keys are dropped. Only exact allowlist
    members survive, so TOKEN/SECRET/PASSWORD/CREDENTIAL/COOKIE, SSH_AUTH_SOCK,
    GITHUB_*, GH_*, AWS_* and Steam secrets cannot sneak in via a similar prefix.
    Empty locale values are preserved (they can mean no locale override).
    Empty socket addresses block; this does not verify a live socket or session.
    Empty input produces an empty mapping, not invented runtime defaults.
    Payloads are returned only through child_env, never findings or repr.
    """
    if not isinstance(parent, Mapping):
        return EnvironmentResult(reasons=("environment_mapping_invalid",))
    reasons = []
    if any(not isinstance(key, str) or not isinstance(value, str)
           for key, value in parent.items()):
        reasons.append("environment_entry_type_invalid")
    if any((isinstance(key, str) and "\0" in key)
           or (isinstance(value, str) and "\0" in value)
           for key, value in parent.items()):
        reasons.append("environment_nul")
    if any(isinstance(key, str) and "\0" not in key
           and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None for key in parent):
        reasons.append("environment_key_invalid")
    if any(name in parent and parent[name] == ""
           for name in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")):
        reasons.append("environment_value_empty")
    if reasons:
        return EnvironmentResult(reasons=tuple(sorted(set(reasons))))
    child = {name: parent[name] for name in ENV_ALLOWLIST if name in parent}
    return EnvironmentResult(MappingProxyType(child))
