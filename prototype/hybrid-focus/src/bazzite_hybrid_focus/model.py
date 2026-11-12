"""Pure state and controller identity types."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Sequence


GlyphFamily = Literal["xbox", "playstation", "nintendo", "neutral"]


class FocusTarget(str, Enum):
    GAME = "game"
    DESKTOP = "desktop"


@dataclass(frozen=True)
class ControllerDevice:
    path: str
    name: str
    vendor_id: str | None
    product_id: str | None
    profile_name: str


@dataclass(frozen=True)
class FocusStatus:
    target: FocusTarget
    devices: tuple[ControllerDevice, ...]
    glyph_family: GlyphFamily
    degraded: bool = False
    message: str = ""


_VENDOR_FAMILIES: dict[str, GlyphFamily] = {
    "045e": "xbox",
    "054c": "playstation",
    "057e": "nintendo",
}


def _normalize_hex_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    try:
        return f"{int(normalized, 16):04x}"
    except ValueError:
        return None


def classify_glyph_family(devices: Sequence[ControllerDevice]) -> GlyphFamily:
    """Return a family only when every connected device agrees."""

    if not devices:
        return "neutral"
    families = {
        _VENDOR_FAMILIES.get(_normalize_hex_id(device.vendor_id) or "", "neutral")
        for device in devices
    }
    if len(families) != 1 or "neutral" in families:
        return "neutral"
    return families.pop()
