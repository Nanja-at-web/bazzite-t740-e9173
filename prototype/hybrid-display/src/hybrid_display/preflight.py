"""Pure preflight decision over caller-supplied data."""

from .model import Finding, Output, OutputIdentity, PreflightResult, SessionSnapshot
from .outputs import outputs_are_valid, resolve_output


def evaluate_preflight(snapshot: object) -> PreflightResult:
    """Assess supplied facts only; no probing, repair, default selection or start."""
    findings = []
    if not isinstance(snapshot, SessionSnapshot):
        return PreflightResult((Finding("snapshot_invalid"),))
    flags = (snapshot.own_local_session, snapshot.kwin_running,
             snapshot.focus_service_active, snapshot.decky_active)
    schema_valid = (isinstance(snapshot.session_type, str)
                    and isinstance(snapshot.desktop, str)
                    and all(type(value) is bool for value in flags)
                    and isinstance(snapshot.outputs, (tuple, list))
                    and all(isinstance(o, Output) and isinstance(o.identity, OutputIdentity)
                            for o in snapshot.outputs)
                    and isinstance(snapshot.existing_clients, (tuple, list))
                    and all(isinstance(name, str) and name for name in snapshot.existing_clients)
                    and isinstance(snapshot.capabilities, (set, frozenset))
                    and all(isinstance(name, str) and name for name in snapshot.capabilities))
    if not schema_valid:
        findings.append(Finding("snapshot_invalid"))
    outputs = snapshot.outputs if isinstance(snapshot.outputs, (tuple, list)) else ()
    outputs = tuple(o for o in outputs if isinstance(o, Output) and isinstance(o.identity, OutputIdentity))
    if not outputs_are_valid(snapshot.outputs):
        findings.append(Finding("outputs_invalid"))
    capabilities = snapshot.capabilities if isinstance(snapshot.capabilities, (set, frozenset)) else frozenset()
    if snapshot.session_type != "wayland":
        findings.append(Finding("session_not_wayland"))
    if snapshot.desktop not in ("KDE", "plasma", "Plasma"):
        findings.append(Finding("session_not_plasma"))
    if snapshot.kwin_running is not True:
        findings.append(Finding("kwin_missing"))
    if snapshot.own_local_session is not True:
        findings.append(Finding("session_not_local"))
    if sum(o.enabled is True for o in outputs) < 2:
        findings.append(Finding("too_few_active_outputs"))
    if any(o.enabled and o.mirrored for o in outputs):
        findings.append(Finding("mirrored_outputs"))
    if snapshot.existing_clients:
        findings.append(Finding("process_conflict"))
    if snapshot.focus_service_active is not False:
        findings.append(Finding("focus_integration_active"))
    if snapshot.decky_active is not False:
        findings.append(Finding("decky_active"))
    if "gamescope" not in capabilities:
        findings.append(Finding("missing_gamescope"))
    if "vkcube" not in capabilities:
        findings.append(Finding("missing_graphics_client"))
    if not snapshot.gaming_edid_sha256:
        findings.append(Finding("selection_missing"))
    else:
        findings.extend(Finding(reason) for reason in resolve_output(outputs, snapshot.gaming_edid_sha256).reasons)
    if any(not o.identity.manufacturer or not o.identity.model for o in outputs):
        findings.append(Finding("monitor_description_missing", "warning"))
    return PreflightResult(tuple(sorted(set(findings), key=lambda f: f.code)))
