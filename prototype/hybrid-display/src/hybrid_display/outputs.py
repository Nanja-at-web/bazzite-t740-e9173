"""Pure monitor identity resolution. No display queries or changes."""

from .model import Output, OutputIdentity, OutputResolution, normalize_edid_sha256


def output_is_valid(output: object) -> bool:
    """Validate supplied fields; a disconnected unused connector may lack EDID."""
    if not isinstance(output, Output) or not isinstance(output.identity, OutputIdentity):
        return False
    identity = output.identity
    flags = (output.enabled, output.connected, output.mirrored)
    names = (output.gpu_pci, output.drm_connector, output.kwin_name)
    valid_digest = normalize_edid_sha256(identity.edid_sha256) is not None
    return (
        all(type(flag) is bool for flag in flags)
        and all(isinstance(name, str) and name.strip() for name in names)
        and isinstance(identity.manufacturer, str)
        and isinstance(identity.model, str)
        and (not output.enabled or output.connected)
        and (valid_digest or (
            not output.connected and not output.enabled and identity.edid_sha256 is None
        ))
    )


def outputs_are_valid(outputs: object) -> bool:
    """Reject malformed inventories and conflicting logical/connector addresses."""
    return (
        isinstance(outputs, (tuple, list))
        and all(output_is_valid(o) for o in outputs)
        and len({(o.gpu_pci, o.drm_connector) for o in outputs}) == len(outputs)
        and len({o.kwin_name for o in outputs}) == len(outputs)
    )


def resolve_output(outputs: object, edid_sha256: object) -> OutputResolution:
    """Resolve only a full EDID digest, never a model, connector or primary hint.

    Expected invalid inputs return reason codes, not exceptions. A uniquely
    matched disabled/disconnected/mirrored output is fully rejected: output=None
    with blocking reasons, preserving the design's no-fallback rule. This function
    neither chooses a gaming role nor activates anything; the caller supplies it.
    """
    digest = normalize_edid_sha256(edid_sha256)
    if digest is None:
        return OutputResolution(reasons=("selection_invalid",))
    if not outputs_are_valid(outputs):
        return OutputResolution(reasons=("outputs_invalid",))
    matches = [o for o in outputs if o.identity.edid_sha256 == digest]
    if not matches:
        return OutputResolution(reasons=("selection_not_found",))
    if len(matches) != 1:
        return OutputResolution(reasons=("selection_ambiguous",))
    match = matches[0]
    reasons = []
    if not match.enabled:
        reasons.append("selected_output_disabled")
    if not match.connected:
        reasons.append("selected_output_disconnected")
    if match.mirrored:
        reasons.append("selected_output_mirrored")
    return OutputResolution(None if reasons else match, tuple(reasons))
