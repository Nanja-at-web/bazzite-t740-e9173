"""Data-only foundation models. No collection or host integration."""

from dataclasses import dataclass, field
import re


def normalize_edid_sha256(value: object) -> str | None:
    """Canonical full digest, or None; never retain raw EDID or invalid data."""
    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return value.lower()
    return None


@dataclass(frozen=True)
class OutputIdentity:
    """Full normalized digest is the sole identity; descriptions are not keys.

    Invalid digests become None and are never eligible connected identities.
    Raw EDID has no field. Full hashes stay internal and out of default repr.
    A future user label is defined as 'edid:' + first 12 lowercase hex digits
    + '…'; a prefix collision must be marked ambiguous, never used for lookup.
    Formatting/export is intentionally outside this foundation.
    """
    edid_sha256: str | None = field(repr=False)
    manufacturer: str = field(default="", compare=False)
    model: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "edid_sha256", normalize_edid_sha256(self.edid_sha256))


@dataclass(frozen=True)
class Output:
    identity: OutputIdentity
    gpu_pci: str
    drm_connector: str
    kwin_name: str
    enabled: bool
    mirrored: bool
    connected: bool | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    """Caller-supplied facts, not evidence of hardware acceptance.

    None means unknown, never an implicit permission. existing_clients contains
    only externally collected conflict labels, not process handles or argv.
    capabilities contains confirmed program names for this graphics stage.
    """
    session_type: str | None = None
    desktop: str | None = None
    own_local_session: bool | None = None
    kwin_running: bool | None = None
    outputs: tuple[Output, ...] | None = None
    existing_clients: tuple[str, ...] | None = None
    focus_service_active: bool | None = None
    decky_active: bool | None = None
    capabilities: frozenset[str] | None = None
    gaming_edid_sha256: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for name in ("outputs", "existing_clients"):
            value = getattr(self, name)
            if isinstance(value, list):
                object.__setattr__(self, name, tuple(value))
        if isinstance(self.capabilities, set):
            object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str = "error"


@dataclass(frozen=True)
class PreflightResult:
    """Stable finding codes; warnings do not grant permission to start hardware."""

    findings: tuple[Finding, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.reasons

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(f.code for f in self.findings if f.severity != "warning")

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(f.code for f in self.findings if f.severity == "warning")

    @property
    def status(self) -> str:
        return "blocked" if not self.ok else "warning" if self.warnings else "success"


@dataclass(frozen=True)
class OutputResolution:
    output: Output | None = None
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.output is not None and not self.reasons
