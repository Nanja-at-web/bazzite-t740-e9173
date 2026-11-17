"""Pure DRM flag, EDID and exact association validation; no filesystem access."""
from hashlib import sha256
import re
from .collect import CONNECTOR
from .host_reader import (ParseResult, DrmRaw, DrmOutput, DrmData,
                          KScreenData, KOutput, Associated, immutable)

PCI = r'[0-9a-f]{4}:[0-9a-f]{2}:[01][0-9a-f]\.[0-7]'


def edid_digest(value, empty_allowed=False):
    if type(value) is not bytes or len(value) > 4096:
        raise ValueError
    if not value:
        if empty_allowed:
            return None
        raise ValueError
    if (len(value) % 128 or value[:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00'
            or value[126] + 1 != len(value) // 128
            or any(sum(value[index:index + 128]) % 256
                   for index in range(0, len(value), 128))):
        raise ValueError
    return sha256(value).hexdigest()


def parse_drm(raw):
    if type(raw) is not tuple or len(raw) > 16:
        return ParseResult(reasons=('input_invalid',))
    parsed, addresses, names, digests = [], set(), set(), set()
    for item in raw:
        if type(item) is not DrmRaw or not immutable(item):
            return ParseResult(reasons=('input_invalid',))
        if (type(item.card) is not int or not 0 <= item.card <= 15
                or type(item.connector) is not str or len(item.connector) > 24
                or re.fullmatch(CONNECTOR, item.connector) is None
                or type(item.gpu) is not str or len(item.gpu) != 12
                or re.fullmatch(PCI, item.gpu) is None):
            return ParseResult(reasons=('drm_device_invalid',))
        if type(item.status) is not bytes or item.status not in (b'connected\n', b'disconnected\n'):
            return ParseResult(reasons=('drm_status_invalid',))
        if type(item.enabled) is not bytes or item.enabled not in (b'enabled\n', b'disabled\n'):
            return ParseResult(reasons=('drm_enabled_invalid',))
        connected, enabled = item.status == b'connected\n', item.enabled == b'enabled\n'
        if enabled and not connected:
            return ParseResult(reasons=('inventory_changed',))
        try:
            digest = edid_digest(item.edid, not connected and not enabled)
        except ValueError:
            return ParseResult(reasons=('edid_invalid',))
        address = (item.gpu, item.connector)
        if address in addresses or item.connector in names or digest is not None and digest in digests:
            return ParseResult(reasons=('association_ambiguous',))
        addresses.add(address)
        names.add(item.connector)
        if digest is not None:
            digests.add(digest)
        parsed.append(DrmOutput(item.card, item.connector, item.gpu, connected, enabled, digest))
    return ParseResult(DrmData(tuple(sorted(parsed, key=lambda item: (item.card, item.connector)))))


def _valid_association_data(kscreen, drm):
    if (type(kscreen) is not KScreenData or type(drm) is not DrmData
            or not immutable(kscreen) or not immutable(drm)
            or type(kscreen.outputs) is not tuple or len(kscreen.outputs) > 16
            or type(drm.outputs) is not tuple or len(drm.outputs) > 16):
        return False
    for item in kscreen.outputs:
        if (type(item) is not KOutput or not immutable(item)
                or type(item.output_id) is not int or not 1 <= item.output_id <= 2147483647
                or type(item.name) is not str or len(item.name) > 24
                or re.fullmatch(CONNECTOR, item.name) is None
                or type(item.connected) is not bool or type(item.enabled) is not bool
                or type(item.mirrored) is not bool or item.enabled and not item.connected):
            return False
        if item.enabled:
            rectangle = item.rectangle
            if (type(rectangle) is not tuple or len(rectangle) != 4
                    or any(type(number) is not int for number in rectangle)
                    or not all(-32768 <= number <= 32767 for number in rectangle[:2])
                    or not all(1 <= number <= 16384 for number in rectangle[2:])):
                return False
        elif item.rectangle is not None:
            return False
    for item in drm.outputs:
        if (type(item) is not DrmOutput or not immutable(item)
                or type(item.card) is not int or not 0 <= item.card <= 15
                or type(item.connector) is not str or len(item.connector) > 24
                or re.fullmatch(CONNECTOR, item.connector) is None
                or type(item.gpu) is not str or re.fullmatch(PCI, item.gpu) is None
                or type(item.connected) is not bool or type(item.enabled) is not bool
                or item.enabled and not item.connected):
            return False
        if item.digest is None:
            if item.connected or item.enabled:
                return False
        elif (type(item.digest) is not str or len(item.digest) != 64
              or re.fullmatch(r'[0-9a-f]{64}', item.digest) is None):
            return False
    return True


def associate(kscreen, drm, edids):
    if (not _valid_association_data(kscreen, drm)
            or type(edids) is not tuple or len(edids) > 16
            or len(kscreen.outputs) != len(drm.outputs)):
        return ParseResult(reasons=('association_ambiguous',))
    lookup = {}
    for item in edids:
        if (type(item) is not tuple or len(item) != 2 or type(item[0]) is not int
                or not 1 <= item[0] <= 2147483647 or item[0] in lookup
                or type(item[1]) is not bytes):
            return ParseResult(reasons=('association_ambiguous',))
        lookup[item[0]] = item[1]
    result, used = [], set()
    for output in kscreen.outputs:
        candidates = [item for item in drm.outputs if item.connector == output.name]
        if len(candidates) != 1 or output.output_id not in lookup:
            return ParseResult(reasons=('association_ambiguous',))
        match = candidates[0]
        if match.connected is not output.connected or match.enabled is not output.enabled:
            return ParseResult(reasons=('inventory_changed',))
        try:
            digest = edid_digest(lookup[output.output_id], not output.connected and not output.enabled)
        except ValueError:
            return ParseResult(reasons=('edid_invalid',))
        if digest != match.digest or (match.card, match.connector) in used:
            return ParseResult(reasons=('association_ambiguous',))
        used.add((match.card, match.connector))
        result.append((digest, match.gpu, match.connector, output.name,
                       output.enabled, output.mirrored, output.connected))
    if len(lookup) != len(result):
        return ParseResult(reasons=('association_ambiguous',))
    return ParseResult(Associated(tuple(result)))
